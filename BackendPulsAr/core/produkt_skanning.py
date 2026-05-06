"""
produkt_skanning.py — Läge 2: per-frame produktskanning mot befintlig karta
──────────────────────────────────────────────────────────────────────────
Parallell till kart-skanningen (Läge 1). Användaren har redan byggt en karta
och VPS-lokaliserat sig. Den här modulen tar emot frames + LiDAR-punkter +
ARKit-pose + T_arkit→karta, kör A1-logiken (bbox-baserad 3D-position) och
skriver positioner direkt i kartans koordinatsystem.

Pipeline per frame:
  1. Qwen 2.5 VL → JSON-rader {namn, bbox} (samma som ProduktPipeline._qwen_hylla)
  2. Projicera frame-punkter (ARKit-world) till portrait-pixel via cameraTransform
  3. För varje bbox: median-djup av träffande punkter → back-projektera centrum
     → world i ARKit-frame
  4. Multiplicera med T_arkit→karta → world i karta-frame
  5. Fuzzy-match mot ICA-katalog (ProduktPipeline._fuzzy_match)
  6. Append till data/kartor/{karta}/identifierade_produkter.json (ej dedup)

Trådsäkerhet: filskrivning skyddas av en process-global lock.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


# ─────────────────────────────────────────────────────────────────
# SINGLETON: ProduktPipeline-instans (lazy-laddar ICA-katalog en gång)
# ─────────────────────────────────────────────────────────────────

_pipeline_singleton = None
_pipeline_lock = threading.Lock()


def _hämta_pipeline():
    """
    Returnerar en delad ProduktPipeline-instans (för _qwen_hylla + _fuzzy_match).
    Skapar med tom frames_dir/positioner/punkter — vi använder bara metoderna.
    """
    global _pipeline_singleton
    if _pipeline_singleton is not None:
        return _pipeline_singleton

    with _pipeline_lock:
        if _pipeline_singleton is not None:
            return _pipeline_singleton

        from core.produkt_pipeline import ProduktPipeline

        # Hitta ICA-katalog (samma default som ProduktPipeline använder)
        kandidat_paths = [
            "data/ica_produkter.json",
            "/home/hartman/ICA_ai/BackendPulsAr/data/ica_produkter.json",
            os.path.join(os.path.dirname(os.path.dirname(__file__)),
                         "data", "ica_produkter.json"),
        ]
        ica_path = next((p for p in kandidat_paths if os.path.exists(p)), kandidat_paths[0])

        # Skapa instans med dummy-data
        _pipeline_singleton = ProduktPipeline(
            frames_dir="/tmp",
            positioner=[],
            punkter_3d=[],
            ica_produkter_path=ica_path,
        )
        print(f"📦 produkt_skanning: laddat ICA-katalog från {ica_path}")
        return _pipeline_singleton


# ─────────────────────────────────────────────────────────────────
# KOORDINAT-MATTE (samma konventioner som ProduktPipeline._identifiera_frame)
# ─────────────────────────────────────────────────────────────────

def _projicera_punkter_till_portrait(
    frame_punkter: List[dict],
    T: np.ndarray,
    T_inv: np.ndarray,
    fx_L: float, fy_L: float, cx_L: float, cy_L: float,
    H_L: float,
) -> List[Tuple[float, float, float]]:
    """World (ARKit) → portrait pixel (u_P, v_P, djup_framåt).
    ARKit camera-frame: +X right, +Y up, +Z BAKÅT. Punkter framför kameran
    har alltså negativt Z. Vi flippar till CV-konvention (Z framåt, Y ned)
    innan pinhole-formeln. Punkter bakom kameran filtreras bort."""
    ut: List[Tuple[float, float, float]] = []
    for p in frame_punkter:
        try:
            X = float(p.get("x", 0))
            Y = float(p.get("y", 0))
            Z = float(p.get("z", 0))
        except (TypeError, ValueError):
            continue
        cam = T_inv @ np.array([X, Y, Z, 1.0])
        # ARKit → CV konvention (Y och Z flippas)
        xc_cv = float(cam[0])
        yc_cv = -float(cam[1])
        djup = -float(cam[2])
        if djup <= 0.1:
            continue
        u_L = fx_L * xc_cv / djup + cx_L
        v_L = fy_L * yc_cv / djup + cy_L
        u_P = H_L - v_L
        v_P = u_L
        ut.append((u_P, v_P, djup))
    return ut


def _back_projicera_bbox_centrum(
    bbox: List[float],
    djup: float,
    T: np.ndarray,
    fx_L: float, fy_L: float, cx_L: float, cy_L: float,
    H_L: float,
) -> Tuple[float, float, float]:
    """Bbox-centrum + djup_framåt → world i ARKit-frame.
    djup är positiv framåt-distans (CV-konvention). Konverterar tillbaka till
    ARKit camera-frame (Y ned → upp, Z framåt → bak) innan T-multiplikation."""
    x1, y1, x2, y2 = bbox
    u_P_c = (x1 + x2) / 2.0
    v_P_c = (y1 + y2) / 2.0
    u_L_c = v_P_c
    v_L_c = H_L - u_P_c
    # CV-pixel → CV camera-frame (X right, Y down, Z forward)
    xc_cv = (u_L_c - cx_L) * djup / fx_L
    yc_cv = (v_L_c - cy_L) * djup / fy_L
    # CV → ARKit camera-frame (Y och Z flippas)
    xc_arkit = xc_cv
    yc_arkit = -yc_cv
    zc_arkit = -djup
    world = T @ np.array([xc_arkit, yc_arkit, zc_arkit, 1.0])
    return float(world[0]), float(world[1]), float(world[2])


def _transformera_arkit_till_karta(
    p_arkit: Tuple[float, float, float],
    T_arkit_till_karta: Optional[np.ndarray],
    cam_arkit: Optional[Tuple[float, float, float]] = None,
) -> Tuple[float, float, float]:
    """Multiplicera (x,y,z) med 4x4 transform. Identitet om transform saknas.

    OBS Y-axeln: både ARKit och kart-frame är gravitations-justerade, så Y
    skall idealt bara translateras (inte roteras). Men VPS-lokaliseringens
    PnP ger 6-DOF-pose med små roll/pitch-fel som blandar in X/Z i Y och
    sprider produkt-höjder med flera meter. Om cam_arkit ges räknar vi ut
    Y-offset från kamera-translationen och translaterar ARKit-Y direkt,
    vilket sidsteg-skär tilt-felet."""
    if T_arkit_till_karta is None:
        return p_arkit
    v = np.array([p_arkit[0], p_arkit[1], p_arkit[2], 1.0])
    w = T_arkit_till_karta @ v
    if cam_arkit is not None:
        cam_v = np.array([cam_arkit[0], cam_arkit[1], cam_arkit[2], 1.0])
        cam_karta = T_arkit_till_karta @ cam_v
        y_offset = float(cam_karta[1]) - float(cam_arkit[1])
        return float(w[0]), float(p_arkit[1]) + y_offset, float(w[2])
    return float(w[0]), float(w[1]), float(w[2])


# ─────────────────────────────────────────────────────────────────
# HUVUDFUNKTION: extrahera produkter från en frame
# ─────────────────────────────────────────────────────────────────

def extrahera_produkter_a1(
    bild_bytes: bytes,
    frame_punkter: List[dict],          # [{x,y,z,...}] i ARKit-world
    transform: List[float],             # 16-floats column-major (ARKit world_from_camera)
    intrinsics: dict,                   # {fx, fy, cx, cy} i PORTRAIT (samma som butik_skanning sparar)
    image_dims: dict,                   # {image_width, image_height} (image_width = H_L)
    T_arkit_till_karta: Optional[List[float]] = None,  # 16-floats column-major eller None
    frame_id: int = 0,
) -> List[dict]:
    """
    Per-frame A1-extraktion. Returnerar lista med produkter där (x,y,z) är
    i kartans koordinatsystem (om T_arkit_till_karta ges) eller ARKit-world annars.

    Returnerade fält per produkt:
      visningsnamn, varumarke, kategori, id, bild_url,
      x, y, z (karta-frame),
      x_arkit, y_arkit, z_arkit (för debug),
      säkerhet, qwen_svar, match_score,
      position_metod, bbox, frame, antal_träffar, observerad
    """
    # ─── Validera & konvertera transformer ───
    if not isinstance(transform, list) or len(transform) != 16:
        return []

    try:
        T = np.array(transform, dtype=np.float64).reshape(4, 4).T  # column-major flat → 4x4
        T_inv = np.linalg.inv(T)
    except (ValueError, np.linalg.LinAlgError):
        return []

    T_ak: Optional[np.ndarray] = None
    if T_arkit_till_karta and isinstance(T_arkit_till_karta, list) and len(T_arkit_till_karta) == 16:
        try:
            T_ak = np.array(T_arkit_till_karta, dtype=np.float64).reshape(4, 4).T
        except ValueError:
            T_ak = None

    fx_P = float(intrinsics.get("fx", 0) or 0)
    fy_P = float(intrinsics.get("fy", 0) or 0)
    cx_P = float(intrinsics.get("cx", 0) or 0)
    cy_P = float(intrinsics.get("cy", 0) or 0)
    H_L = float(image_dims.get("image_width", 0) or 0)  # iOS sparar image_width = H_L

    if fx_P <= 0 or fy_P <= 0 or H_L <= 0:
        return []

    # Återskapa landscape-intrinsics (invers av iOS portrait-konvertering)
    fx_L = fy_P
    fy_L = fx_P
    cx_L = cy_P
    cy_L = H_L - cx_P

    # ─── Avkoda bild ───
    arr = np.frombuffer(bild_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    # ─── Kör Qwen → kandidater {namn, bbox} ───
    pipe = _hämta_pipeline()
    kandidater = pipe._qwen_hylla(img)
    if not kandidater:
        return []

    # ─── Projicera frame-punkter en gång ───
    projicerade = _projicera_punkter_till_portrait(
        frame_punkter, T, T_inv, fx_L, fy_L, cx_L, cy_L, H_L
    )

    # Diagnos: visa hur många LiDAR-punkter vi har att jobba med
    print(f"   📊 Diag: in={len(frame_punkter)} punkter, "
          f"projicerade_framåt={len(projicerade)}, "
          f"intrinsics fx_P={fx_P:.1f} cx_P={cx_P:.1f} cy_P={cy_P:.1f} H_L={H_L:.0f}")

    # Median-djup som fallback
    giltiga_z = [zc for (_, _, zc) in projicerade if 0.3 < zc < 5.0]
    median_djup = float(np.median(giltiga_z)) if giltiga_z else 1.5
    if np.isnan(median_djup) or median_djup <= 0:
        median_djup = 1.5

    # Kameraposition (för fallback)
    cam_x = float(T[0, 3]); cam_y = float(T[1, 3]); cam_z = float(T[2, 3])
    # Yaw från transform (ARKit Y-axel). T[:,2] = kamerans Z-axel i world,
    # vilket pekar BAKÅT i ARKit. Framåt-riktningen = -T[:,2].
    rot_y = math.atan2(-T[0, 2], -T[2, 2])

    # ─── Dedupa kandidater på namn ───
    seen = set()
    unika: List[dict] = []
    for k in kandidater:
        n = k.get("namn", "")
        if n and n not in seen:
            seen.add(n)
            unika.append(k)

    resultat: List[dict] = []
    for kand in unika:
        namn = kand["namn"]
        bbox = kand.get("bbox")

        # Fuzzy-match mot ICA-katalog
        match = pipe._fuzzy_match(namn)
        if not match:
            continue

        prod_x_arkit = prod_y_arkit = prod_z_arkit = None
        position_metod = "fallback_median"
        antal_träffar = 0

        # Bbox-baserad position
        if isinstance(bbox, list) and len(bbox) == 4 and projicerade:
            x1, y1, x2, y2 = bbox
            if x2 > x1 and y2 > y1:
                träffar = [
                    zc for (u_P, v_P, zc) in projicerade
                    if x1 <= u_P <= x2 and y1 <= v_P <= y2
                ]
                antal_träffar = len(träffar)
                if antal_träffar >= 3:
                    djup = float(np.median(träffar))
                    if 0.2 < djup < 10.0 and not np.isnan(djup):
                        prod_x_arkit, prod_y_arkit, prod_z_arkit = _back_projicera_bbox_centrum(
                            bbox, djup, T, fx_L, fy_L, cx_L, cy_L, H_L
                        )
                        position_metod = f"bbox_{antal_träffar}p"

        # Fallback: kamera + median-djup framåt
        if prod_x_arkit is None:
            prod_x_arkit = cam_x + median_djup * math.sin(rot_y)
            prod_z_arkit = cam_z + median_djup * math.cos(rot_y)
            prod_y_arkit = cam_y - 0.3

        if (math.isnan(prod_x_arkit) or math.isnan(prod_y_arkit) or
                math.isnan(prod_z_arkit)):
            continue

        # Transformera till karta-frame.
        # Skicka cam_arkit så Y-translation kan beräknas separat från rotation
        # (T_ak har ofta tilt-fel som annars sprider Y med flera meter).
        prod_x, prod_y, prod_z = _transformera_arkit_till_karta(
            (prod_x_arkit, prod_y_arkit, prod_z_arkit), T_ak,
            cam_arkit=(cam_x, cam_y, cam_z),
        )

        # Säkerhetsbedömning
        score = match.get("score", 0)
        if position_metod.startswith("bbox") and score > 80:
            säkerhet = "hög"
        elif score > 80:
            säkerhet = "medium"
        else:
            säkerhet = "låg"

        # Diagnos: skriv ut kamera + produkt-position så vi kan verifiera koord-fixen
        dx = prod_x_arkit - cam_x
        dz = prod_z_arkit - cam_z
        avstånd = math.sqrt(dx*dx + dz*dz)
        # Kamerapos i karta-frame (för att jämföra mot path)
        if T_ak is not None:
            cam_karta_v = T_ak @ np.array([cam_x, cam_y, cam_z, 1.0])
            cam_karta_str = f" cam_karta=({float(cam_karta_v[0]):+.2f},{float(cam_karta_v[2]):+.2f})"
        else:
            cam_karta_str = " cam_karta=(ingen T_ak)"
        print(f"   🛒 {match['kanoniskt_namn'][:30]:<30} "
              f"cam=({cam_x:+.2f},{cam_z:+.2f}) "
              f"prod_arkit=({prod_x_arkit:+.2f},{prod_z_arkit:+.2f}) "
              f"prod_karta=({prod_x:+.2f},{prod_z:+.2f}){cam_karta_str} "
              f"avstånd={avstånd:.2f}m metod={position_metod}")

        resultat.append({
            "visningsnamn": match["kanoniskt_namn"],
            "varumarke": match.get("varumarke", ""),
            "kategori": match.get("kategori", ""),
            "id": match.get("id", ""),
            "bild_url": match.get("bild_url", ""),
            "x": prod_x,
            "y": prod_y,
            "z": prod_z,
            "x_arkit": prod_x_arkit,
            "y_arkit": prod_y_arkit,
            "z_arkit": prod_z_arkit,
            "frame": frame_id,
            "säkerhet": säkerhet,
            "qwen_svar": namn,
            "match_score": score,
            "position_metod": position_metod,
            "bbox": bbox,
            "antal_träffar": antal_träffar,
            "observerad": time.strftime("%Y-%m-%d %H:%M:%S"),
        })

    return resultat


# ─────────────────────────────────────────────────────────────────
# PERSISTENS — append till kartans identifierade_produkter.json
# ─────────────────────────────────────────────────────────────────

# Per-karta lås så två samtidiga frames inte korrumperar JSON
_skriv_låsen: Dict[str, threading.Lock] = {}
_skriv_låsen_lock = threading.Lock()


def _hämta_skrivlås(karta_namn: str) -> threading.Lock:
    with _skriv_låsen_lock:
        lås = _skriv_låsen.get(karta_namn)
        if lås is None:
            lås = threading.Lock()
            _skriv_låsen[karta_namn] = lås
        return lås


def _karta_dir(karta_namn: str) -> Path:
    """Skriv produkter där viewern och /vps/karta/{gång}/produkter läser dem.
    Tidigare pekade detta på data/kartor/{namn}/ — fel katalog. Butik-skanningen
    och 3D-viewern använder data/butik_modell/identifierade_produkter.json."""
    return Path("/home/hartman/ICA_ai/BackendPulsAr/data/butik_modell")


def append_produkter(karta_namn: str, nya: List[dict]) -> dict:
    """
    Append alla nya observationer till identifierade_produkter.json
    (option 3a — ingen realtids-dedup, sker senare).

    Returnerar {totalt, nya, fil}.
    """
    if not nya:
        return {"totalt": 0, "nya": 0, "fil": ""}

    karta_dir = _karta_dir(karta_namn)
    karta_dir.mkdir(parents=True, exist_ok=True)
    fil = karta_dir / "identifierade_produkter.json"

    lås = _hämta_skrivlås(karta_namn)
    with lås:
        if fil.exists():
            try:
                befintliga = json.loads(fil.read_text(encoding="utf-8"))
                if not isinstance(befintliga, list):
                    befintliga = []
            except (json.JSONDecodeError, OSError):
                befintliga = []
        else:
            befintliga = []

        befintliga.extend(nya)
        fil.write_text(
            json.dumps(befintliga, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return {"totalt": len(befintliga), "nya": len(nya), "fil": str(fil)}


def läs_produkter(karta_namn: str) -> List[dict]:
    fil = _karta_dir(karta_namn) / "identifierade_produkter.json"
    if not fil.exists():
        return []
    try:
        data = json.loads(fil.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


# ─────────────────────────────────────────────────────────────────
# KONSOLIDERING — slå ihop rådata till en produkt-instans per fysisk plats
# ─────────────────────────────────────────────────────────────────

# Säkerhetsranking: hög > medium/medel > låg > okänd
_SÄK_RANK = {"hög": 3, "medium": 2, "medel": 2, "låg": 1, "?": 0, "": 0}


def _spatial_kluster(obs_list: List[dict], threshold: float) -> List[List[dict]]:
    """
    Greedy spatial clustering: tilldelar varje observation till första klustret
    där distansen till klustrets centroid är < threshold meter.

    Detta gör att samma produkt på flera fysiska platser (t.ex. samma vara
    i mejeri OCH frukost) hamnar i separata kluster.
    """
    kluster: List[List[dict]] = []
    for o in obs_list:
        try:
            x = float(o.get("x", 0) or 0)
            y = float(o.get("y", 0) or 0)
            z = float(o.get("z", 0) or 0)
        except (TypeError, ValueError):
            continue

        placed = False
        for k in kluster:
            cx = sum(float(p.get("x", 0) or 0) for p in k) / len(k)
            cy = sum(float(p.get("y", 0) or 0) for p in k) / len(k)
            cz = sum(float(p.get("z", 0) or 0) for p in k) / len(k)
            d = math.sqrt((x - cx) ** 2 + (y - cy) ** 2 + (z - cz) ** 2)
            if d < threshold:
                k.append(o)
                placed = True
                break
        if not placed:
            kluster.append([o])
    return kluster


def _säkerhet_namn(rank: int) -> str:
    if rank >= 3:
        return "hög"
    if rank >= 2:
        return "medium"
    if rank >= 1:
        return "låg"
    return "okänd"


def konsolidera_produkter(
    karta_namn: str,
    distance_threshold: float = 1.5,
) -> dict:
    """
    Konsoliderar rådata-observationer i identifierade_produkter.json till
    produkter_konsoliderade.json där varje fysisk produkt-instans får EN rad.

    Logik:
      1. Gruppera per produkt-id.
      2. Inom varje grupp: spatial sub-clustering (greedy) med distance_threshold.
      3. Inom varje sub-kluster: behåll bara observationer med högst säkerhet.
      4. Vägt medelvärde av (x, y, z) med vikt = match_score.

    Returnerar summary-dict {antal_observationer, antal_kluster, fil}.
    """
    obs_lista = läs_produkter(karta_namn)
    if not obs_lista:
        return {
            "antal_observationer": 0,
            "antal_unika_id": 0,
            "antal_kluster": 0,
            "fil": "",
        }

    # 1) Gruppera per id
    grupper: Dict[str, List[dict]] = {}
    för_id = 0
    for o in obs_lista:
        i = o.get("id", "")
        if not i:
            continue
        grupper.setdefault(i, []).append(o)
        för_id += 1

    konsoliderade: List[dict] = []

    for prod_id, obs in grupper.items():
        # 2) Spatial sub-clustering inom samma id
        sub_kluster = _spatial_kluster(obs, distance_threshold)

        for klust in sub_kluster:
            # 3) Behåll bara bästa säkerhet
            bästa_rank = max(
                _SÄK_RANK.get(o.get("säkerhet", "?"), 0) for o in klust
            )
            kvar = [
                o for o in klust
                if _SÄK_RANK.get(o.get("säkerhet", "?"), 0) == bästa_rank
            ]
            if not kvar:
                kvar = klust  # fallback (borde aldrig hända)

            # 4) Vägt medel av positioner med vikt = match_score (clamp >0)
            try:
                vikter = np.array([
                    max(float(o.get("match_score", 1) or 1), 0.001)
                    for o in kvar
                ])
                xs = np.array([float(o.get("x", 0) or 0) for o in kvar])
                ys = np.array([float(o.get("y", 0) or 0) for o in kvar])
                zs = np.array([float(o.get("z", 0) or 0) for o in kvar])
            except (TypeError, ValueError):
                continue

            w_sum = float(vikter.sum())
            if w_sum <= 0:
                vikter = np.ones(len(kvar)) / len(kvar)
            else:
                vikter = vikter / w_sum

            x_med = float((xs * vikter).sum())
            y_med = float((ys * vikter).sum())
            z_med = float((zs * vikter).sum())

            första = kvar[0]
            bästa_score = max(
                float(o.get("match_score", 0) or 0) for o in kvar
            )

            konsoliderade.append({
                "id": prod_id,
                "visningsnamn": första.get("visningsnamn", ""),
                "varumarke": första.get("varumarke", ""),
                "kategori": första.get("kategori", ""),
                "bild_url": första.get("bild_url", ""),
                "x": x_med,
                "y": y_med,
                "z": z_med,
                "säkerhet": _säkerhet_namn(bästa_rank),
                "antal_observationer": len(klust),
                "antal_använda": len(kvar),
                "bästa_match_score": bästa_score,
                "konsoliderad": time.strftime("%Y-%m-%d %H:%M:%S"),
            })

    # Skriv till disk (separat lås så vi inte krockar med pågående append)
    karta_dir = _karta_dir(karta_namn)
    karta_dir.mkdir(parents=True, exist_ok=True)
    fil = karta_dir / "produkter_konsoliderade.json"

    lås = _hämta_skrivlås(karta_namn + "::konsoliderad")
    with lås:
        fil.write_text(
            json.dumps(konsoliderade, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return {
        "antal_observationer": len(obs_lista),
        "antal_unika_id": len(grupper),
        "antal_kluster": len(konsoliderade),
        "fil": str(fil),
    }


def läs_konsoliderade(karta_namn: str) -> List[dict]:
    fil = _karta_dir(karta_namn) / "produkter_konsoliderade.json"
    if not fil.exists():
        return []
    try:
        data = json.loads(fil.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []

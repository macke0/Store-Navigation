"""
produkt_extraktion.py — Andra scan-passet: extrahera produkter med 3D-koord
"""

import numpy as np
import cv2
from pathlib import Path
import json, time
from typing import List, Dict, Optional

from core.vps_3d import lokalisera, Karta3DCache
from core.scanner import dela_i_rutnät, förbehandla_ruta, MAX_WORKERS
from core.identifiera import identifiera_produkt
import concurrent.futures


# ─── Backproject (uc,vc) till 3D i kamera-koordinater via LiDAR-interp ───
def _kamerakoord_från_uv(uc: float, vc: float,
                         frame_uvs: np.ndarray,
                         frame_xyz_kamera: np.ndarray,
                         max_pixel_avstånd: float = 30.0) -> Optional[np.ndarray]:
    """Samma trick som bygg_3d_karta: nearest-4 viktad interpolation."""
    if len(frame_uvs) == 0:
        return None
    dists = np.linalg.norm(frame_uvs - np.array([uc, vc]), axis=1)
    nearest = np.argsort(dists)[:4]
    if dists[nearest[0]] > max_pixel_avstånd:
        return None
    w = 1.0 / (dists[nearest] + 1e-6)
    w /= w.sum()
    return np.sum(frame_xyz_kamera[nearest] * w[:, None], axis=0)


def _transformera_kamera_till_karta(p_cam: np.ndarray,
                                     pose: dict) -> np.ndarray:
    """
    pose innehåller {x,y,z, roll, pitch, yaw} = kamerans pose i kart-frame.
    Vi behöver R,t så att p_world = R @ p_cam + t.
    """
    cr, cp, cy = np.deg2rad([pose["roll"], pose["pitch"], pose["yaw"]])
    Rx = np.array([[1,0,0],[0,np.cos(cr),-np.sin(cr)],[0,np.sin(cr),np.cos(cr)]])
    Ry = np.array([[np.cos(cp),0,np.sin(cp)],[0,1,0],[-np.sin(cp),0,np.cos(cp)]])
    Rz = np.array([[np.cos(cy),-np.sin(cy),0],[np.sin(cy),np.cos(cy),0],[0,0,1]])
    R = Rz @ Ry @ Rx
    t = np.array([pose["x"], pose["y"], pose["z"]])
    return R @ p_cam + t


# ─── Huvudfunktion: kör på en frame ───
def extrahera_produkter_frame(bild_bytes: bytes,
                              frame_lidar: List[dict],   # [{u,v,x,y,z}] i NY ARKit-frame
                              gång_namn: str,
                              rader: int = 8,
                              kolumner: int = 8) -> List[dict]:
    """Returnerar lista av {visningsnamn, x, y, z, säkerhet, ...}."""
    # 1) Lokalisera frame i kartan
    pose = lokalisera(bild_bytes, gång=gång_namn)
    if not pose.get("hittad"):
        return []

    # 2) Dela i rutor + Qwen/CLIP parallellt
    arr = np.frombuffer(bild_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    boxar = dela_i_rutnät(img, rader, kolumner)

    def _kör(args):
        i, box = args
        x1,y1,x2,y2 = box
        crop = img[y1:y2, x1:x2]
        if crop.size == 0: return None
        prod = identifiera_produkt(förbehandla_ruta(crop), ruta_nr=i)
        if not prod: return None
        return {"i": i, "box": box, **prod}

    träffar = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for r in ex.map(_kör, [(i+1, b) for i, b in enumerate(boxar)]):
            if r: träffar.append(r)

    if not träffar:
        return []

    # 3) Backproject varje träff till kart-koord
    frame_uvs = np.array([[p["u"], p["v"]] for p in frame_lidar], dtype=np.float32)
    frame_xyz_cam = np.array([[p["x"], p["y"], p["z"]] for p in frame_lidar],
                              dtype=np.float32)

    resultat = []
    for t in träffar:
        x1, y1, x2, y2 = t["box"]
        uc, vc = (x1+x2)/2, (y1+y2)/2
        p_cam = _kamerakoord_från_uv(uc, vc, frame_uvs, frame_xyz_cam)
        if p_cam is None:
            continue   # vi kräver djup för att placera prick
        p_map = _transformera_kamera_till_karta(p_cam, pose)
        resultat.append({
            "visningsnamn": t["visningsnamn"],
            "varumarke":    t.get("varumarke", ""),
            "kategori":     t.get("kategori", ""),
            "säkerhet":     t["säkerhet"],
            "clip_likhet":  t.get("clip_likhet", 0.0),
            "x": float(p_map[0]),
            "y": float(p_map[1]),
            "z": float(p_map[2]),
            "frame_pose":   {k: pose[k] for k in ("x","y","z","yaw")},
        })
    return resultat


# ─── Persistens ───
def spara_produkter(gång_namn: str, nya: List[dict]) -> dict:
    """Append + dedup per (visningsnamn, ~position). Lagras bredvid kartan."""
    säker = gång_namn.replace(" ", "_").replace("/", "_")
    fil = Path(f"/tmp/kartor_3d/{säker}/produkter.json")
    fil.parent.mkdir(parents=True, exist_ok=True)
    befintliga = json.loads(fil.read_text()) if fil.exists() else []

    def samma(a, b, tol=0.4):
        if a["visningsnamn"] != b["visningsnamn"]: return False
        d = np.linalg.norm([a["x"]-b["x"], a["y"]-b["y"], a["z"]-b["z"]])
        return d < tol

    for n in nya:
        träff = next((b for b in befintliga if samma(n, b)), None)
        if träff:
            träff["antal_observationer"] = träff.get("antal_observationer", 1) + 1
            träff["x"] = (träff["x"] + n["x"]) / 2  # enkel medelvärdes-uppdatering
            träff["y"] = (träff["y"] + n["y"]) / 2
            träff["z"] = (träff["z"] + n["z"]) / 2
        else:
            n["antal_observationer"] = 1
            n["uppdaterad"] = time.strftime("%Y-%m-%d %H:%M:%S")
            befintliga.append(n)

    fil.write_text(json.dumps(befintliga, indent=2, ensure_ascii=False))
    return {"totalt": len(befintliga), "nya": len(nya)}


def läs_produkter(gång_namn: str) -> List[dict]:
    säker = gång_namn.replace(" ", "_").replace("/", "_")
    fil = Path(f"/tmp/kartor_3d/{säker}/produkter.json")
    return json.loads(fil.read_text()) if fil.exists() else []
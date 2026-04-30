"""
multi_session.py — Multi-session mapping för Puls-AR

Hanterar att slå ihop flera skanningar till en sammanhängande karta.
"""

import json
import shutil
import time
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass

import numpy as np
import cv2
import faiss
import torch

from core.vps_3d import (
    extractor, matcher, device,
    Karta3D, Karta3DCache, FrameData,
    bygg_3d_karta,
    lokalisera,
)
from lightglue.utils import load_image


# ─────────────────────────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────────────────────────

KARTOR_DIR = Path("/home/hartman/ICA_ai/BackendPulsAr/data/kartor")

# Tröskelvärden för transformation
MIN_3D_3D_CORRESPONDENCES = 30      # Minst N matchande 3D-punkter krävs
MAX_REPROJECTION_ERROR_M  = 0.5     # Medelfel max 50 cm efter alignment
MAX_TILT_DEGREES          = 30      # Telefonen bör hållas upprätt
TOP_K_FRAMES_PER_QUERY    = 5       # Antal kandidat-frames per session-frame
SESSION_FRAMES_TO_TEST    = 20      # Antal frames från sessionen att testa mot kartan

# Preflight-tröskel
PREFLIGHT_MIN_INLIERS = 50


# ─────────────────────────────────────────────────────────────────
# DATATYPER
# ─────────────────────────────────────────────────────────────────

@dataclass
class TransformationResultat:
    """Resultat av att försöka hitta transformation mellan session och karta."""
    lyckades: bool
    matris_4x4: Optional[np.ndarray]    # 4x4 rigid transform
    inliers: int
    medelfel_m: float
    anledning: str = ""


# ─────────────────────────────────────────────────────────────────
# 1. PREFLIGHT — Identifiera vilken karta användaren är vid
# ─────────────────────────────────────────────────────────────────

def preflight(bild_bytes: bytes) -> dict:
    """
    Anropas innan skanning startar.
    Returnerar vilken karta användaren är i (om någon känns igen).

    Returnerar:
        {
            "status": "match" | "första_skanning" | "okänd_plats",
            "karta_id": "bromma_maxi" | None,
            "inliers": 87,
            ...
        }
    """
    befintliga_kartor = lista_kartor()

    if not befintliga_kartor:
        return {
            "status": "första_skanning",
            "karta_id": None,
            "meddelande": "Inga befintliga kartor — detta blir första skanningen."
        }

    # Testa mot alla befintliga kartor, välj bäst match
    bästa_match = None
    bästa_inliers = 0

    for karta_id in befintliga_kartor:
        resultat = lokalisera(bild_bytes, gång=karta_id)

        if resultat.get("hittad") and resultat.get("inliers", 0) >= PREFLIGHT_MIN_INLIERS:
            inliers = resultat["inliers"]
            if inliers > bästa_inliers:
                bästa_inliers = inliers
                bästa_match = karta_id

    if bästa_match:
        return {
            "status": "match",
            "karta_id": bästa_match,
            "inliers": bästa_inliers,
            "meddelande": f"Känner igen {bästa_match}"
        }

    return {
        "status": "okänd_plats",
        "karta_id": None,
        "meddelande": "Kunde inte känna igen platsen. Stå där du tidigare skannat."
    }


# ─────────────────────────────────────────────────────────────────
# 2. HITTA TRANSFORMATION mellan session och karta
# ─────────────────────────────────────────────────────────────────

def hitta_transformation(
    session_karta_dir: Path,
    befintlig_karta_id: str,
    verbose: bool = True
) -> TransformationResultat:
    """
    Hitta rigid transformation som mappar session-koordinatsystem
    till befintlig kartas koordinatsystem.

    Algoritm:
        1. Ladda båda kartor
        2. För N frames i sessionen, hitta liknande frames i befintliga kartan
        3. LightGlue-matcha → samla 2D-2D matchningar med 3D i båda
        4. Samla 3D-3D correspondences
        5. RANSAC + Umeyama för att få bästa rigid transform
        6. Verifiera kvalitet
    """
    if verbose:
        print(f"🔗 Söker transformation: {session_karta_dir.name} → {befintlig_karta_id}")

    # Ladda kartor
    session_karta = _ladda_lokal_karta(session_karta_dir)
    if session_karta is None:
        return TransformationResultat(
            False, None, 0, 0.0,
            "Kunde inte ladda session-kartan"
        )

    befintlig_karta = Karta3DCache.ladda(befintlig_karta_id)
    if befintlig_karta is None:
        return TransformationResultat(
            False, None, 0, 0.0,
            f"Kunde inte ladda kartan {befintlig_karta_id}"
        )

    # Samla 3D-3D-correspondences
    correspondences = _samla_3d_correspondences(
        session_karta, befintlig_karta, verbose=verbose
    )

    if verbose:
        print(f"   Samlade {len(correspondences)} 3D-3D-correspondences")

    if len(correspondences) < MIN_3D_3D_CORRESPONDENCES:
        return TransformationResultat(
            False, None, len(correspondences), 0.0,
            f"För få matchande 3D-punkter ({len(correspondences)})"
        )

    # Räkna ut rigid transform med RANSAC
    src_points = np.array([c[0] for c in correspondences], dtype=np.float64)
    dst_points = np.array([c[1] for c in correspondences], dtype=np.float64)

    T, inlier_mask = _ransac_rigid_transform(src_points, dst_points, verbose=verbose)

    if T is None:
        return TransformationResultat(
            False, None, 0, 0.0,
            "RANSAC kunde inte hitta giltig transformation"
        )

    inliers = int(inlier_mask.sum())

    if inliers < MIN_3D_3D_CORRESPONDENCES:
        return TransformationResultat(
            False, None, inliers, 0.0,
            f"För få inliers efter RANSAC ({inliers})"
        )

    # Beräkna medelfel
    src_inliers = src_points[inlier_mask]
    dst_inliers = dst_points[inlier_mask]
    src_homog = np.hstack([src_inliers, np.ones((len(src_inliers), 1))])
    transformerade = (T @ src_homog.T).T[:, :3]
    fel = np.linalg.norm(transformerade - dst_inliers, axis=1)
    medelfel = float(fel.mean())

    if verbose:
        print(f"   RANSAC: {inliers} inliers")
        print(f"   Medelfel: {medelfel:.3f} m")

    if medelfel > MAX_REPROJECTION_ERROR_M:
        return TransformationResultat(
            False, T, inliers, medelfel,
            f"För högt reprojektionsfel ({medelfel:.2f} m)"
        )

    # Verifiera tilt-vinkel
    R = T[:3, :3]
    tilt_grader = _beräkna_tilt(R)

    if verbose:
        print(f"   Tilt: {tilt_grader:.1f}°")

    if tilt_grader > MAX_TILT_DEGREES:
        return TransformationResultat(
            False, T, inliers, medelfel,
            f"För stor tilt ({tilt_grader:.1f}°) — telefonen lutad eller fel orientering"
        )

    if verbose:
        print(f"✅ Transformation lyckades")

    return TransformationResultat(True, T, inliers, medelfel, "OK")


def _ladda_lokal_karta(karta_dir: Path) -> Optional[Karta3D]:
    """Ladda en karta från disk (samma logik som Karta3DCache.ladda men för godtycklig path)."""
    if not (karta_dir / "metadata.json").exists():
        return None

    try:
        with open(karta_dir / "metadata.json") as f:
            meta = json.load(f)

        frames = {}
        for fid in meta.get("frames", []):
            frame_dir = karta_dir / f"frame_{fid}"
            if not frame_dir.exists():
                continue
            frames[fid] = FrameData(
                frame_id=fid,
                keypoints=np.load(frame_dir / "keypoints.npy"),
                descriptors=np.load(frame_dir / "descriptors.npy"),
                scores=np.load(frame_dir / "scores.npy"),
                points_3d=np.load(frame_dir / "points_3d.npy"),
                has_3d=np.load(frame_dir / "has_3d.npy"),
            )

        frame_descriptors = np.load(karta_dir / "frame_descriptors.npy")
        frame_ids = np.load(karta_dir / "frame_ids.npy")
        frame_index = faiss.read_index(str(karta_dir / "frame_index.faiss"))

        return Karta3D(
            namn=karta_dir.name,
            frames=frames,
            frame_descriptors=frame_descriptors,
            frame_ids=frame_ids,
            frame_index=frame_index,
            intrinsics=meta.get("intrinsics", {}),
            all_points_3d=np.load(karta_dir / "all_points_3d.npy"),
            all_descriptors=np.load(karta_dir / "all_descriptors.npy"),
            all_frame_ids=np.load(karta_dir / "all_frame_ids.npy"),
            point_index=faiss.read_index(str(karta_dir / "point_index.faiss")),
        )
    except Exception as e:
        print(f"❌ Kunde inte ladda karta från {karta_dir}: {e}")
        return None


def _samla_3d_correspondences(
    session_karta: Karta3D,
    befintlig_karta: Karta3D,
    verbose: bool = False
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Samla 3D-3D-correspondences mellan session och befintlig karta.

    För varje frame i sessionen:
        - Hitta top-K kandidat-frames i befintliga kartan via FAISS
        - LightGlue-matcha
        - För matcher där båda har 3D: spara (session_3d, befintlig_3d)
    """
    correspondences = []

    if matcher is None:
        if verbose:
            print("   ⚠️ LightGlue ej tillgänglig")
        return correspondences

    # Välj N frames från sessionen att testa (jämnt fördelade)
    session_frame_ids = sorted(session_karta.frames.keys())
    if len(session_frame_ids) > SESSION_FRAMES_TO_TEST:
        steg = len(session_frame_ids) // SESSION_FRAMES_TO_TEST
        session_frame_ids = session_frame_ids[::steg]

    if verbose:
        print(f"   Testar {len(session_frame_ids)} frames från sessionen")

    for fid in session_frame_ids:
        frame = session_karta.frames[fid]

        # Coarse-search via FAISS
        query_mean = frame.descriptors.mean(axis=0, keepdims=True).astype(np.float32)
        faiss.normalize_L2(query_mean)
        _, indices = befintlig_karta.frame_index.search(query_mean, TOP_K_FRAMES_PER_QUERY)
        kandidater = [int(befintlig_karta.frame_ids[i]) for i in indices[0]]

        # LightGlue-matcha mot varje kandidat
        for kandidat_fid in kandidater:
            if kandidat_fid not in befintlig_karta.frames:
                continue
            kandidat = befintlig_karta.frames[kandidat_fid]

            try:
                kp_session = torch.from_numpy(frame.keypoints).float().unsqueeze(0).to(device)
                desc_session = torch.from_numpy(frame.descriptors).float().unsqueeze(0).to(device)
                scores_session = torch.from_numpy(frame.scores).float().unsqueeze(0).to(device)

                kp_kandidat = torch.from_numpy(kandidat.keypoints).float().unsqueeze(0).to(device)
                desc_kandidat = torch.from_numpy(kandidat.descriptors).float().unsqueeze(0).to(device)
                scores_kandidat = torch.from_numpy(kandidat.scores).float().unsqueeze(0).to(device)

                with torch.no_grad():
                    out = matcher({
                        "image0": {
                            "keypoints": kp_session,
                            "descriptors": desc_session,
                            "keypoint_scores": scores_session,
                        },
                        "image1": {
                            "keypoints": kp_kandidat,
                            "descriptors": desc_kandidat,
                            "keypoint_scores": scores_kandidat,
                        }
                    })

                if "matches0" not in out:
                    continue

                matches = out["matches0"][0].cpu().numpy()

                for s_idx, k_idx in enumerate(matches):
                    if k_idx < 0:
                        continue
                    if not frame.has_3d[s_idx]:
                        continue
                    if not kandidat.has_3d[k_idx]:
                        continue

                    p_session = frame.points_3d[s_idx]
                    p_kandidat = kandidat.points_3d[k_idx]

                    # Filtrera NaN
                    if np.any(np.isnan(p_session)) or np.any(np.isnan(p_kandidat)):
                        continue

                    correspondences.append((p_session, p_kandidat))

            except Exception as e:
                if verbose:
                    print(f"   LightGlue-fel för frame {fid}-{kandidat_fid}: {e}")
                continue

    return correspondences


def _ransac_rigid_transform(
    src: np.ndarray,
    dst: np.ndarray,
    max_iter: int = 2000,
    tröskel_m: float = 0.3,
    verbose: bool = False
) -> Tuple[Optional[np.ndarray], np.ndarray]:
    """
    RANSAC för rigid transform (rotation + translation, ingen skalning).

    Använder Umeyama för att lösa varje hypotes.
    """
    n = len(src)
    if n < 3:
        return None, np.zeros(n, dtype=bool)

    bästa_T = None
    bästa_inliers = np.zeros(n, dtype=bool)
    bästa_count = 0

    rng = np.random.default_rng(42)

    for _ in range(max_iter):
        # Slumpmässig sample av 3 punkter
        idx = rng.choice(n, 3, replace=False)
        T_kandidat = _umeyama_rigid(src[idx], dst[idx])

        if T_kandidat is None:
            continue

        # Räkna inliers
        src_homog = np.hstack([src, np.ones((n, 1))])
        transformerade = (T_kandidat @ src_homog.T).T[:, :3]
        fel = np.linalg.norm(transformerade - dst, axis=1)
        inlier_mask = fel < tröskel_m
        count = int(inlier_mask.sum())

        if count > bästa_count:
            bästa_count = count
            bästa_inliers = inlier_mask
            bästa_T = T_kandidat

    # Refinement: återlös med alla inliers
    if bästa_T is not None and bästa_count >= MIN_3D_3D_CORRESPONDENCES:
        bästa_T = _umeyama_rigid(src[bästa_inliers], dst[bästa_inliers])

    return bästa_T, bästa_inliers


def _umeyama_rigid(src: np.ndarray, dst: np.ndarray) -> Optional[np.ndarray]:
    """
    Umeyama-algoritmen för rigid alignment (rotation + translation).
    Ingen skalning — antar att båda är i meter.

    src, dst: (N, 3)
    Returnerar: 4x4 transform-matris, eller None.
    """
    if len(src) < 3:
        return None

    src_centroid = src.mean(axis=0)
    dst_centroid = dst.mean(axis=0)

    src_centered = src - src_centroid
    dst_centered = dst - dst_centroid

    H = src_centered.T @ dst_centered
    U, S, Vt = np.linalg.svd(H)

    R = Vt.T @ U.T

    # Hantera reflektion
    if np.linalg.det(R) < 0:
        Vt[-1, :] *= -1
        R = Vt.T @ U.T

    t = dst_centroid - R @ src_centroid

    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t
    return T


def _beräkna_tilt(R: np.ndarray) -> float:
    """
    Beräkna hur mycket transformationens rotation lutar runt x/z-axlarna
    (dvs ej runt y-axeln, som är förväntad rotation runt gravitationen).
    """
    # I ARKit: y är upp.
    # En "ren" yaw-rotation ger R[1, 1] ≈ 1.
    # Tilt mäts som hur mycket y-axeln avvikit.
    y_axis_efter = R[:, 1]
    y_axis_före = np.array([0, 1, 0])
    cos_vinkel = float(np.clip(y_axis_efter @ y_axis_före, -1, 1))
    vinkel_rad = np.arccos(cos_vinkel)
    return float(np.degrees(vinkel_rad))


# ─────────────────────────────────────────────────────────────────
# 3. APPLICERA TRANSFORMATION
# ─────────────────────────────────────────────────────────────────

def applicera_transformation(karta_dir: Path, T: np.ndarray, verbose: bool = True):
    """
    Applicera 4x4 transform på alla 3D-data i en karta.
    Modifierar filerna in-place.
    """
    if verbose:
        print(f"🔄 Applicerar transformation på {karta_dir.name}")

    # Per-frame points_3d
    for frame_dir in karta_dir.iterdir():
        if not frame_dir.is_dir() or not frame_dir.name.startswith("frame_"):
            continue

        points_3d_path = frame_dir / "points_3d.npy"
        if points_3d_path.exists():
            points = np.load(points_3d_path)
            transformerade = _applicera_på_punkter(points, T)
            np.save(points_3d_path, transformerade)

        # Pose_arkit (4x4 matrix) — komponera med T
        pose_path = frame_dir / "pose_arkit.npy"
        if pose_path.exists():
            pose = np.load(pose_path)
            ny_pose = T @ pose
            np.save(pose_path, ny_pose)

    # all_points_3d
    all_points_path = karta_dir / "all_points_3d.npy"
    if all_points_path.exists():
        all_points = np.load(all_points_path)
        transformerade = _applicera_på_punkter(all_points, T)
        np.save(all_points_path, transformerade)

    if verbose:
        print(f"   ✅ Klart")


def _applicera_på_punkter(points: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Applicera 4x4-transform på en (N, 3)-array av punkter."""
    if len(points) == 0:
        return points

    # Hantera NaN — behåll dem som NaN
    nan_mask = np.any(np.isnan(points), axis=1)
    resultat = points.copy().astype(np.float32)

    om_giltig = ~nan_mask
    if om_giltig.any():
        homog = np.hstack([points[om_giltig], np.ones((om_giltig.sum(), 1))])
        transformerade = (T @ homog.T).T[:, :3]
        resultat[om_giltig] = transformerade

    return resultat


# ─────────────────────────────────────────────────────────────────
# 4. MERGE in i karta
# ─────────────────────────────────────────────────────────────────

def merge_in_i_karta(
    session_karta_dir: Path,
    befintlig_karta_id: str,
    session_id: str,
    verbose: bool = True
) -> dict:
    """
    Kopiera frame-data från session till befintlig karta.
    Bygg om alla index och stora arrays.
    """
    befintlig_dir = KARTOR_DIR / befintlig_karta_id

    if not befintlig_dir.exists():
        return {"ok": False, "fel": f"Befintlig karta {befintlig_karta_id} finns inte"}

    # Ladda metadata
    with open(befintlig_dir / "metadata.json") as f:
        befintlig_meta = json.load(f)

    befintliga_fids = set(befintlig_meta.get("frames", []))
    nästa_fid = (max(befintliga_fids) + 1) if befintliga_fids else 1

    if verbose:
        print(f"🔀 Mergar session in i {befintlig_karta_id}")
        print(f"   Befintlig: {len(befintliga_fids)} frames")

    # Ladda session-metadata
    with open(session_karta_dir / "metadata.json") as f:
        session_meta = json.load(f)

    session_fids = session_meta.get("frames", [])

    # Kopiera frame-mappar med nya frame_ids
    fid_mapping = {}  # session_fid → ny_fid
    for old_fid in session_fids:
        old_dir = session_karta_dir / f"frame_{old_fid}"
        if not old_dir.exists():
            continue

        ny_fid = nästa_fid
        nästa_fid += 1
        ny_dir = befintlig_dir / f"frame_{ny_fid}"
        shutil.copytree(old_dir, ny_dir)
        fid_mapping[old_fid] = ny_fid

        # Skriv källa-info
        källa = {
            "session_id": session_id,
            "ursprunglig_frame_id": old_fid,
        }
        with open(ny_dir / "källa.json", "w") as f:
            json.dump(källa, f)

    if verbose:
        print(f"   Kopierade {len(fid_mapping)} frames (nya IDs: {min(fid_mapping.values())}..{max(fid_mapping.values())})")

    # Bygg om alla frame-level descriptors och index
    nya_fids = sorted(befintliga_fids | set(fid_mapping.values()))
    frame_descriptors_lista = []
    frame_ids_lista = []

    for fid in nya_fids:
        desc_path = befintlig_dir / f"frame_{fid}" / "descriptors.npy"
        if not desc_path.exists():
            continue
        descriptors = np.load(desc_path)
        if len(descriptors) == 0:
            continue
        mean_desc = descriptors.mean(axis=0).astype(np.float32)
        frame_descriptors_lista.append(mean_desc)
        frame_ids_lista.append(fid)

    frame_descriptors_arr = np.array(frame_descriptors_lista)
    faiss.normalize_L2(frame_descriptors_arr)
    frame_ids_arr = np.array(frame_ids_lista, dtype=np.int32)

    np.save(befintlig_dir / "frame_descriptors.npy", frame_descriptors_arr)
    np.save(befintlig_dir / "frame_ids.npy", frame_ids_arr)

    # Bygg FAISS-index för frames
    dim = frame_descriptors_arr.shape[1]
    frame_index = faiss.IndexFlatIP(dim)
    frame_index.add(frame_descriptors_arr)
    faiss.write_index(frame_index, str(befintlig_dir / "frame_index.faiss"))

    # Bygg om punkt-level data
    all_points = []
    all_descs = []
    all_fids = []

    for fid in nya_fids:
        frame_dir = befintlig_dir / f"frame_{fid}"
        descriptors = np.load(frame_dir / "descriptors.npy")
        points_3d = np.load(frame_dir / "points_3d.npy")
        has_3d = np.load(frame_dir / "has_3d.npy")

        for i in range(len(descriptors)):
            if has_3d[i]:
                all_points.append(points_3d[i])
                all_descs.append(descriptors[i])
                all_fids.append(fid)

    if not all_points:
        return {"ok": False, "fel": "Inga 3D-punkter efter merge"}

    all_points_arr = np.array(all_points, dtype=np.float32)
    all_descs_arr = np.array(all_descs, dtype=np.float32)
    all_fids_arr = np.array(all_fids, dtype=np.int32)

    np.save(befintlig_dir / "all_points_3d.npy", all_points_arr)
    np.save(befintlig_dir / "all_descriptors.npy", all_descs_arr)
    np.save(befintlig_dir / "all_frame_ids.npy", all_fids_arr)

    # Bygg punkt-FAISS
    desc_normaliserade = all_descs_arr.copy()
    faiss.normalize_L2(desc_normaliserade)
    point_index = faiss.IndexFlatIP(dim)
    point_index.add(desc_normaliserade)
    faiss.write_index(point_index, str(befintlig_dir / "point_index.faiss"))

    # Uppdatera metadata
    befintlig_meta["frames"] = nya_fids
    befintlig_meta.setdefault("session_log", []).append({
        "session_id": session_id,
        "tidpunkt": time.time(),
        "tillagda_frames": list(fid_mapping.values()),
        "tillagda_punkter": len(all_points) - len(befintlig_meta.get("frames", [])) * 100,  # uppskattning
    })

    with open(befintlig_dir / "metadata.json", "w") as f:
        json.dump(befintlig_meta, f, indent=2)

    # Rensa cache så nästa lokalisering läser om
    Karta3DCache.rensa()

    if verbose:
        print(f"   ✅ Total efter merge: {len(nya_fids)} frames, {len(all_points)} 3D-punkter")

    return {
        "ok": True,
        "tillagda_frames": len(fid_mapping),
        "totalt_frames": len(nya_fids),
        "totalt_punkter": int(len(all_points)),
    }


# ─────────────────────────────────────────────────────────────────
# 5. HÖGNIVÅ — komplett pipeline för att lägga till en session
# ─────────────────────────────────────────────────────────────────

def lägg_till_session(
    session_dir: str,
    punkter_3d: List[dict],
    positioner: List[dict],
    session_id: str,
    förväntat_karta_id: Optional[str] = None,
    verbose: bool = True
) -> dict:
    """
    Komplett pipeline: bygg session-karta, hitta överlapp, transformera, merge.

    Om `förväntat_karta_id` är None → skapar ny karta direkt (första skanning).
    Annars → mergar mot befintlig.
    """
    session_path = Path(session_dir)

    # FALL 1: Första skanning
    if förväntat_karta_id is None:
        if verbose:
            print("🆕 Första skanning — bygger ny karta")

        # bygg_3d_karta i vps_3d.py vill ha gång_namn — vi använder en
        # standard-id "bromma_maxi" från konfig
        from core.vps_3d import bygg_3d_karta
        karta_dir = bygg_3d_karta(
            skanning_dir=session_dir,
            punkter_3d=punkter_3d,
            positioner=positioner,
            gång_namn="bromma_maxi"  # FIXME: gör detta konfigurerbart
        )

        if karta_dir is None:
            return {"ok": False, "fel": "Kunde inte bygga karta"}

        Karta3DCache.rensa()

        return {
            "ok": True,
            "karta_id": "bromma_maxi",
            "första_skanning": True,
            "frames": len([p for p in positioner]),
        }

    # FALL 2: Lägg till på befintlig karta
    if verbose:
        print(f"➕ Lägger till session i {förväntat_karta_id}")

    # Steg 1: Bygg sessions egen lokala karta i temp-mapp
    temp_dir = Path(f"/tmp/session_karta_{session_id}")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    säker_namn = f"_session_{session_id}"
    from core.vps_3d import bygg_3d_karta as bygg_karta_intern

    # bygg_3d_karta använder hårdkodad path. Vi måste därför bygga lokalt
    # på annat sätt. För enkelhetens skull: bygg som vanlig karta först
    # men under temporärt namn som vi kommer ta bort.
    session_karta_dir = bygg_karta_intern(
        skanning_dir=session_dir,
        punkter_3d=punkter_3d,
        positioner=positioner,
        gång_namn=säker_namn
    )

    if session_karta_dir is None:
        return {"ok": False, "fel": "Kunde inte bygga session-kartan"}

    session_karta_path = Path(session_karta_dir)

    try:
        # Steg 2: Hitta transformation
        transform_resultat = hitta_transformation(
            session_karta_path,
            förväntat_karta_id,
            verbose=verbose
        )

        if not transform_resultat.lyckades:
            # Ohanterad — spara info
            ohanterad_path = Path(f"/tmp/ohanterad_session_{session_id}.json")
            with open(ohanterad_path, "w") as f:
                json.dump({
                    "session_id": session_id,
                    "session_karta_dir": str(session_karta_path),
                    "anledning": transform_resultat.anledning,
                    "tidpunkt": time.time(),
                }, f, indent=2)

            return {
                "ok": False,
                "fel": f"Kunde inte hitta överlapp: {transform_resultat.anledning}",
                "ohanterad_sparad": str(ohanterad_path),
                "inliers": transform_resultat.inliers,
            }

        # Steg 3: Applicera transformation
        applicera_transformation(session_karta_path, transform_resultat.matris_4x4, verbose=verbose)

        # Steg 4: Merge in i befintlig karta
        merge_resultat = merge_in_i_karta(
            session_karta_path,
            förväntat_karta_id,
            session_id,
            verbose=verbose
        )

        if not merge_resultat["ok"]:
            return {"ok": False, "fel": merge_resultat.get("fel", "Merge misslyckades")}

        return {
            "ok": True,
            "karta_id": förväntat_karta_id,
            "första_skanning": False,
            "transformation": {
                "inliers": transform_resultat.inliers,
                "medelfel_m": transform_resultat.medelfel_m,
            },
            **merge_resultat,
        }
    finally:
        # Städa bort sessions egen karta
        if session_karta_path.exists():
            shutil.rmtree(session_karta_path, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────
# HJÄLPFUNKTIONER
# ─────────────────────────────────────────────────────────────────

def lista_kartor() -> List[str]:
    """Lista alla befintliga kartor."""
    if not KARTOR_DIR.exists():
        return []
    return [
        d.name
        for d in KARTOR_DIR.iterdir()
        if d.is_dir() and (d / "metadata.json").exists() and not d.name.startswith("_")
    ]


# ─────────────────────────────────────────────────────────────────
# CLI TEST
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    print("🧪 multi_session.py test")
    print(f"Kartor: {lista_kartor()}")
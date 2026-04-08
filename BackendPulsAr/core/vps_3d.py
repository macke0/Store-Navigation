"""
vps_3d.py — Google-style VPS med LightGlue + PnP
─────────────────────────────────────────────────

Pipeline:
  SKANNING:
    1. Samla frames + LiDAR 3D-punkter
    2. SuperPoint features per frame
    3. Koppla 2D features → 3D punkter
    4. Spara per-frame data för LightGlue

  LOKALISERING (coarse-to-fine):
    1. Coarse: FAISS hittar kandidat-frames
    2. Fine: LightGlue matchar query mot top-k frames
    3. PnP + RANSAC → exakt pose

Precision: ~5-15 cm
"""

import numpy as np
import cv2
import faiss
import torch
import os
import json
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
import tempfile

# ─────────────────────────────────────────────────────────────────
# IMPORTS: SuperPoint + LightGlue
# ─────────────────────────────────────────────────────────────────

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"🔧 VPS 3D: använder {device}")

extractor = None
matcher = None

try:
    from lightglue import LightGlue, SuperPoint
    from lightglue.utils import load_image
    
    extractor = SuperPoint(max_num_keypoints=1024).eval().to(device)
    matcher = LightGlue(features="superpoint").eval().to(device)
    
    print("✅ SuperPoint + LightGlue laddade")
except Exception as e:
    print(f"⚠️  Kunde inte ladda modeller: {e}")


# ─────────────────────────────────────────────────────────────────
# DATASTRUKTURER
# ─────────────────────────────────────────────────────────────────

@dataclass
class FrameData:
    """Data för en enskild frame."""
    frame_id: int
    keypoints: np.ndarray       # [K, 2] pixel-koordinater
    descriptors: np.ndarray     # [K, 256]
    scores: np.ndarray          # [K] feature-kvalitet
    points_3d: np.ndarray       # [K, 3] 3D-koordinat (NaN om saknas)
    has_3d: np.ndarray          # [K] bool, har 3D?


@dataclass
class Karta3D:
    """3D VPS-karta för en gång/zon."""
    namn: str
    frames: Dict[int, FrameData]      # frame_id → FrameData
    frame_descriptors: np.ndarray     # [F, 256] medel-descriptor per frame
    frame_ids: np.ndarray             # [F] frame-id:n
    frame_index: faiss.Index          # FAISS för frame retrieval
    intrinsics: dict
    
    # Globalt 3D-index (backup för snabb sökning)
    all_points_3d: np.ndarray         # [N, 3]
    all_descriptors: np.ndarray       # [N, 256]
    all_frame_ids: np.ndarray         # [N]
    point_index: faiss.Index          # FAISS för punkt-sökning


# ─────────────────────────────────────────────────────────────────
# KARTA-CACHE
# ─────────────────────────────────────────────────────────────────

class Karta3DCache:
    """Cache för laddade kartor."""
    _kartor: Dict[str, Karta3D] = {}
    
    @classmethod
    def ladda(cls, gång_namn: str) -> Optional[Karta3D]:
        if gång_namn in cls._kartor:
            return cls._kartor[gång_namn]
        
        säker_namn = gång_namn.replace(" ", "_").replace("/", "_")
        karta_dir = Path(f"/tmp/kartor_3d/{säker_namn}")
        
        if not (karta_dir / "metadata.json").exists():
            return None
        
        try:
            with open(karta_dir / "metadata.json") as f:
                meta = json.load(f)
            
            # Ladda frame-data
            frames = {}
            frame_list = meta.get("frames", [])
            
            for fid in frame_list:
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
            
            # Ladda frame-level index
            frame_descriptors = np.load(karta_dir / "frame_descriptors.npy")
            frame_ids = np.load(karta_dir / "frame_ids.npy")
            frame_index = faiss.read_index(str(karta_dir / "frame_index.faiss"))
            
            # Ladda punkt-index (använd optimerade om de finns)
            optimized_path = karta_dir / "all_points_3d_optimized.npy"
            if optimized_path.exists():
                all_points_3d = np.load(optimized_path)
                print(f"   📈 Använder COLMAP-optimerade punkter")
            else:
                all_points_3d = np.load(karta_dir / "all_points_3d.npy")
            
            all_descriptors = np.load(karta_dir / "all_descriptors.npy")
            all_frame_ids = np.load(karta_dir / "all_frame_ids.npy")
            point_index = faiss.read_index(str(karta_dir / "point_index.faiss"))
            
            karta = Karta3D(
                namn=gång_namn,
                frames=frames,
                frame_descriptors=frame_descriptors,
                frame_ids=frame_ids,
                frame_index=frame_index,
                intrinsics=meta.get("intrinsics", {}),
                all_points_3d=all_points_3d,
                all_descriptors=all_descriptors,
                all_frame_ids=all_frame_ids,
                point_index=point_index,
            )
            
            cls._kartor[gång_namn] = karta
            print(f"📍 Laddade karta: {gång_namn} ({len(frames)} frames, {len(all_points_3d)} 3D-punkter)")
            return karta
            
        except Exception as e:
            print(f"❌ Kunde inte ladda karta {gång_namn}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    @classmethod
    def rensa(cls):
        cls._kartor.clear()
    
    @classmethod
    def lista(cls) -> List[str]:
        kartor_dir = Path("/tmp/kartor_3d")
        if not kartor_dir.exists():
            return []
        return [
            d.name.replace("_", " ")
            for d in kartor_dir.iterdir()
            if d.is_dir() and (d / "metadata.json").exists()
        ]


# ─────────────────────────────────────────────────────────────────
# BYGG 3D-KARTA
# ─────────────────────────────────────────────────────────────────

def bygg_3d_karta(
    skanning_dir: str,
    punkter_3d: List[dict],
    positioner: List[dict],
    gång_namn: str
) -> Optional[str]:
    """
    Bygg 3D VPS-karta med per-frame data för LightGlue.
    """
    if extractor is None:
        print("⚠️  SuperPoint ej tillgänglig")
        return None
    
    print(f"🗺️  Bygger 3D-karta för {gång_namn}...")
    
    säker_namn = gång_namn.replace(" ", "_").replace("/", "_")
    karta_dir = Path(f"/tmp/kartor_3d/{säker_namn}")
    karta_dir.mkdir(parents=True, exist_ok=True)
    
    # Hitta frames
    skanning_path = Path(skanning_dir)
    frame_files = sorted([
        f for f in skanning_path.iterdir()
        if f.name.startswith("frame_") and f.suffix == ".jpg"
    ])
    
    if not frame_files:
        print("⚠️  Inga frames hittade")
        return None
    
    # Bygg lookup: frame_id → 3D-punkter
    punkter_per_frame: Dict[int, List[dict]] = {}
    for p in punkter_3d:
        fid = p.get("frame", 0)
        if fid not in punkter_per_frame:
            punkter_per_frame[fid] = []
        punkter_per_frame[fid].append(p)
    
    print(f"   {len(frame_files)} frames, {len(punkter_3d)} LiDAR-punkter")
    
    # Hämta intrinsics
    intrinsics = {"fx": 1000, "fy": 1000, "cx": 540, "cy": 960}
    if positioner:
        pos = positioner[0]
        intrinsics = {
            "fx": pos.get("fx", 1000),
            "fy": pos.get("fy", 1000),
            "cx": pos.get("cx", 540),
            "cy": pos.get("cy", 960),
        }
    
    # Processera varje frame
    frame_ids_list = []
    frame_mean_descriptors = []
    all_points = []
    all_descs = []
    all_fids = []
    
    for frame_file in frame_files:
        frame_id = int(frame_file.stem.replace("frame_", ""))
        frame_punkter = punkter_per_frame.get(frame_id + 1, [])  # iOS är 1-indexerat
        
        # Extrahera features
        try:
            image = load_image(str(frame_file)).to(device)
            with torch.no_grad():
                feats = extractor.extract(image)
            
            keypoints = feats["keypoints"][0].cpu().numpy()
            descriptors = feats["descriptors"][0].cpu().numpy()
            scores = feats["keypoint_scores"][0].cpu().numpy() if "keypoint_scores" in feats else np.ones(len(keypoints))
            
        except Exception as e:
            print(f"   ⚠️ Frame {frame_id}: {e}")
            continue
        
        # Matcha features till 3D-punkter
        K = len(keypoints)
        points_3d = np.full((K, 3), np.nan, dtype=np.float32)
        has_3d = np.zeros(K, dtype=bool)
        
        if frame_punkter:
            # iOS roterar bilden 90° - transformera koordinater
            frame_uvs = np.array([[p["u"], p["v"]] for p in frame_punkter])
            frame_xyz = np.array([[p["x"], p["y"], p["z"]] for p in frame_punkter])
            
            for i, kp in enumerate(keypoints):
                dists = np.linalg.norm(frame_uvs - kp, axis=1)
                nearest_idx = np.argsort(dists)[:4]
                if dists[nearest_idx[0]] < 30:  # Interpolera om punkter finns nära
                    weights = 1.0 / (dists[nearest_idx] + 1e-6)
                    weights /= weights.sum()
                    xyz_interp = np.sum(frame_xyz[nearest_idx] * weights[:, np.newaxis], axis=0)
                    points_3d[i] = xyz_interp
                    has_3d[i] = True
        
        # Spara frame-data
        frame_dir = karta_dir / f"frame_{frame_id}"
        frame_dir.mkdir(exist_ok=True)
        
        np.save(frame_dir / "keypoints.npy", keypoints.astype(np.float32))
        np.save(frame_dir / "descriptors.npy", descriptors.astype(np.float32))
        np.save(frame_dir / "scores.npy", scores.astype(np.float32))
        np.save(frame_dir / "points_3d.npy", points_3d)
        np.save(frame_dir / "has_3d.npy", has_3d)
        
        # Samla för index
        frame_ids_list.append(frame_id)
        frame_mean_descriptors.append(descriptors.mean(axis=0))
        
        # Samla 3D-punkter med descriptors
        valid_3d = has_3d
        if valid_3d.sum() > 0:
            all_points.append(points_3d[valid_3d])
            all_descs.append(descriptors[valid_3d])
            all_fids.append(np.full(valid_3d.sum(), frame_id, dtype=np.int32))
    
    if not frame_ids_list:
        print("⚠️  Inga frames processerade")
        return None
    
    # Bygg frame-level FAISS index
    frame_desc_arr = np.array(frame_mean_descriptors, dtype=np.float32)
    faiss.normalize_L2(frame_desc_arr)
    
    frame_index = faiss.IndexFlatIP(frame_desc_arr.shape[1])
    frame_index.add(frame_desc_arr)
    
    # Bygg punkt-level FAISS index
    all_points_arr = np.vstack(all_points).astype(np.float32)
    all_descs_arr = np.vstack(all_descs).astype(np.float32)
    all_fids_arr = np.concatenate(all_fids)
    
    faiss.normalize_L2(all_descs_arr)
    point_index = faiss.IndexFlatIP(all_descs_arr.shape[1])
    point_index.add(all_descs_arr)
    
    # Spara globala index
    np.save(karta_dir / "frame_descriptors.npy", frame_desc_arr)
    np.save(karta_dir / "frame_ids.npy", np.array(frame_ids_list, dtype=np.int32))
    faiss.write_index(frame_index, str(karta_dir / "frame_index.faiss"))
    
    np.save(karta_dir / "all_points_3d.npy", all_points_arr)
    np.save(karta_dir / "all_descriptors.npy", all_descs_arr)
    np.save(karta_dir / "all_frame_ids.npy", all_fids_arr)
    faiss.write_index(point_index, str(karta_dir / "point_index.faiss"))
    
    # Metadata
    with open(karta_dir / "metadata.json", "w") as f:
        json.dump({
            "gång": gång_namn,
            "frames": frame_ids_list,
            "antal_frames": len(frame_ids_list),
            "antal_3d_punkter": len(all_points_arr),
            "intrinsics": intrinsics,
            "skapad": time.strftime("%Y-%m-%d %H:%M:%S"),
            "version": "2.0-lightglue",
        }, f, indent=2)
    
    print(f"✅ Karta sparad: {len(frame_ids_list)} frames, {len(all_points_arr)} 3D-punkter")
    
    # ─────────────────────────────────────────────
    # KÖR COLMAP BUNDLE ADJUSTMENT
    # ─────────────────────────────────────────────
    
    try:
        from core.colmap_bundle import optimize_map, COLMAP_AVAILABLE
        
        if COLMAP_AVAILABLE:
            print("🔧 Kör Bundle Adjustment...")
            success = optimize_map(str(karta_dir), verbose=True)
            
            if success:
                # Ladda optimerade punkter och ersätt
                optimized_path = karta_dir / "all_points_3d_optimized.npy"
                if optimized_path.exists():
                    optimized_points = np.load(optimized_path)
                    print(f"   Använder {len(optimized_points)} optimerade 3D-punkter")
        else:
            print("⚠️  COLMAP ej tillgänglig, hoppar över optimering")
            
    except ImportError:
        print("⚠️  colmap_bundle.py saknas, hoppar över optimering")
    except Exception as e:
        print(f"⚠️  Bundle adjustment misslyckades: {e}")
    
    return str(karta_dir)


# ─────────────────────────────────────────────────────────────────
# LOKALISERING MED LIGHTGLUE
# ─────────────────────────────────────────────────────────────────

def lokalisera(
    bild_bytes: bytes,
    gång: str = None,
    intrinsics: dict = None,
    debug: bool = False
) -> dict:
    """
    Lokalisera med coarse-to-fine approach:
    1. FAISS: hitta kandidat-frames
    2. LightGlue: matcha mot bästa frames
    3. PnP + RANSAC: beräkna pose
    """
    t_start = time.time()
    
    if extractor is None:
        return {"hittad": False, "anledning": "SuperPoint ej tillgänglig"}
    
    # ─────────────────────────────────────────────
    # 1. EXTRAHERA FEATURES FRÅN QUERY
    # ─────────────────────────────────────────────
    
    t0 = time.time()
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(bild_bytes)
            temp_path = f.name
        
        query_image = load_image(temp_path).to(device)
        
        with torch.no_grad():
            query_feats = extractor.extract(query_image)
        
        os.unlink(temp_path)
        
    except Exception as e:
        return {"hittad": False, "anledning": f"Feature extraction misslyckades: {e}"}
    
    t_extract = time.time() - t0
    
    query_kp = query_feats["keypoints"][0].cpu().numpy()
    query_desc = query_feats["descriptors"][0].cpu().numpy()
    
    if len(query_kp) < 20:
        return {"hittad": False, "anledning": f"För få features ({len(query_kp)})"}
    
    # ─────────────────────────────────────────────
    # 2. HITTA KARTOR
    # ─────────────────────────────────────────────
    
    if gång:
        kartor_att_söka = [gång]
    else:
        kartor_att_söka = Karta3DCache.lista()
    
    if not kartor_att_söka:
        return {"hittad": False, "anledning": "Inga kartor tillgängliga"}
    
    bästa_resultat = None
    
    for gång_namn in kartor_att_söka:
        karta = Karta3DCache.ladda(gång_namn)
        if karta is None:
            continue
        
        resultat = _lokalisera_mot_karta(
            query_feats, query_kp, query_desc,
            karta,
            intrinsics or karta.intrinsics,
            debug
        )
        resultat["gång"] = gång_namn
        
        if resultat["hittad"]:
            if bästa_resultat is None or resultat.get("inliers", 0) > bästa_resultat.get("inliers", 0):
                bästa_resultat = resultat
    
    t_total = time.time() - t_start
    
    if bästa_resultat is None:
        return {
            "hittad": False,
            "anledning": "Ingen matchning",
            "sökta_kartor": kartor_att_söka,
            "debug": {
                "extract_ms": round(t_extract * 1000, 1),
                "total_ms": round(t_total * 1000, 1),
                "query_features": len(query_kp),
            } if debug else None
        }
    
    if debug:
        bästa_resultat.setdefault("debug", {})
        bästa_resultat["debug"]["total_ms"] = round(t_total * 1000, 1)
    
    return bästa_resultat


def _lokalisera_mot_karta(
    query_feats: dict,
    query_kp: np.ndarray,
    query_desc: np.ndarray,
    karta: Karta3D,
    intrinsics: dict,
    debug: bool
) -> dict:
    """
    Coarse-to-fine lokalisering mot en karta.
    """
    
    # ─────────────────────────────────────────────
    # STEG 1: COARSE - Hitta kandidat-frames (FAISS)
    # ─────────────────────────────────────────────
    
    t0 = time.time()
    
    # Medel-descriptor för query
    query_mean = query_desc.mean(axis=0, keepdims=True).astype(np.float32)
    faiss.normalize_L2(query_mean)
    
    # Hitta top-k frames
    k_frames = min(5, len(karta.frame_ids))
    similarities, frame_indices = karta.frame_index.search(query_mean, k_frames)
    
    candidate_frame_ids = [int(karta.frame_ids[i]) for i in frame_indices[0]]
    
    t_coarse = time.time() - t0
    
    # ─────────────────────────────────────────────
    # STEG 2: FINE - LightGlue matchning
    # ─────────────────────────────────────────────
    
    t0 = time.time()
    all_points_2d = []
    all_points_3d = []
    best_frame_matches = 0
    best_frame_id = None
    
    if matcher is not None:
        # Hitta BÄSTA frame (mest matcher med 3D)
        for fid in candidate_frame_ids:
            if fid not in karta.frames:
                continue
            frame_data = karta.frames[fid]
            
            db_kp = torch.from_numpy(frame_data.keypoints).float().unsqueeze(0).to(device)
            db_desc = torch.from_numpy(frame_data.descriptors).float().unsqueeze(0).to(device)
            db_scores = torch.from_numpy(frame_data.scores).float().unsqueeze(0).to(device)
            
            try:
                with torch.no_grad():
                    data = {
                        "image0": {
                            "keypoints": query_feats["keypoints"],
                            "descriptors": query_feats["descriptors"],
                            "keypoint_scores": query_feats.get("keypoint_scores", torch.ones_like(query_feats["keypoints"][..., 0])),
                        },
                        "image1": {
                            "keypoints": db_kp,
                            "descriptors": db_desc,
                            "keypoint_scores": db_scores,
                        }
                    }
                    matches_output = matcher(data)
                
                if "matches0" in matches_output:
                    matches = matches_output["matches0"][0].cpu().numpy()
                    # Räkna matcher med 3D
                    pts_2d = []
                    pts_3d = []
                    for q_idx, db_idx in enumerate(matches):
                        if db_idx >= 0 and frame_data.has_3d[db_idx]:
                            pts_2d.append(query_kp[q_idx])
                            pts_3d.append(frame_data.points_3d[db_idx])
                    
                    if len(pts_2d) > best_frame_matches:
                        best_frame_matches = len(pts_2d)
                        best_frame_id = fid
                        all_points_2d = pts_2d
                        all_points_3d = pts_3d
                        
            except Exception as e:
                if debug:
                    print(f"   LightGlue fel för frame {fid}: {e}")
                continue
    
    else:
        # Fallback: FAISS nearest neighbor (ratio test)
        query_norm = query_desc.copy().astype(np.float32)
        faiss.normalize_L2(query_norm)
        
        sims, idxs = karta.point_index.search(query_norm, 2)
        
        for i, (sim, idx) in enumerate(zip(sims, idxs)):
            if len(sim) < 2:
                continue
            # Ratio test
            if sim[1] > 0.001 and sim[0] / sim[1] > 1.2 and sim[0] > 0.5:
                all_points_2d.append(query_kp[i])
                all_points_3d.append(karta.all_points_3d[idx[0]])
    
    t_match = time.time() - t0
    
    if len(all_points_2d) < 10:
        return {
            "hittad": False,
            "anledning": f"För få matcher ({len(all_points_2d)})",
            "debug": {
                "coarse_ms": round(t_coarse * 1000, 1),
                "match_ms": round(t_match * 1000, 1),
                "kandidat_frames": candidate_frame_ids,
            } if debug else None
        }
    
    # ─────────────────────────────────────────────
    # STEG 3: PnP + RANSAC
    # ─────────────────────────────────────────────
    
    t0 = time.time()
    
    points_2d = np.array(all_points_2d, dtype=np.float64)
    points_3d = np.array(all_points_3d, dtype=np.float64)
    
    fx = intrinsics.get("fx", 1000)
    fy = intrinsics.get("fy", 1000)
    # Portrait intrinsics (bild roterad 90° clockwise)
    cx_land = intrinsics.get("cx", 960)
    cy_land = intrinsics.get("cy", 720)
    cx = 1440 - cy_land  # portrait cx
    cy = cx_land         # portrait cy
    
    camera_matrix = np.array([
        [fx,  0, cx],
        [ 0, fy, cy],
        [ 0,  0,  1]
    ], dtype=np.float64)
    
    dist_coeffs = np.zeros(4)
    
    success, rvec, tvec, inliers = cv2.solvePnPRansac(
        points_3d, points_2d,
        camera_matrix, dist_coeffs,
        reprojectionError=4.0,
        iterationsCount=2000,
        confidence=0.995,
        flags=cv2.SOLVEPNP_EPNP
    )
    
    t_pnp = time.time() - t0
    
    if not success or inliers is None or len(inliers) < 6:
        return {
            "hittad": False,
            "anledning": f"PnP misslyckades (inliers: {len(inliers) if inliers is not None else 0})",
            "debug": {
                "matcher": len(all_points_2d),
                "pnp_ms": round(t_pnp * 1000, 1),
            } if debug else None
        }
    
    num_inliers = len(inliers)
    
    # Extrahera pose
    R, _ = cv2.Rodrigues(rvec)
    position = -R.T @ tvec
    x, y, z = position.flatten()
    
    # Euler-vinklar
    sy = np.sqrt(R[0, 0]**2 + R[1, 0]**2)
    if sy > 1e-6:
        roll = np.arctan2(R[2, 1], R[2, 2])
        pitch = np.arctan2(-R[2, 0], sy)
        yaw = np.arctan2(R[1, 0], R[0, 0])
    else:
        roll = np.arctan2(-R[1, 2], R[1, 1])
        pitch = np.arctan2(-R[2, 0], sy)
        yaw = 0
    
    # Konfidens
    inlier_ratio = num_inliers / len(all_points_2d)
    if num_inliers >= 40 and inlier_ratio > 0.5:
        konfidens = "hög"
    elif num_inliers >= 20 and inlier_ratio > 0.3:
        konfidens = "medium"
    else:
        konfidens = "låg"
    
    return {
        "hittad": True,
        "x": float(x),
        "y": float(y),
        "z": float(z),
        "roll": float(np.degrees(roll)),
        "pitch": float(np.degrees(pitch)),
        "yaw": float(np.degrees(yaw)),
        "konfidens": konfidens,
        "metod": "lightglue_pnp" if matcher else "faiss_pnp",
        "inliers": num_inliers,
        "debug": {
            "kandidat_frames": candidate_frame_ids,
            "total_matcher": len(all_points_2d),
            "inliers": num_inliers,
            "inlier_ratio": round(inlier_ratio, 3),
            "coarse_ms": round(t_coarse * 1000, 1),
            "match_ms": round(t_match * 1000, 1),
            "pnp_ms": round(t_pnp * 1000, 1),
        } if debug else None
    }


# ─────────────────────────────────────────────────────────────────
# BAKÅTKOMPATIBLA FUNKTIONER
# ─────────────────────────────────────────────────────────────────

def lokalisera_pnp(bild_bytes: bytes, **kwargs) -> dict:
    """Alias för lokalisera()."""
    return lokalisera(bild_bytes, **kwargs)


def lokalisera_kund(bild_bytes: bytes, **kwargs) -> dict:
    """Alias för lokalisera()."""
    return lokalisera(bild_bytes, **kwargs)


# ─────────────────────────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("🧪 Testar VPS 3D med LightGlue...")
    print(f"   SuperPoint: {'✅' if extractor else '❌'}")
    print(f"   LightGlue: {'✅' if matcher else '❌'}")
    
    kartor = Karta3DCache.lista()
    print(f"   Kartor: {kartor}")
    
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            bild = f.read()
        
        resultat = lokalisera(bild, debug=True)
        print(json.dumps(resultat, indent=2, ensure_ascii=False))
"""
colmap_bundle.py — COLMAP Bundle Adjustment för VPS
────────────────────────────────────────────────────

Optimerar 3D-punkter och kameraposer genom att minimera
reprojektionsfel. Körs vid kartbygge (en gång).

Kräver: pip install pycolmap==3.10.0
"""

import numpy as np
import os
import json
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

# ─────────────────────────────────────────────────────────────────
# COLMAP IMPORT
# ─────────────────────────────────────────────────────────────────

try:
    import pycolmap
    COLMAP_AVAILABLE = True
    print("✅ pycolmap laddad")
except ImportError:
    COLMAP_AVAILABLE = False
    print("⚠️  pycolmap ej installerad (pip install pycolmap)")


# ─────────────────────────────────────────────────────────────────
# DATASTRUKTURER
# ─────────────────────────────────────────────────────────────────

@dataclass
class CameraIntrinsics:
    """Kamera-parametrar."""
    fx: float
    fy: float
    cx: float
    cy: float
    width: int = 1920
    height: int = 1080


@dataclass 
class FramePose:
    """Kamerapose för en frame."""
    frame_id: int
    R: np.ndarray  # [3, 3] rotationsmatris
    t: np.ndarray  # [3] translation
    

@dataclass
class OptimizedMap:
    """Resultat från bundle adjustment."""
    points_3d: np.ndarray       # [N, 3] optimerade 3D-punkter
    point_errors: np.ndarray    # [N] reprojektionsfel per punkt
    camera_poses: Dict[int, FramePose]  # frame_id → optimerad pose
    mean_error: float           # medel reprojektionsfel
    success: bool


# ─────────────────────────────────────────────────────────────────
# BUNDLE ADJUSTMENT
# ─────────────────────────────────────────────────────────────────

def bundle_adjustment(
    frames_data: Dict[int, dict],
    intrinsics: CameraIntrinsics,
    initial_poses: Optional[Dict[int, FramePose]] = None,
    max_iterations: int = 100,
    verbose: bool = True
) -> OptimizedMap:
    """
    Kör bundle adjustment på frames med 2D-3D korrespondenser.
    """
    
    if not COLMAP_AVAILABLE:
        print("⚠️  COLMAP ej tillgänglig, returnerar ooptimerade data")
        return _fallback_no_colmap(frames_data)
    
    if verbose:
        print("🔧 Startar Bundle Adjustment...")
    
    t_start = time.time()
    
    # ─────────────────────────────────────────────
    # 1. SAMLA OBSERVATIONER
    # ─────────────────────────────────────────────
    
    # Samla alla 3D-punkter och deras observationer
    all_observations = []  # [(point_idx, frame_id, u, v), ...]
    point_to_frames = {}
    point_idx = 0
    point_coords = {}
    
    for frame_id, data in frames_data.items():
        keypoints = data["keypoints"]
        points_3d = data["points_3d"]
        has_3d = data["has_3d"]
        
        for i in range(len(keypoints)):
            if not has_3d[i]:
                continue
            
            u, v = keypoints[i]
            x, y, z = points_3d[i]
            
            # Kolla om denna 3D-punkt redan finns (inom 5cm)
            found_existing = False
            for existing_idx, (ex, ey, ez) in point_coords.items():
                dist = np.sqrt((x-ex)**2 + (y-ey)**2 + (z-ez)**2)
                if dist < 0.05:
                    all_observations.append((existing_idx, frame_id, u, v))
                    point_to_frames.setdefault(existing_idx, []).append(frame_id)
                    found_existing = True
                    break
            
            if not found_existing:
                point_coords[point_idx] = (x, y, z)
                all_observations.append((point_idx, frame_id, u, v))
                point_to_frames.setdefault(point_idx, []).append(frame_id)
                point_idx += 1
    
    if verbose:
        print(f"   {len(point_coords)} unika 3D-punkter")
        print(f"   {len(all_observations)} observationer")
        print(f"   {len(frames_data)} frames")
    
    # Filtrera: behåll bara punkter som ses i >= 2 frames
    multi_view_points = {
        idx: coords 
        for idx, coords in point_coords.items()
        if len(point_to_frames.get(idx, [])) >= 2
    }
    
    if len(multi_view_points) < 10:
        print("⚠️  För få multi-view punkter för BA")
        return _fallback_no_colmap(frames_data)
    
    if verbose:
        print(f"   {len(multi_view_points)} multi-view punkter (>=2 frames)")
    
    # ─────────────────────────────────────────────
    # 2. BYGG RECONSTRUCTION
    # ─────────────────────────────────────────────
    
    reconstruction = pycolmap.Reconstruction()
    
    # Lägg till kamera
    camera = pycolmap.Camera(
        model="PINHOLE",
        width=intrinsics.width,
        height=intrinsics.height,
        params=[intrinsics.fx, intrinsics.fy, intrinsics.cx, intrinsics.cy]
    )
    camera.camera_id = 1
    reconstruction.add_camera(camera)
    
    # Gruppera observationer per frame och per punkt
    frame_observations = {}  # frame_id → [(u, v, point_idx), ...]
    point_observations = {}  # point_idx → [(frame_id, local_idx), ...]
    
    for pt_idx, frame_id, u, v in all_observations:
        if pt_idx not in multi_view_points:
            continue
        
        if frame_id not in frame_observations:
            frame_observations[frame_id] = []
        
        local_idx = len(frame_observations[frame_id])
        frame_observations[frame_id].append((u, v, pt_idx))
        
        point_observations.setdefault(pt_idx, []).append((frame_id, local_idx))
    
    # Lägg till bilder med deras points2D
    frame_to_img_id = {}
    img_id = 1
    
    for frame_id in sorted(frames_data.keys()):
        image = pycolmap.Image()
        image.image_id = img_id
        image.camera_id = 1
        image.name = f"frame_{frame_id}.jpg"
        image.registered = True
        
        if initial_poses and frame_id in initial_poses:
            pose = initial_poses[frame_id]
            image.qvec = _rotation_matrix_to_quaternion(pose.R)
            image.tvec = pose.t
        
        # Skapa points2D för denna bild
        obs_list = frame_observations.get(frame_id, [])
        points2D = []
        for u, v, pt_idx in obs_list:
            p2d = pycolmap.Point2D()
            p2d.xy = np.array([u, v], dtype=np.float64)
            # point3D_id sätts senare
            points2D.append(p2d)
        
        image.points2D = pycolmap.ListPoint2D(points2D)
        
        reconstruction.add_image(image)
        frame_to_img_id[frame_id] = img_id
        img_id += 1
    
    # Lägg till 3D-punkter med tracks och koppla till points2D
    new_point_mapping = {}
    num_observations_added = 0
    
    for old_idx, (x, y, z) in multi_view_points.items():
        obs_list = point_observations.get(old_idx, [])
        if len(obs_list) < 2:
            continue
        
        # Skapa track
        track = pycolmap.Track()
        for frame_id, local_idx in obs_list:
            im_id = frame_to_img_id.get(frame_id)
            if im_id is not None:
                track.add_element(im_id, local_idx)
        
        if track.length() < 2:
            continue
        
        # Lägg till 3D-punkt
        xyz = np.array([x, y, z], dtype=np.float64)
        color = np.array([128, 128, 128], dtype=np.uint8)
        
        try:
            p3d_id = reconstruction.add_point3D(xyz, track, color)
            new_point_mapping[old_idx] = p3d_id
            num_observations_added += track.length()
        except Exception as e:
            pass
    
    if verbose:
        print(f"   {len(new_point_mapping)} 3D-punkter i reconstruction")
        print(f"   {num_observations_added} 2D-3D observationer")
    
    # Verifiera reconstruction
    num_obs = sum(img.num_points3D for img in reconstruction.images.values())
    if verbose:
        print(f"   Reconstruction: {reconstruction.num_points3D} punkter, {num_obs} observationer")
    
    if reconstruction.num_points3D == 0:
        print("⚠️  Inga 3D-punkter i reconstruction")
        return _fallback_no_colmap(frames_data)
    
    # ─────────────────────────────────────────────
    # 3. KÖR BUNDLE ADJUSTMENT
    # ─────────────────────────────────────────────
    
    ba_options = pycolmap.BundleAdjustmentOptions()
    
    if verbose:
        print("   Kör bundle adjustment...")
    
    try:
        summary = pycolmap.bundle_adjustment(reconstruction, ba_options)
        
        if verbose:
            print(f"   ✅ BA klar!")
            
    except Exception as e:
        print(f"⚠️  Bundle adjustment misslyckades: {e}")
        return _fallback_no_colmap(frames_data)
    
    # ─────────────────────────────────────────────
    # 4. EXTRAHERA RESULTAT
    # ─────────────────────────────────────────────
    
    optimized_points = []
    point_errors = []
    
    for point3d_id, point3d in reconstruction.points3D.items():
        optimized_points.append(point3d.xyz)
        err = point3d.error
        point_errors.append(err if err >= 0 else 0.0)
    
    # Extrahera kameraposer
    camera_poses = {}
    for im_id, img in reconstruction.images.items():
        frame_id = int(img.name.replace("frame_", "").replace(".jpg", ""))
        
        R = _quaternion_to_rotation_matrix(img.cam_from_world.rotation.quat)
        t = np.array(img.cam_from_world.translation)
        
        camera_poses[frame_id] = FramePose(
            frame_id=frame_id,
            R=R,
            t=t
        )
    
    t_total = time.time() - t_start
    mean_err = float(np.mean(point_errors)) if point_errors else 0.0
    
    if verbose:
        print(f"   Total tid: {t_total:.2f}s")
        print(f"   {len(optimized_points)} optimerade 3D-punkter")
        print(f"   Medel reprojektionsfel: {mean_err:.4f} px")
    
    return OptimizedMap(
        points_3d=np.array(optimized_points, dtype=np.float32) if optimized_points else np.zeros((0,3)),
        point_errors=np.array(point_errors, dtype=np.float32) if point_errors else np.zeros(0),
        camera_poses=camera_poses,
        mean_error=mean_err,
        success=True
    )


# ─────────────────────────────────────────────────────────────────
# INTEGRATION MED VPS_3D
# ─────────────────────────────────────────────────────────────────

def optimize_map(karta_dir: str, verbose: bool = True) -> bool:
    """Optimera en befintlig VPS-karta med bundle adjustment."""
    karta_path = Path(karta_dir)
    
    if not (karta_path / "metadata.json").exists():
        print(f"❌ Ingen metadata hittad i {karta_dir}")
        return False
    
    with open(karta_path / "metadata.json") as f:
        meta = json.load(f)
    
    if verbose:
        print(f"🗺️  Optimerar karta: {meta.get('gång', 'okänd')}")
    
    frames_data = {}
    
    for frame_id in meta.get("frames", []):
        frame_dir = karta_path / f"frame_{frame_id}"
        if not frame_dir.exists():
            continue
        
        frames_data[frame_id] = {
            "keypoints": np.load(frame_dir / "keypoints.npy"),
            "points_3d": np.load(frame_dir / "points_3d.npy"),
            "has_3d": np.load(frame_dir / "has_3d.npy"),
            "descriptors": np.load(frame_dir / "descriptors.npy"),
        }
    
    if not frames_data:
        print("❌ Ingen frame-data hittad")
        return False
    
    intr = meta.get("intrinsics", {})
    intrinsics = CameraIntrinsics(
        fx=intr.get("fx", 1000),
        fy=intr.get("fy", 1000),
        cx=intr.get("cx", 540),
        cy=intr.get("cy", 960),
    )
    
    result = bundle_adjustment(frames_data, intrinsics, verbose=verbose)
    
    if not result.success:
        print("❌ Bundle adjustment misslyckades")
        return False
    
    if verbose:
        print("   Sparar optimerade data...")
    
    np.save(karta_path / "all_points_3d_optimized.npy", result.points_3d)
    np.save(karta_path / "point_errors.npy", result.point_errors)
    
    poses_data = {}
    for frame_id, pose in result.camera_poses.items():
        poses_data[str(frame_id)] = {
            "R": pose.R.tolist(),
            "t": pose.t.tolist()
        }
    
    with open(karta_path / "optimized_poses.json", "w") as f:
        json.dump(poses_data, f, indent=2)
    
    meta["optimized"] = True
    meta["mean_reprojection_error"] = result.mean_error
    meta["optimization_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
    
    with open(karta_path / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)
    
    if verbose:
        print(f"✅ Karta optimerad!")
        print(f"   Medel reprojektionsfel: {result.mean_error:.4f} px")
    
    return True


# ─────────────────────────────────────────────────────────────────
# HJÄLPFUNKTIONER
# ─────────────────────────────────────────────────────────────────

def _fallback_no_colmap(frames_data: Dict) -> OptimizedMap:
    """Returnera ooptimerade data när COLMAP ej är tillgängligt."""
    all_points = []
    for frame_id, data in frames_data.items():
        has_3d = data["has_3d"]
        points_3d = data["points_3d"]
        valid = has_3d & ~np.isnan(points_3d).any(axis=1)
        if valid.sum() > 0:
            all_points.append(points_3d[valid])
    
    points = np.vstack(all_points) if all_points else np.zeros((0, 3))
    
    return OptimizedMap(
        points_3d=points,
        point_errors=np.zeros(len(points)),
        camera_poses={},
        mean_error=0.0,
        success=False
    )


def _rotation_matrix_to_quaternion(R: np.ndarray) -> np.ndarray:
    """Konvertera rotationsmatris till quaternion [w, x, y, z]."""
    trace = np.trace(R)
    
    if trace > 0:
        s = 0.5 / np.sqrt(trace + 1.0)
        w = 0.25 / s
        x = (R[2, 1] - R[1, 2]) * s
        y = (R[0, 2] - R[2, 0]) * s
        z = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    
    return np.array([w, x, y, z])


def _quaternion_to_rotation_matrix(q: np.ndarray) -> np.ndarray:
    """Konvertera quaternion [w, x, y, z] till rotationsmatris."""
    w, x, y, z = q
    
    return np.array([
        [1 - 2*y*y - 2*z*z, 2*x*y - 2*z*w, 2*x*z + 2*y*w],
        [2*x*y + 2*z*w, 1 - 2*x*x - 2*z*z, 2*y*z - 2*x*w],
        [2*x*z - 2*y*w, 2*y*z + 2*x*w, 1 - 2*x*x - 2*y*y]
    ])


if __name__ == "__main__":
    print("🧪 Testar COLMAP Bundle Adjustment...")
    print(f"   pycolmap: {'✅' if COLMAP_AVAILABLE else '❌'}")
    
    import sys
    if len(sys.argv) > 1:
        optimize_map(sys.argv[1], verbose=True)
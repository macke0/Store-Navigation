#!/usr/bin/env python3
"""
Generera 2D-butikskarta från 3D-punktmoln.

Användning:
    python generera_2d_karta.py data/kartor/hela_butiken
"""

import sys
import json
from pathlib import Path
import numpy as np
import cv2


CELL_SIZE        = 0.10
GOLV_HOJD        = 0.30
TAK_HOJD         = 2.50
DENSITY_THRESHOLD = 8
MIN_HYLLA_AREA   = 0.2
PADDING_METER    = 1.0


def f(v):
    """Konvertera numpy/float till vanlig Python-float för JSON."""
    return float(round(float(v), 2))


def generera_karta(karta_dir: Path) -> None:
    print(f"📂 Läser punktmoln från: {karta_dir}")
    
    opt_path = karta_dir / "all_points_3d_optimized.npy"
    raw_path = karta_dir / "all_points_3d.npy"
    
    if opt_path.exists():
        points = np.load(opt_path)
        print(f"   ✅ Använder COLMAP-optimerade punkter")
    elif raw_path.exists():
        points = np.load(raw_path)
        print(f"   ⚠️  Använder råa punkter (BA ej körd)")
    else:
        print(f"   ❌ Hittade ingen all_points_3d.npy")
        return
    
    print(f"   {len(points)} 3D-punkter totalt")
    print(f"   X: {points[:,0].min():.1f} → {points[:,0].max():.1f} m")
    print(f"   Y: {points[:,1].min():.1f} → {points[:,1].max():.1f} m (höjd)")
    print(f"   Z: {points[:,2].min():.1f} → {points[:,2].max():.1f} m")
    
    golv_ref = np.percentile(points[:, 1], 5)
    print(f"   🔻 Auto-detekterat golv-referens: Y={golv_ref:.2f}")
    
    höjd_relative = points[:, 1] - golv_ref
    mask = (höjd_relative > GOLV_HOJD) & (höjd_relative < TAK_HOJD)
    hyllpunkter = points[mask]
    
    print(f"   {len(hyllpunkter)} punkter efter golv/tak-filter ({100*len(hyllpunkter)/len(points):.1f}%)")
    
    if len(hyllpunkter) < 100:
        print("   ⚠️  För få hyllpunkter — kartan blir tom")
    
    xz = hyllpunkter[:, [0, 2]]
    
    x_min = float(xz[:, 0].min()) - PADDING_METER
    x_max = float(xz[:, 0].max()) + PADDING_METER
    z_min = float(xz[:, 1].min()) - PADDING_METER
    z_max = float(xz[:, 1].max()) + PADDING_METER
    
    bredd_m = x_max - x_min
    djup_m  = z_max - z_min
    
    print(f"   📐 Kart-dimensioner: {bredd_m:.1f} × {djup_m:.1f} m")
    
    grid_bredd = int(bredd_m / CELL_SIZE) + 1
    grid_djup  = int(djup_m / CELL_SIZE) + 1
    
    grid = np.zeros((grid_djup, grid_bredd), dtype=np.int32)
    
    ix = ((xz[:, 0] - x_min) / CELL_SIZE).astype(int)
    iz = ((xz[:, 1] - z_min) / CELL_SIZE).astype(int)
    
    for x, z in zip(ix, iz):
        if 0 <= x < grid_bredd and 0 <= z < grid_djup:
            grid[z, x] += 1
    
    print(f"   📊 Grid: {grid_djup} × {grid_bredd} celler, max density: {grid.max()}")
    
    occupancy = (grid > DENSITY_THRESHOLD).astype(np.uint8) * 255
    
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    occupancy_clean = cv2.morphologyEx(occupancy, cv2.MORPH_CLOSE, kernel)
    occupancy_clean = cv2.morphologyEx(occupancy_clean, cv2.MORPH_OPEN, kernel)
    
    contours, _ = cv2.findContours(
        occupancy_clean, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    
    hyllor = []
    min_cells = MIN_HYLLA_AREA / (CELL_SIZE ** 2)
    
    for c in contours:
        x_cell, z_cell, w_cell, h_cell = cv2.boundingRect(c)
        area_cells = w_cell * h_cell
        if area_cells < min_cells:
            continue
        
        hyllor.append({
            "x":     f(x_min + x_cell * CELL_SIZE),
            "z":     f(z_min + z_cell * CELL_SIZE),
            "bredd": f(w_cell * CELL_SIZE),
            "djup":  f(h_cell * CELL_SIZE),
        })
    
    print(f"   📦 Hittade {len(hyllor)} objekt (hyllor/möbler)")
    
    karta_data = {
        "bounds": {
            "x_min": f(x_min),
            "x_max": f(x_max),
            "z_min": f(z_min),
            "z_max": f(z_max),
            "bredd": f(bredd_m),
            "djup":  f(djup_m),
        },
        "hyllor": hyllor,
        "metadata": {
            "cell_size_m":       CELL_SIZE,
            "density_threshold": DENSITY_THRESHOLD,
            "golv_ref_y":        f(golv_ref),
            "antal_punkter":     int(len(points)),
            "antal_hyllpunkter": int(len(hyllpunkter)),
        }
    }
    
    json_path = karta_dir / "butikskarta.json"
    with open(json_path, "w") as fh:
        json.dump(karta_data, fh, indent=2)
    print(f"   💾 Sparade JSON: {json_path}")
    
    scale = 10
    img_h = grid_djup * scale
    img_w = grid_bredd * scale
    
    img = np.full((img_h, img_w, 3), 255, dtype=np.uint8)
    
    for row in range(grid_djup):
        for col in range(grid_bredd):
            if grid[row, col] > 0:
                intensitet = min(255, grid[row, col] * 3)
                grå = 255 - intensitet
                y0, y1 = row * scale, (row + 1) * scale
                x0, x1 = col * scale, (col + 1) * scale
                img[y0:y1, x0:x1] = [grå, grå, grå]
    
    overlay = img.copy()
    for h in hyllor:
        x_px = int((h["x"] - x_min) / CELL_SIZE * scale)
        z_px = int((h["z"] - z_min) / CELL_SIZE * scale)
        w_px = int(h["bredd"] / CELL_SIZE * scale)
        d_px = int(h["djup"]  / CELL_SIZE * scale)
        
        cv2.rectangle(overlay, (x_px, z_px), (x_px + w_px, z_px + d_px),
                      (255, 150, 50), -1)
        cv2.rectangle(img,     (x_px, z_px), (x_px + w_px, z_px + d_px),
                      (0, 0, 255), 2)
    
    img = cv2.addWeighted(overlay, 0.3, img, 0.7, 0)
    
    meter_px = int(1.0 / CELL_SIZE * scale)
    cv2.line(img, (20, img_h - 30), (20 + meter_px, img_h - 30), (0, 0, 0), 3)
    cv2.putText(img, "1 m", (20, img_h - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    
    if x_min <= 0 <= x_max and z_min <= 0 <= z_max:
        ox = int((0 - x_min) / CELL_SIZE * scale)
        oz = int((0 - z_min) / CELL_SIZE * scale)
        cv2.circle(img, (ox, oz), 8, (0, 200, 0), -1)
        cv2.putText(img, "origin", (ox + 12, oz + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 150, 0), 1)
    
    png_path = karta_dir / "butikskarta.png"
    cv2.imwrite(str(png_path), img)
    print(f"   🖼️  Sparade PNG: {png_path}")
    
    print(f"\n✅ Klart! {len(hyllor)} hyllor/objekt, {bredd_m:.1f}×{djup_m:.1f} m karta")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Användning: python generera_2d_karta.py <karta_dir>")
        sys.exit(1)
    
    karta_dir = Path(sys.argv[1])
    if not karta_dir.exists():
        print(f"❌ Hittade inte: {karta_dir}")
        sys.exit(1)
    
    generera_karta(karta_dir)
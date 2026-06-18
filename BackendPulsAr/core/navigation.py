"""
navigation.py — Occupancy grid + A*-pathfinding mot kart-3D
─────────────────────────────────────────────────────────────
Bygger en 2D occupancy grid (top-down, y ignoreras) ur kartans
all_points_3d.npy genom att:

  1. Hitta golv-y som 5e percentilen av punkternas y-värden.
  2. Behålla bara punkter mellan (golv + höjd_över_golv_min) och
     (golv + höjd_över_golv_max). Detta filtrerar bort både golvet
     självt och taket/skyltar högt upp.
  3. Projicera överlevande punkter till en (x, z)-cell via
     cell_storlek (default 0.10 m).
  4. Dilatera obstacles med dilation_meter (default 0.35 m) så att
     en person ryms i fri-corridor.

Sedan kan astar_väg(start_xz, mål_xz, karta_namn) returnera en
lista med (x, z)-waypoints i karta-frame.

Allt i karta-koordinatsystemet — samma frame som identifierade_produkter.json.
"""

from __future__ import annotations

import heapq
import json
import math
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np


_KARTA_BAS = Path("/home/hartman/ICA_ai/BackendPulsAr/data/kartor")


# ─────────────────────────────────────────────────────────────────
# CACHE: Grid + meta laddade en gång per process
# ─────────────────────────────────────────────────────────────────

_grid_cache: dict = {}
_grid_cache_lock = threading.Lock()


def _karta_dir(namn: str) -> Path:
    säker = namn.replace(" ", "_").replace("/", "_")
    return _KARTA_BAS / säker


def _rensa_cache(karta_namn: str) -> None:
    with _grid_cache_lock:
        _grid_cache.pop(karta_namn, None)


# ─────────────────────────────────────────────────────────────────
# BYGG OCCUPANCY GRID
# ─────────────────────────────────────────────────────────────────

def bygg_occupancy_grid(
    karta_namn: str,
    cell_storlek: float = 0.10,
    höjd_över_golv_min: float = 0.30,
    höjd_över_golv_max: float = 2.00,
    dilation_meter: float = 0.35,
    marginal: float = 1.0,
) -> dict:
    """
    Läser data/kartor/{karta_namn}/all_points_3d.npy, bygger occupancy-grid,
    sparar occupancy.npy + occupancy_meta.json bredvid den.

    Returnerar meta-dict (samma som sparas till occupancy_meta.json).
    """
    karta_dir = _karta_dir(karta_namn)
    pts_fil = karta_dir / "all_points_3d.npy"
    if not pts_fil.exists():
        return {"ok": False, "fel": f"Saknar {pts_fil}"}

    pts = np.load(pts_fil).astype(np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3 or pts.shape[0] < 100:
        return {"ok": False, "fel": f"Ogiltig punkt-array: {pts.shape}"}

    xs, ys, zs = pts[:, 0], pts[:, 1], pts[:, 2]

    # Robust golv/tak via percentiler
    y_floor = float(np.percentile(ys, 5))
    y_ceil = float(np.percentile(ys, 95))

    h_min = y_floor + höjd_över_golv_min
    h_max = min(y_floor + höjd_över_golv_max, y_ceil - 0.2)

    # Filtrera till "obstacle-höjd"
    obstacle_mask = (ys > h_min) & (ys < h_max)
    obs_pts = pts[obstacle_mask]

    # Bounds (med marginal så att A* har lite svängrum vid kanterna)
    x_min = float(xs.min()) - marginal
    x_max = float(xs.max()) + marginal
    z_min = float(zs.min()) - marginal
    z_max = float(zs.max()) + marginal

    nx = int(np.ceil((x_max - x_min) / cell_storlek))
    nz = int(np.ceil((z_max - z_min) / cell_storlek))

    if nx <= 0 or nz <= 0 or nx * nz > 50_000_000:
        return {"ok": False, "fel": f"Orealistisk grid-storlek: {nx}x{nz}"}

    grid = np.zeros((nz, nx), dtype=np.uint8)  # 0=fri, 1=obstacle

    if obs_pts.shape[0] > 0:
        ix = np.clip(((obs_pts[:, 0] - x_min) / cell_storlek).astype(int), 0, nx - 1)
        iz = np.clip(((obs_pts[:, 2] - z_min) / cell_storlek).astype(int), 0, nz - 1)
        grid[iz, ix] = 1

    # Dilatera obstacles så att en person ryms i fri-corridor
    if dilation_meter > 0:
        radie_celler = int(np.ceil(dilation_meter / cell_storlek))
        if radie_celler > 0:
            kernel_storlek = 2 * radie_celler + 1
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (kernel_storlek, kernel_storlek)
            )
            grid = cv2.dilate(grid, kernel)

    # Spara
    np.save(karta_dir / "occupancy.npy", grid)
    meta = {
        "ok": True,
        "karta_namn": karta_namn,
        "cell_storlek": cell_storlek,
        "x_min": x_min, "x_max": x_max,
        "z_min": z_min, "z_max": z_max,
        "nx": nx, "nz": nz,
        "y_floor": y_floor, "y_ceil": y_ceil,
        "höjd_över_golv_min": höjd_över_golv_min,
        "höjd_över_golv_max": höjd_över_golv_max,
        "h_min": h_min, "h_max": h_max,
        "dilation_meter": dilation_meter,
        "marginal": marginal,
        "antal_punkter_total": int(pts.shape[0]),
        "antal_punkter_obstacle": int(obs_pts.shape[0]),
        "antal_obstacle_celler": int((grid > 0).sum()),
        "antal_fria_celler": int((grid == 0).sum()),
        "skapad": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    (karta_dir / "occupancy_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _rensa_cache(karta_namn)
    return meta


# ─────────────────────────────────────────────────────────────────
# LÄSA / CACHA GRID
# ─────────────────────────────────────────────────────────────────

def läs_grid(karta_namn: str) -> Optional[Tuple[np.ndarray, dict]]:
    with _grid_cache_lock:
        if karta_namn in _grid_cache:
            return _grid_cache[karta_namn]

    d = _karta_dir(karta_namn)
    grid_fil = d / "occupancy.npy"
    meta_fil = d / "occupancy_meta.json"
    if not grid_fil.exists() or not meta_fil.exists():
        return None

    try:
        grid = np.load(grid_fil)
        meta = json.loads(meta_fil.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None

    with _grid_cache_lock:
        _grid_cache[karta_namn] = (grid, meta)
    return grid, meta


def läs_grid_meta(karta_namn: str) -> Optional[dict]:
    res = läs_grid(karta_namn)
    return res[1] if res else None


# ─────────────────────────────────────────────────────────────────
# KOORDINAT-KONVERTERING (karta x,z ↔ grid-cell)
# ─────────────────────────────────────────────────────────────────

def world_till_cell(x: float, z: float, meta: dict) -> Tuple[int, int]:
    cs = meta["cell_storlek"]
    ix = int((x - meta["x_min"]) / cs)
    iz = int((z - meta["z_min"]) / cs)
    return ix, iz


def cell_till_world(ix: int, iz: int, meta: dict) -> Tuple[float, float]:
    cs = meta["cell_storlek"]
    return (
        meta["x_min"] + (ix + 0.5) * cs,
        meta["z_min"] + (iz + 0.5) * cs,
    )


def _hitta_närmaste_fria(
    grid: np.ndarray,
    ix: int,
    iz: int,
    max_radie: int = 30,
    labels: Optional[np.ndarray] = None,
    region: Optional[int] = None,
) -> Optional[Tuple[int, int]]:
    """
    Spiral-sök fria celler om (ix,iz) är obstacle eller out-of-bounds.

    Om `labels` och `region` ges kräver vi att den hittade fria cellen
    ligger i den angivna regionen — annars fortsätter sökandet ut.
    Detta hindrar att snap landar i en isolerad fri-ö som A* sedan inte
    kan nå.
    """
    nz, nx = grid.shape

    def är_giltig(i: int, j: int) -> bool:
        if not (0 <= i < nx and 0 <= j < nz):
            return False
        if grid[j, i] != 0:
            return False
        if labels is not None and region is not None:
            return int(labels[j, i]) == region
        return True

    if är_giltig(ix, iz):
        return ix, iz

    for r in range(1, max_radie + 1):
        # Skanna ringen vid avstånd r (endast kanterna)
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if abs(di) != r and abs(dj) != r:
                    continue
                ni, nj = ix + di, iz + dj
                if är_giltig(ni, nj):
                    return ni, nj
    return None


def _connected_components(grid: np.ndarray) -> Tuple[Optional[np.ndarray], int]:
    """
    Beräknar 4-connected components på fria celler (grid==0).
    Returnerar (labels, huvud_region_label) eller (None, 0) om scipy saknas.
    """
    try:
        from scipy import ndimage
    except ImportError:
        return None, 0

    labels, _n = ndimage.label(grid == 0)
    storlekar = np.bincount(labels.ravel())
    if storlekar.size == 0:
        return labels, 0
    storlekar[0] = 0  # label 0 = obstacles, ignorera
    huvud = int(np.argmax(storlekar))
    return labels, huvud


# ─────────────────────────────────────────────────────────────────
# A*  (8-connected)
# ─────────────────────────────────────────────────────────────────

_GRANNAR_8 = [
    (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
    (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)),
    (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2)),
]


def astar_väg(
    start_xz: Tuple[float, float],
    mål_xz: Tuple[float, float],
    karta_namn: str,
    förenkla: bool = True,
) -> dict:
    """
    A* från start_xz till mål_xz i kartans koordinatsystem.

    Returnerar:
      ok: bool
      waypoints: List[(x, z)] i karta-frame
      längd_meter: float
      antal_celler: int
      start_cell, mål_cell: [ix, iz] (efter eventuell justering till fri cell)
      fel: str (om ok=False)
    """
    res = läs_grid(karta_namn)
    if res is None:
        return {"ok": False, "fel": "occupancy_grid saknas — bygg först"}
    grid, meta = res

    nz, nx = grid.shape

    sx, sz = world_till_cell(start_xz[0], start_xz[1], meta)
    gx, gz = world_till_cell(mål_xz[0], mål_xz[1], meta)

    if not (0 <= sx < nx and 0 <= sz < nz):
        return {"ok": False, "fel": f"Start utanför grid: ({sx},{sz}) vs {nx}x{nz}"}
    if not (0 <= gx < nx and 0 <= gz < nz):
        return {"ok": False, "fel": f"Mål utanför grid: ({gx},{gz}) vs {nx}x{nz}"}

    # Connected components → snap både start och mål till HUVUDREGIONEN
    # (annars kan vi landa i en isolerad fri-ö som A* aldrig når)
    labels, huvud_region = _connected_components(grid)

    nya_start = _hitta_närmaste_fria(
        grid, sx, sz, max_radie=50,
        labels=labels, region=huvud_region if labels is not None else None,
    )
    nya_mål = _hitta_närmaste_fria(
        grid, gx, gz, max_radie=50,
        labels=labels, region=huvud_region if labels is not None else None,
    )

    # Fallback: om vi inte hittade i huvudregionen, försök utan region-filter
    if nya_start is None:
        nya_start = _hitta_närmaste_fria(grid, sx, sz, max_radie=50)
    if nya_mål is None:
        nya_mål = _hitta_närmaste_fria(grid, gx, gz, max_radie=50)

    if nya_start is None:
        return {"ok": False, "fel": "Ingen fri cell nära start"}
    if nya_mål is None:
        return {"ok": False, "fel": "Ingen fri cell nära mål"}
    sx, sz = nya_start
    gx, gz = nya_mål

    # A*
    def h(a: Tuple[int, int], b: Tuple[int, int]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    start_cell = (sx, sz)
    mål_cell = (gx, gz)

    open_set: List[tuple] = [(h(start_cell, mål_cell), 0.0, start_cell)]
    g_score = {start_cell: 0.0}
    came_from: dict = {}

    iterations = 0
    max_iterations = nx * nz  # safety: slutar om vi söker hela griden

    while open_set:
        iterations += 1
        if iterations > max_iterations:
            return {"ok": False, "fel": "A* timeout (max iterations)"}

        _, g, current = heapq.heappop(open_set)

        if current == mål_cell:
            # Rekonstruera väg
            celler = [current]
            while current in came_from:
                current = came_from[current]
                celler.append(current)
            celler.reverse()

            if förenkla:
                celler = _line_of_sight_förenkla(celler, grid)

            waypoints = [list(cell_till_world(ix, iz, meta)) for ix, iz in celler]
            längd_m = g * meta["cell_storlek"]

            return {
                "ok": True,
                "antal_celler_sökta": iterations,
                "antal_waypoints": len(waypoints),
                "längd_meter": längd_m,
                "waypoints": waypoints,
                "start_cell": [sx, sz],
                "mål_cell": [gx, gz],
            }

        if g > g_score.get(current, math.inf):
            continue

        for dx, dz, kostnad in _GRANNAR_8:
            ni = current[0] + dx
            nj = current[1] + dz
            if not (0 <= ni < nx and 0 <= nj < nz):
                continue
            if grid[nj, ni] != 0:
                continue
            ny_g = g + kostnad
            nb = (ni, nj)
            if ny_g < g_score.get(nb, math.inf):
                g_score[nb] = ny_g
                came_from[nb] = current
                f = ny_g + h(nb, mål_cell)
                heapq.heappush(open_set, (f, ny_g, nb))

    return {"ok": False, "fel": "Ingen väg hittad mellan start och mål"}


def _line_of_sight_förenkla(celler: List[Tuple[int, int]], grid: np.ndarray) -> List[Tuple[int, int]]:
    """
    Förenklar väg genom att hoppa över mellanliggande celler om
    det finns rak line-of-sight (alla celler mellan A och B är fria).
    Ger färre waypoints och rakare väg för rendering.
    """
    if len(celler) <= 2:
        return celler

    förenklad = [celler[0]]
    i = 0
    while i < len(celler) - 1:
        # Hitta längsta j > i där LOS från celler[i] till celler[j] är fri
        j = len(celler) - 1
        while j > i + 1 and not _line_of_sight(celler[i], celler[j], grid):
            j -= 1
        förenklad.append(celler[j])
        i = j
    return förenklad


def _line_of_sight(a: Tuple[int, int], b: Tuple[int, int], grid: np.ndarray) -> bool:
    """Bresenham — kollar att alla celler mellan a och b är fria (0)."""
    x0, y0 = a
    x1, y1 = b
    nz, nx = grid.shape

    dx = abs(x1 - x0); dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        if not (0 <= x0 < nx and 0 <= y0 < nz):
            return False
        if grid[y0, x0] != 0:
            return False
        if x0 == x1 and y0 == y1:
            return True
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy

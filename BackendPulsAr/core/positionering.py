"""
positionering.py  –  LiDAR-baserad positionskorrigering
─────────────────────────────────────────────────────────────────
Korrigerar ARKit-drift med LiDAR-djupmätningar.

Princip:
  Om djup_vänster ≈ djup_höger är kameran parallell med hyllan.
  Vi vet då exakt avstånd till hyllan och kan korrigera positionen.
"""

import math


def närmaste_position(frame_nr: int, positioner: list) -> dict:
    """Hittar närmaste position för ett givet frame-nummer."""
    if not positioner:
        return {"x": 0, "y": 0, "z": 0, "djup_fram": 0}

    bästa    = None
    bästa_diff = float("inf")

    for pos in positioner:
        diff = abs(pos.get("frame", 0) - frame_nr)
        if diff < bästa_diff:
            bästa_diff = diff
            bästa      = pos

    return bästa or positioner[0]


def korrigera_position(positioner: list, frame_nr: int) -> dict:
    """
    Korrigerar ARKit-drift med LiDAR-djupmätningar.

    Returnerar korrigerad position med precision-indikator:
    - hög:   LiDAR parallellmätning lyckades
    - medium: LiDAR-djup finns men inte parallell
    - låg:   Bara ARKit, ingen LiDAR
    """
    pos = närmaste_position(frame_nr, positioner)

    djup_vänster = float(pos.get("djup_vänster", 0) or 0)
    djup_höger   = float(pos.get("djup_höger",   0) or 0)
    djup_fram    = float(pos.get("djup_fram",    0) or 0)
    rot_y        = float(pos.get("rot_y",        0) or 0)

    x = float(pos.get("x", 0) or 0)
    y = float(pos.get("y", 0) or 0)
    z = float(pos.get("z", 0) or 0)

    # Är kameran parallell med hyllan?
    har_sido_djup = djup_vänster > 0.1 and djup_höger > 0.1
    parallell     = har_sido_djup and abs(djup_vänster - djup_höger) < 0.3

    if parallell and djup_fram > 0.1:
        # Beräkna avstånd till hyllan
        avstånd = min(djup_vänster, djup_höger, djup_fram)

        # Korrigera position baserat på kamerans riktning
        korr_x = x + avstånd * math.sin(rot_y)
        korr_z = z + avstånd * math.cos(rot_y)

        return {
            **pos,
            "x":          korr_x,
            "y":          y,
            "z":          korr_z,
            "korrigerad": True,
            "precision":  "hög",
        }

    elif djup_fram > 0.1:
        # Har djup men inte parallell
        return {**pos, "korrigerad": False, "precision": "medium"}

    # Bara ARKit
    return {**pos, "korrigerad": False, "precision": "låg"}


def beräkna_hyllposition(position: dict) -> dict:
    """
    Beräknar produktens faktiska position på hyllan.

    Tar hänsyn till att kameran pekar mot hyllan —
    produkten är på det avstånd LiDAR mäter framåt.
    """
    djup_fram = float(position.get("djup_fram", 0) or 0)
    rot_y     = float(position.get("rot_y",     0) or 0)
    x         = float(position.get("x",         0) or 0)
    z         = float(position.get("z",         0) or 0)

    if djup_fram > 0.1:
        produkt_x = x + djup_fram * math.sin(rot_y)
        produkt_z = z + djup_fram * math.cos(rot_y)
        return {**position, "x": produkt_x, "z": produkt_z}

    return position
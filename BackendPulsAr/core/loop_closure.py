"""
loop_closure.py  –  SLAM loop closure korrigering
─────────────────────────────────────────────────────────────────
När scanning avslutas nära startpunkten korrigeras alla
koordinater proportionellt för att eliminera ackumulerad drift.

Princip:
  Start:  (0, 0)
  Slut:   (0.8, 0.3)  ← borde vara (0, 0) om vi är tillbaka
  Drift:  (0.8, 0.3)
  
  Korrigera varje punkt proportionellt baserat på hur långt
  längs rutten den är — punkter i slutet korrigeras mer.
"""

import math


def beräkna_rutlängd(positioner: list) -> list[float]:
    """Beräknar ackumulerad sträcka längs rutten."""
    längder = [0.0]
    for i in range(1, len(positioner)):
        prev = positioner[i-1]
        curr = positioner[i]
        dx = float(curr.get("x", 0)) - float(prev.get("x", 0))
        dz = float(curr.get("z", 0)) - float(prev.get("z", 0))
        längder.append(längder[-1] + math.sqrt(dx*dx + dz*dz))
    return längder


def detektera_loop_closure(positioner: list,
                           tröskel: float = 1.5) -> dict | None:
    """
    Kontrollerar om sista positionen är nära startpositionen.
    
    Returnerar loop closure-info om detekterad, annars None.
    """
    if len(positioner) < 10:
        return None

    start = positioner[0]
    slut  = positioner[-1]

    start_x = float(start.get("x", 0))
    start_z = float(start.get("z", 0))
    slut_x  = float(slut.get("x", 0))
    slut_z  = float(slut.get("z", 0))

    drift_x = slut_x - start_x
    drift_z = slut_z - start_z
    total_drift = math.sqrt(drift_x**2 + drift_z**2)

    if total_drift > tröskel:
        return None

    return {
        "detekterad":  True,
        "drift_x":     drift_x,
        "drift_z":     drift_z,
        "total_drift": total_drift,
    }


def korrigera_loop_closure(positioner: list) -> tuple[list, dict]:
    closure = detektera_loop_closure(positioner)
    if not closure:
        return positioner, {"korrigerad": False}

    drift_x     = closure["drift_x"]
    drift_z     = closure["drift_z"]
    total_drift = closure["total_drift"]

    längder     = beräkna_rutlängd(positioner)
    total_längd = längder[-1]

    if total_längd < 0.1:
        return positioner, {"korrigerad": False}

    korrigerade = []
    for i, pos in enumerate(positioner):
        t = längder[i] / total_längd
        
        # Smooth S-kurva istället för linjär korrigering
        # Korrigerar lite i början, mest i mitten, lite i slutet
        t_smooth = t * t * (3 - 2 * t)
        
        korr_x = float(pos.get("x", 0)) - drift_x * t_smooth
        korr_z = float(pos.get("z", 0)) - drift_z * t_smooth

        korrigerade.append({
            **pos,
            "x": korr_x,
            "z": korr_z,
            "loop_korrigerad": True,
        })

    print(f"✅ Loop closure: drift {total_drift:.2f}m korrigerad (smooth)")
    return korrigerade, {
        "korrigerad":    True,
        "total_drift":   total_drift,
        "drift_x":       drift_x,
        "drift_z":       drift_z,
        "antal_punkter": len(positioner),
    }
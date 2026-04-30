"""
Butik-kalibreringsmodul.

Hanterar koordinattransform mellan VPS-koordinatsystem (meter) och
2D-kartbild (pixlar).

En "butik" består av:
  - En kartbild (PNG/JPG)
  - En kalibrering (affine transform VPS → pixlar)

Filstruktur på disk:
  data/butiker/{butik_id}/
      karta.png
      kalibrering.json
"""

import json
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


# ─────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────

BUTIKER_DIR = Path("/home/hartman/ICA_ai/BackendPulsAr/data/butiker")
BUTIKER_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
# KALIBRERING
# ─────────────────────────────────────────────

def spara_kalibrering(butik_id: str, referenspunkter: list) -> dict:
    """
    Spara kalibreringspunkter och beräkna transformationsmatris.
    
    referenspunkter: [
        {"vps": [x, z], "pixel": [px, py], "beskrivning": "entré"},
        ...
    ]
    
    Minst 3 punkter krävs för affine transform.
    Om 4+ punkter ges: använder homography (hanterar perspektiv).
    
    Returnerar dict med status och matris.
    """
    if len(referenspunkter) < 3:
        return {
            "ok": False,
            "fel": f"Minst 3 referenspunkter krävs, fick {len(referenspunkter)}"
        }
    
    # Extrahera arrays
    vps_pts = np.array([p["vps"] for p in referenspunkter], dtype=np.float32)
    pix_pts = np.array([p["pixel"] for p in referenspunkter], dtype=np.float32)
    
    # Välj transformationstyp baserat på antal punkter
    if len(referenspunkter) == 3:
        # Affine transform: rotation + skalning + translation
        M = cv2.getAffineTransform(vps_pts, pix_pts)
        transform_type = "affine"
        M_list = M.tolist()
    else:
        # Homography: hanterar även perspektiv/skevning
        M, _ = cv2.findHomography(vps_pts, pix_pts, method=0)
        transform_type = "homography"
        M_list = M.tolist()
    
    # Beräkna kalibreringsfel: hur bra matchar transformen referenspunkterna?
    fel_pixlar = []
    for p in referenspunkter:
        vps_xz = np.array([[p["vps"]]], dtype=np.float32)
        if transform_type == "affine":
            pred = cv2.transform(vps_xz, M)[0][0]
        else:
            pred = cv2.perspectiveTransform(vps_xz, M)[0][0]
        
        faktisk = np.array(p["pixel"])
        fel = float(np.linalg.norm(pred - faktisk))
        fel_pixlar.append(fel)
    
    medelfel = float(np.mean(fel_pixlar))
    maxfel = float(np.max(fel_pixlar))
    
    # Spara till disk
    butik_dir = BUTIKER_DIR / butik_id
    butik_dir.mkdir(parents=True, exist_ok=True)
    
    kalibrering_data = {
        "butik_id": butik_id,
        "transform_type": transform_type,
        "matris": M_list,
        "referenspunkter": referenspunkter,
        "kvalitet": {
            "medelfel_pixlar": round(medelfel, 1),
            "maxfel_pixlar":   round(maxfel, 1),
        }
    }
    
    with open(butik_dir / "kalibrering.json", "w") as f:
        json.dump(kalibrering_data, f, indent=2)
    
    print(f"✅ Sparade kalibrering för {butik_id}")
    print(f"   Typ: {transform_type}")
    print(f"   Medelfel: {medelfel:.1f} pixlar")
    print(f"   Max fel:  {maxfel:.1f} pixlar")
    
    return {
        "ok": True,
        "transform_type": transform_type,
        "medelfel_pixlar": round(medelfel, 1),
        "maxfel_pixlar":   round(maxfel, 1),
        "antal_punkter":   len(referenspunkter),
    }


def ladda_kalibrering(butik_id: str) -> Optional[dict]:
    """Ladda kalibrering för en butik. Returnerar None om ej kalibrerad."""
    kal_path = BUTIKER_DIR / butik_id / "kalibrering.json"
    if not kal_path.exists():
        return None
    with open(kal_path) as f:
        return json.load(f)


def vps_till_pixel(butik_id: str, x: float, z: float) -> Optional[dict]:
    """
    Översätt VPS-koordinat (x, z i meter) till pixelposition på kartan.
    
    Returnerar {"pixel_x": ..., "pixel_y": ...} eller None om ej kalibrerad.
    """
    kal = ladda_kalibrering(butik_id)
    if kal is None:
        return None
    
    M = np.array(kal["matris"], dtype=np.float32)
    vps_pt = np.array([[[float(x), float(z)]]], dtype=np.float32)
    
    if kal["transform_type"] == "affine":
        pixel = cv2.transform(vps_pt, M)[0][0]
    else:
        pixel = cv2.perspectiveTransform(vps_pt, M)[0][0]
    
    return {
        "pixel_x": float(round(float(pixel[0]), 1)),
        "pixel_y": float(round(float(pixel[1]), 1)),
    }


def pixel_till_vps(butik_id: str, pixel_x: float, pixel_y: float) -> Optional[dict]:
    """
    Översätt pixelposition på kartan till VPS-koordinat (x, z i meter).
    
    Används för att placera produkter: personal trycker på kartan → VPS-koordinat.
    """
    kal = ladda_kalibrering(butik_id)
    if kal is None:
        return None
    
    M = np.array(kal["matris"], dtype=np.float32)
    pix_pt = np.array([[[float(pixel_x), float(pixel_y)]]], dtype=np.float32)
    
    if kal["transform_type"] == "affine":
        # Invertera affine-matrisen
        M_inv = cv2.invertAffineTransform(M)
        vps = cv2.transform(pix_pt, M_inv)[0][0]
    else:
        # Invertera homography
        M_inv = np.linalg.inv(M)
        vps = cv2.perspectiveTransform(pix_pt, M_inv)[0][0]
    
    return {
        "x": float(round(float(vps[0]), 2)),
        "z": float(round(float(vps[1]), 2)),
    }


# ─────────────────────────────────────────────
# KARTBILD
# ─────────────────────────────────────────────

def spara_kartbild(butik_id: str, bild_bytes: bytes, filnamn: str = "karta.png") -> dict:
    """Spara kartbild för en butik."""
    butik_dir = BUTIKER_DIR / butik_id
    butik_dir.mkdir(parents=True, exist_ok=True)
    
    # Bestäm filändelse från filnamnet
    suffix = Path(filnamn).suffix.lower()
    if suffix not in [".png", ".jpg", ".jpeg"]:
        suffix = ".png"
    
    bild_path = butik_dir / f"karta{suffix}"
    with open(bild_path, "wb") as f:
        f.write(bild_bytes)
    
    # Läs dimensioner för validering
    img = cv2.imdecode(np.frombuffer(bild_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        bild_path.unlink()
        return {"ok": False, "fel": "Kunde inte läsa bilden"}
    
    height, width = img.shape[:2]
    
    print(f"🖼️  Sparade kartbild för {butik_id}: {width}×{height} px")
    
    return {
        "ok": True,
        "bredd_pixlar": width,
        "höjd_pixlar": height,
        "filnamn": bild_path.name,
    }


def hämta_kartbild_path(butik_id: str) -> Optional[Path]:
    """Returnera sökväg till kartbilden, eller None om den inte finns."""
    butik_dir = BUTIKER_DIR / butik_id
    if not butik_dir.exists():
        return None
    for suffix in [".png", ".jpg", ".jpeg"]:
        p = butik_dir / f"karta{suffix}"
        if p.exists():
            return p
    return None


def butik_status(butik_id: str) -> dict:
    """Returnera status för en butik: har den kartbild och kalibrering?"""
    bild_path = hämta_kartbild_path(butik_id)
    kal = ladda_kalibrering(butik_id)
    
    status = {
        "butik_id": butik_id,
        "har_kartbild": bild_path is not None,
        "har_kalibrering": kal is not None,
    }
    
    if bild_path:
        img = cv2.imread(str(bild_path))
        if img is not None:
            status["kartbild"] = {
                "bredd": img.shape[1],
                "höjd": img.shape[0],
                "filnamn": bild_path.name,
            }
    
    if kal:
        status["kalibrering"] = {
            "transform_type": kal.get("transform_type"),
            "antal_punkter": len(kal.get("referenspunkter", [])),
            "kvalitet": kal.get("kvalitet", {}),
        }
    
    return status


def lista_butiker() -> list:
    """Lista alla konfigurerade butiker."""
    if not BUTIKER_DIR.exists():
        return []
    return [
        butik_status(d.name)
        for d in BUTIKER_DIR.iterdir()
        if d.is_dir()
    ]


# ─────────────────────────────────────────────
# CLI TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    print("🧪 Testar kalibreringsmodul...")
    
    # Test: spara en exempel-kalibrering
    test_punkter = [
        {"vps": [0.0, 0.0],  "pixel": [100, 500], "beskrivning": "entré"},
        {"vps": [10.0, 0.0], "pixel": [600, 500], "beskrivning": "kassa"},
        {"vps": [0.0, 8.0],  "pixel": [100, 100], "beskrivning": "chark"},
    ]
    
    resultat = spara_kalibrering("test_butik", test_punkter)
    print(f"\nSpara-resultat: {resultat}")
    
    # Test: översätt VPS-koordinat
    test_vps_x, test_vps_z = 5.0, 4.0
    pixel = vps_till_pixel("test_butik", test_vps_x, test_vps_z)
    print(f"\nVPS ({test_vps_x}, {test_vps_z}) → pixel {pixel}")
    
    # Test: invers
    if pixel:
        vps_igen = pixel_till_vps("test_butik", pixel["pixel_x"], pixel["pixel_y"])
        print(f"Pixel {pixel} → VPS {vps_igen}")
    
    # Test: status
    print(f"\nButik-status: {butik_status('test_butik')}")
    
    # Städa upp test-data
    import shutil
    test_dir = BUTIKER_DIR / "test_butik"
    if test_dir.exists():
        shutil.rmtree(test_dir)
        print("\n🧹 Test-data rensad")
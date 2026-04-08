"""
bygg_clip_index.py  –  Bygger CLIP-vektorindex för alla produktbilder
─────────────────────────────────────────────────────────────────────
Konverterar varje produktbild till en 512-dimensionell vektor.
Sparar indexet som en .npz-fil för snabb sökning vid scanning.

Kör:
    python bygg_clip_index.py
"""

import os
import clip
import torch
import numpy as np
import cv2
from pathlib import Path
from PIL import Image

BILD_MAPP   = "bilder"           # Originalbilder (inte augmenterade)
INDEX_FIL   = "clip_index.npz"   # Sparad vektorindex
BATCH_STORLEK = 64               # Antal bilder per GPU-batch

print("🚀 Laddar CLIP-modell...")
device = "cuda" if torch.cuda.is_available() else "cpu"
modell, preprocess = clip.load("ViT-B/32", device=device)
print(f"   ✅ CLIP laddad på {device}\n")

def bild_till_vektor(bildpath: str) -> np.ndarray | None:
    """Konverterar en bild till en 512-dimensionell CLIP-vektor."""
    try:
        img = Image.open(bildpath).convert("RGB")
        tensor = preprocess(img).unsqueeze(0).to(device)
        with torch.no_grad():
            vektor = modell.encode_image(tensor)
            vektor = vektor / vektor.norm(dim=-1, keepdim=True)  # normalisera
        return vektor.cpu().numpy()[0]
    except Exception as e:
        print(f"   ⚠️  {bildpath}: {e}")
        return None

def bygg_index():
    bilder = list(Path(BILD_MAPP).glob("*.jpg"))
    print(f"🖼️  {len(bilder)} bilder att indexera")

    vektorer  = []
    produkt_ids = []

    for i, bild_path in enumerate(bilder):
        prod_id = bild_path.stem
        vektor  = bild_till_vektor(str(bild_path))

        if vektor is not None:
            vektorer.append(vektor)
            produkt_ids.append(prod_id)

        if i % 500 == 0:
            print(f"   {i}/{len(bilder)} indexerade...")

    # Spara som numpy-array
    vektorer_array = np.array(vektorer, dtype=np.float32)
    ids_array      = np.array(produkt_ids)

    np.savez(
        INDEX_FIL,
        vektorer=vektorer_array,
        ids=ids_array
    )

    print(f"\n✅ Index byggt!")
    print(f"   {len(vektorer)} produkter indexerade")
    print(f"   Sparad som {INDEX_FIL}")
    print(f"   Storlek: {vektorer_array.nbytes / 1024 / 1024:.1f} MB")

if __name__ == "__main__":
    bygg_index()
"""
augmentera_bilder.py  –  Genererar 50 varianter per produktbild
─────────────────────────────────────────────────────────────────
Varje bild får variationer av:
  - Ljusstyrka och kontrast (simulerar olika butiksbelysning)
  - Rotation och perspektiv (simulerar olika kameravinklar)
  - Brus och skärpa (simulerar olika kamerakvalitet)
  - Färgförskjutning (simulerar olika vitbalans)
"""

import os
import cv2
import numpy as np
import albumentations as A
from pathlib import Path

BILD_MAPP      = "bilder"
AUGMENT_MAPP   = "bilder_augmenterade"
VARIANTER       = 50  # antal varianter per bild

# ─────────────────────────────────────────────
# AUGMENTERINGSPIPELINE
# ─────────────────────────────────────────────

pipeline = A.Compose([
    A.RandomBrightnessContrast(
        brightness_limit=0.3,
        contrast_limit=0.3,
        p=0.8
    ),
    A.HueSaturationValue(
        hue_shift_limit=10,
        sat_shift_limit=20,
        val_shift_limit=20,
        p=0.5
    ),
    A.ColorJitter(
        brightness=0.2,
        contrast=0.2,
        saturation=0.2,
        hue=0.05,
        p=0.5
    ),
    A.Affine(
        scale=(0.9, 1.1),
        translate_percent=0.05,
        rotate=(-15, 15),
        p=0.7
    ),
    A.Perspective(
        scale=(0.02, 0.08),
        p=0.4
    ),
    A.OneOf([
        A.GaussianBlur(blur_limit=(3, 5), p=1.0),
        A.MotionBlur(blur_limit=5, p=1.0),
        A.Sharpen(alpha=(0.1, 0.3), p=1.0),
    ], p=0.4),
    A.GaussNoise(p=0.3),
    A.RandomResizedCrop(
        size=(300, 300),
        scale=(0.8, 1.0),
        ratio=(0.9, 1.1),
        p=0.5
    ),
])
# ─────────────────────────────────────────────
# HUVUDFUNKTION
# ─────────────────────────────────────────────

def augmentera_alla():
    bilder = list(Path(BILD_MAPP).glob("*.jpg"))
    print(f"🖼️  {len(bilder)} originalbilder hittade")
    print(f"📦 Genererar {VARIANTER} varianter per bild")
    print(f"   Totalt: {len(bilder) * VARIANTER} bilder\n")

    os.makedirs(AUGMENT_MAPP, exist_ok=True)

    for i, bild_path in enumerate(bilder):
        prod_id = bild_path.stem
        img     = cv2.imread(str(bild_path))

        if img is None:
            continue

        # Skala till 300x300 om den inte redan är det
        img = cv2.resize(img, (300, 300))

        # Kopiera originalet
        dest = os.path.join(AUGMENT_MAPP, f"{prod_id}_0.jpg")
        cv2.imwrite(dest, img)

        # Generera varianter
        for v in range(1, VARIANTER):
            augmenterad = pipeline(image=img)["image"]
            dest        = os.path.join(AUGMENT_MAPP, f"{prod_id}_{v}.jpg")
            cv2.imwrite(dest, augmenterad)

        if i % 100 == 0:
            print(f"   {i}/{len(bilder)} produkter augmenterade "
                  f"({i * VARIANTER} bilder genererade)")

    totalt = len(list(Path(AUGMENT_MAPP).glob("*.jpg")))
    print(f"\n✅ Klar! {totalt} bilder i {AUGMENT_MAPP}/")

if __name__ == "__main__":
    augmentera_alla()
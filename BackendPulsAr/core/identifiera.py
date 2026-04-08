"""
identifiera.py  –  Gemensam produktidentifiering för Puls-AR
─────────────────────────────────────────────────────────────────
Används av både scanner.py och analysera_skanning i server.py.

Pipeline:
  1. Qwen läser text på förpackningen
  2. CLIP matchar visuellt utseende mot produktdatabasen
  3. Kombinera — om båda är överens → hög säkerhet
                  om bara CLIP → medium säkerhet
                  om bara Qwen + CLIP bekräftar → medium
                  om Qwen hittar något CLIP inte känner igen → kasta bort

Returnerar alltid ett kanoniskt namn från ICA-databasen
eller None om ingen säker match hittades.
"""

import cv2
import numpy as np
from rapidfuzz import fuzz, utils

from core.clip_sok import clip_matcha
from core.qwen import fråga_qwen_vllm
from core.produktdb import slå_upp_produkt

# ─────────────────────────────────────────────
# TRÖSKLAR
# ─────────────────────────────────────────────

CLIP_HÖG_SÄKERHET    = 0.88  # CLIP är mycket säker
CLIP_MEDIUM_SÄKERHET = 0.83  # CLIP är ganska säker
CLIP_LÄGSTA          = 0.80  # Under detta → kasta bort
QWEN_CLIP_MATCH      = 55    # Hur likt Qwen och CLIP måste vara


def identifiera_produkt(img: np.ndarray, ruta_nr: int = 0) -> dict | None:
    """
    Pipeline:
      1. Qwen läser text på förpackningen
      2. Fuzzy-match mot ICA-databasen
      3. CLIP matchar visuellt för verifiering/boost
      4. Kombinera — om båda är överens → hög säkerhet
    """
    # Steg 1: Qwen läser texten
    qwen_svar = fråga_qwen_vllm(img, ruta_nr)
    if not qwen_svar or "OKÄND" in qwen_svar.upper():
        return None

    qwen_namn = qwen_svar.strip().split("\n")[0]

    # Steg 2: Fuzzy-match mot ICA-databasen
    match = slå_upp_produkt(qwen_namn)

    if not match or match.get("score", 0) < 65:
        return None

    kanoniskt = match["kanoniskt_namn"]

    # Steg 3: CLIP visuell verifiering
    clip_likhet = 0.0
    säkerhet    = "låg"

    try:
        clip_resultat = clip_matcha(img, topp=3)
        if clip_resultat:
            bästa_clip = clip_resultat[0]
            clip_likhet = bästa_clip.get("likhet", 0.0)

            # Kolla om CLIP:s bästa match stämmer med Qwen
            clip_namn = bästa_clip.get("visningsnamn", "")
            qwen_clip_likhet = fuzz.token_set_ratio(
                kanoniskt.lower(), clip_namn.lower()
            )

            if clip_likhet >= CLIP_HÖG_SÄKERHET and qwen_clip_likhet >= QWEN_CLIP_MATCH:
                # Båda överens med hög CLIP-likhet → hög säkerhet
                säkerhet = "hög"
            elif clip_likhet >= CLIP_MEDIUM_SÄKERHET:
                if qwen_clip_likhet >= QWEN_CLIP_MATCH:
                    säkerhet = "hög"
                else:
                    # CLIP ser något men Qwen säger annat — lita på Qwen text
                    säkerhet = "medium"
            elif clip_likhet >= CLIP_LÄGSTA:
                säkerhet = "medium"
            else:
                # CLIP ser inget som liknar — men Qwen hittade text
                säkerhet = "låg"
    except Exception as e:
        # CLIP inte tillgänglig — fortsätt utan
        print(f"   ⚠️  CLIP-fel (ruta {ruta_nr}): {e}")
        säkerhet = "medium"  # Qwen-only, okänd visuell match

    # Om fuzzy score var hög nog utan CLIP, bumpa till minst medium
    if match.get("score", 0) >= 90 and säkerhet == "låg":
        säkerhet = "medium"

    return _bygg_resultat(
        kanoniskt=kanoniskt,
        clip_info=match,
        säkerhet=säkerhet,
        clip_likhet=clip_likhet,
        qwen_namn=qwen_namn,
    )


def _bygg_resultat(kanoniskt: str, clip_info: dict,
                   säkerhet: str, clip_likhet: float,
                   qwen_namn: str | None) -> dict:
    """Bygger returvärdet."""
    return {
        "visningsnamn": kanoniskt,
        "varumarke":    clip_info.get("varumarke", ""),
        "kategori":     clip_info.get("kategori", ""),
        "säkerhet":     säkerhet,
        "clip_likhet":  clip_likhet,
        "qwen_svar":    qwen_namn or "",
    }
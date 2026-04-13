"""
kombinerar två AI-modeller för att identifiera produkter.
Qwen läser texten, CLIP matchar visuellt utseende mot produktdatabasen.
"""

import cv2
import numpy as np
from rapidfuzz import fuzz, utils

# from core.clip_sok import clip_matcha
from core.qwen import fråga_qwen_vllm
from core.produktdb import slå_upp_produkt

CLIP_HÖG_SÄKERHET    = 0.88
CLIP_MEDIUM_SÄKERHET = 0.83
CLIP_LÄGSTA          = 0.80
QWEN_CLIP_MATCH      = 55


def identifiera_produkt(img: np.ndarray, ruta_nr: int = 0) -> dict | None:
    qwen_svar = fråga_qwen_vllm(img, ruta_nr)
    if not qwen_svar or "OKÄND" in qwen_svar.upper():
        return None

    qwen_namn = qwen_svar.strip().split("\n")[0]

    match = slå_upp_produkt(qwen_namn)

    if not match or match.get("score", 0) < 78:
        return None

    return {
        "visningsnamn": match["kanoniskt_namn"],
        "varumarke":    match.get("varumarke", ""),
        "kategori":     match.get("kategori", ""),
        "säkerhet":     "medium",
        "clip_likhet":  0.0,
        "qwen_svar":    qwen_namn,
    }


def _bygg_resultat(kanoniskt: str, clip_info: dict,
                   säkerhet: str, clip_likhet: float,
                   qwen_namn: str | None) -> dict:
    return {
        "visningsnamn": kanoniskt,
        "varumarke":    clip_info.get("varumarke", ""),
        "kategori":     clip_info.get("kategori", ""),
        "säkerhet":     säkerhet,
        "clip_likhet":  clip_likhet,
        "qwen_svar":    qwen_namn or "",
    }

"""
matratt_bilder_ai.py - generera aptitliga matfoton med Nano Banana
─────────────────────────────────────────────────────────────────
Nano Banana = Googles bildmodell `gemini-2.5-flash-image`. Vi genererar EN
snygg, konsekvent maträttsbild per rätt, sparar den som PNG under
`static/matratter/` och returnerar en absolut URL som appen kan ladda direkt.

Detta görs i den veckovisa precache-batchen (offline) — INTE live — eftersom
bildgenerering tar någon sekund. Live-flödet faller tillbaka på Pexels.

Krav:
  - `pip install google-genai`
  - GEMINI_API_KEY i miljön (lägg i ~/.bashrc som PEXELS_API_KEY).
  - PUBLIC_BASE_URL om servern nås på annat än standard-VPS:en.

Saknas nyckel/paket eller misslyckas anropet → returneras None och anroparen
behåller Pexels-bilden. Bilder cachas på prompt-hash så identiska rätter inte
genereras om.
"""

import hashlib
import os
from pathlib import Path

MODELL = "gemini-2.5-flash-image"  # "Nano Banana"

_BILD_DIR = Path(__file__).resolve().parent.parent / "static" / "matratter"
_BAS_URL = os.environ.get("PUBLIC_BASE_URL", "http://100.84.130.65:8000").rstrip("/")

_client = None


def _hämta_client():
    """Lat-initiera Gemini-klienten. None om paket/nyckel saknas."""
    global _client
    if _client is not None:
        return _client
    nyckel = os.environ.get("GEMINI_API_KEY")
    if not nyckel:
        return None
    try:
        from google import genai
        _client = genai.Client(api_key=nyckel)
    except Exception:
        return None
    return _client


def _prompt(namn: str, beskrivning: str) -> str:
    return (
        f"Professionellt, aptitligt matfotografi av rätten '{namn}'. "
        f"{beskrivning}. Serverad och vackert anrättad på en tallrik, fotad "
        "ovanifrån i naturligt ljus med grunt skärpedjup. Realistiskt, "
        "fräscht, restaurangkvalitet. Ingen text, inga logotyper, inga händer."
    )


def generera_matbild(namn: str, beskrivning: str = "") -> str | None:
    """Generera (eller återanvänd) en Nano Banana-bild för rätten → absolut URL."""
    namn = (namn or "").strip()
    if not namn:
        return None

    prompt = _prompt(namn, beskrivning)
    filnamn = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:16] + ".png"
    fil = _BILD_DIR / filnamn
    url = f"{_BAS_URL}/static/matratter/{filnamn}"

    # Redan genererad → återanvänd direkt (gratis, idempotent batch).
    if fil.exists():
        return url

    client = _hämta_client()
    if client is None:
        return None

    try:
        svar = client.models.generate_content(model=MODELL, contents=[prompt])
        bild_bytes = None
        for del_ in svar.candidates[0].content.parts:
            data = getattr(del_, "inline_data", None)
            if data and data.data:
                bild_bytes = data.data
                break
        if not bild_bytes:
            return None
        _BILD_DIR.mkdir(parents=True, exist_ok=True)
        fil.write_bytes(bild_bytes)
        return url
    except Exception:
        return None

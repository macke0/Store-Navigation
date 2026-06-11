"""
matratt_bilder.py - hämta riktigt matfoto för en rätt via Pexels
─────────────────────────────────────────────────────────────────
Pexels-licensen tillåter kommersiell användning utan attribution, så vi kan
visa fotona i appen. Vi söker på rättens namn (med ingrediens som fallback)
och cachar URL:en i minnet så vi inte gör om samma anrop.

Kräver PEXELS_API_KEY i miljön. Saknas nyckeln eller hittas inget foto
returneras None → anroparen faller tillbaka på ingrediensbilden.
"""

import json
import os
import urllib.parse
import urllib.request

PEXELS_URL = "https://api.pexels.com/v1/search"

# Cacha både träffar (URL) och missar ("") så vi inte upprepar nätanrop.
_cache: dict[str, str] = {}


def hämta_matbild(fråga: str) -> str | None:
    """Returnera URL till ett matfoto för `fråga`, eller None."""
    nyckel = (fråga or "").strip().lower()
    if not nyckel:
        return None
    if nyckel in _cache:
        return _cache[nyckel] or None

    api_nyckel = os.environ.get("PEXELS_API_KEY")
    if not api_nyckel:
        return None

    params = urllib.parse.urlencode({
        "query": fråga,
        "per_page": 1,
        "orientation": "landscape",
    })
    req = urllib.request.Request(
        f"{PEXELS_URL}?{params}",
        # Cloudflare framför Pexels blockar urllibs standard-User-Agent
        # (svarar 403 "error code: 1010"). Skicka en vanlig webbläsar-UA.
        headers={"Authorization": api_nyckel, "User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
    except Exception:
        return None

    foton = data.get("photos") or []
    src = (foton[0].get("src") if foton else {}) or {}
    url = src.get("large") or src.get("medium") or ""
    _cache[nyckel] = url
    return url or None

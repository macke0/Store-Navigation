"""
matratt_bilder.py - hämta riktigt matfoto för en rätt via Pexels
─────────────────────────────────────────────────────────────────
Pexels-licensen tillåter kommersiell användning utan attribution, så vi kan
visa fotona i appen. Vi söker på rättens namn (med ingrediens som fallback)
och cachar träfflistan i minnet så vi inte gör om samma anrop.

Två knep mot vanliga fel: (1) vi lägger till "mat" i frågan så svenska rättnamn
inte matchar landskaps-/skogsfoton, och (2) vi hämtar flera träffar och låter
anroparen välja via `index` så att snarlika rätter inte får exakt samma bild.

Kräver PEXELS_API_KEY i miljön. Saknas nyckeln eller hittas inget foto
returneras None → anroparen faller tillbaka på ingrediensbilden.
"""

import json
import os
import urllib.parse
import urllib.request

PEXELS_URL = "https://api.pexels.com/v1/search"

# Cacha träfflistan (URL:er) per fråga; tom lista = miss, så vi inte upprepar nätanrop.
_cache: dict[str, list[str]] = {}


def _hämta_urls(fråga: str) -> list[str]:
    """Hämta en lista matfoto-URL:er för `fråga` (cachad). Tom lista vid miss."""
    nyckel = fråga.strip().lower()
    if nyckel in _cache:
        return _cache[nyckel]

    api_nyckel = os.environ.get("PEXELS_API_KEY")
    if not api_nyckel:
        return []

    params = urllib.parse.urlencode({
        # "mat" styr Pexels mot riktiga maträtter i stället för t.ex. skog/landskap
        # som svenska rättnamn annars kan matcha.
        "query": f"{fråga} mat",
        "per_page": 15,
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
        return []

    urls = []
    for foto in data.get("photos") or []:
        src = foto.get("src") or {}
        url = src.get("large") or src.get("medium")
        if url:
            urls.append(url)
    _cache[nyckel] = urls
    return urls


def hämta_matbild(fråga: str, index: int = 0) -> str | None:
    """Returnera URL till ett matfoto för `fråga`, eller None.

    `index` plockar olika bild ur träfflistan så att snarlika rätter
    (t.ex. grillad vs stekt kyckling) inte får exakt samma foto.
    """
    if not (fråga or "").strip():
        return None
    urls = _hämta_urls(fråga)
    if not urls:
        return None
    return urls[index % len(urls)]

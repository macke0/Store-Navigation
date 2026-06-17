"""
ica_recept_scraper.py  –  Puls-AR ICA recepthämtare
─────────────────────────────────────────────────────────────────
Skrapar ALLA recept från ica.se/recept (~23 000 st) utan inloggning.

Receptsidorna är publika och bär en JSON-LD-blob
(<script type="application/ld+json"> med @type: Recipe) som innehåller
namn, ingredienser, instruktioner, portioner, NÄRINGSVÄRDE (kcal/fett/
kolhydrater/protein/salt), bild och betyg. Vi enumererar alla recept-URL:er
via sitemap-indexet och parsar JSON-LD per sida.

Kör:
    python ica_recept_scraper.py                 # alla recept, hotlinkar bilder
    python ica_recept_scraper.py --max 50        # testkörning
    python ica_recept_scraper.py --ladda-bilder  # speglar bilder lokalt också
    python ica_recept_scraper.py --konsolidera   # JSONL → data/ica_recept.json

Resultatet är resumebart: redan skrapade recept hoppas över (recept.jsonl).
Bilder hotlinkas som standard (assets.icanet.se) → noll lagring. ICA äger
bilderna och vi säljer till ICA, så hotlink är ok; --ladda-bilder speglar
dem till BackendPulsAr/static/recept/ för servering från egen VPS.
"""

import argparse
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

# ─────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────
BAS               = "https://www.ica.se"
SITEMAP_INDEX     = f"{BAS}/recept/sitemaps/"
HÄR               = Path(__file__).resolve().parent
JSONL_FIL         = HÄR / "recept.jsonl"
DATA_FIL          = HÄR.parent / "data" / "ica_recept.json"
BILD_DIR          = HÄR.parent / "static" / "recept"
ARBETARE          = 8          # parallella hämtningar (var snäll mot ICA)
DELAY             = 0.05       # liten paus per arbetare
TIMEOUT           = 15

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}

_LÅS = threading.Lock()

# Kända mängd-enheter för att dela "2.5 dl vetemjöl" → mängd/enhet/namn.
_ENHETER = {
    "dl", "l", "ml", "cl", "msk", "tsk", "krm", "g", "kg", "hg",
    "st", "stycken", "port", "portioner", "klyfta", "klyftor",
    "burk", "burkar", "pkt", "paket", "påse", "påsar", "näve", "nävar",
    "nypa", "nypor", "skiva", "skivor", "kruka", "knippe", "ask",
}


# ─────────────────────────────────────────────
# ENUMERERA RECEPT-URL:ER VIA SITEMAP
# ─────────────────────────────────────────────

def _hämta_text(url: str) -> str | None:
    for _ in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.text
            if r.status_code in (429, 503):
                time.sleep(2)
                continue
            return None
        except Exception:
            time.sleep(1)
    return None


def hämta_recept_urls() -> list[str]:
    """Sitemap-index → barn-sitemaps → alla recept-URL:er."""
    index = _hämta_text(SITEMAP_INDEX)
    if not index:
        print("❌ Kunde inte hämta sitemap-indexet")
        return []

    barn = re.findall(r"<loc>\s*(.*?)\s*</loc>", index)
    # Barn-sitemaps är de numrerade (/recept/sitemaps/3), inte indexpages.
    barn = [b for b in barn if re.search(r"/recept/sitemaps/\d+$", b)]
    print(f"🗺️  {len(barn)} barn-sitemaps i indexet")

    urls: set[str] = set()
    for i, sm in enumerate(barn, 1):
        txt = _hämta_text(sm)
        if not txt:
            continue
        for loc in re.findall(r"<loc>\s*(.*?)\s*</loc>", txt):
            # Receptsidor ser ut som /recept/<slug>-<id>/
            if re.search(r"/recept/[^/]+-\d+/?$", loc):
                urls.add(loc)
        print(f"   sitemap {i}/{len(barn)} → totalt {len(urls)} recept-URL:er", end="\r")
    print()
    return sorted(urls)


# ─────────────────────────────────────────────
# PARSA ETT RECEPT (JSON-LD)
# ─────────────────────────────────────────────

def _recept_id(url: str) -> str:
    m = re.search(r"-(\d+)/?$", url)
    return m.group(1) if m else url.rstrip("/").rsplit("/", 1)[-1]


def _första_tal(text: str) -> float | None:
    """'281 kcal' → 281.0, '1,2 g' → 1.2."""
    m = re.search(r"\d+(?:[.,]\d+)?", text or "")
    return float(m.group(0).replace(",", ".")) if m else None


def _parsa_ingrediens(text: str) -> dict:
    """'2 1/2 dl vetemjöl' → {text, mangd:'2 1/2', enhet:'dl', namn:'vetemjöl'}."""
    text = (text or "").strip()
    tokens = text.split()
    i = 0
    mangd_delar = []
    # Konsumera alla inledande tal-/bråk-tokens (t.ex. "2 1/2").
    while i < len(tokens) and re.match(r"^[\d.,/½¼¾-]+$", tokens[i]):
        mangd_delar.append(tokens[i])
        i += 1
    enhet = ""
    if i < len(tokens) and tokens[i].lower().rstrip(".") in _ENHETER:
        enhet = tokens[i]
        i += 1
    namn = " ".join(tokens[i:]).strip()
    if not namn:               # ovanligt: hela strängen var mängd/enhet
        namn = text
    return {"text": text, "mangd": " ".join(mangd_delar), "enhet": enhet, "namn": namn}


def _hitta_recept_objekt(data) -> dict | None:
    """JSON-LD kan vara dict, lista eller {"@graph": [...]}. Hitta @type Recipe."""
    if isinstance(data, list):
        for d in data:
            träff = _hitta_recept_objekt(d)
            if träff:
                return träff
        return None
    if isinstance(data, dict):
        if "@graph" in data:
            return _hitta_recept_objekt(data["@graph"])
        typ = data.get("@type")
        if typ == "Recipe" or (isinstance(typ, list) and "Recipe" in typ):
            return data
    return None


def _bild_url(bild) -> str:
    if isinstance(bild, str):
        return bild
    if isinstance(bild, list) and bild:
        return _bild_url(bild[0])
    if isinstance(bild, dict):
        return bild.get("url") or bild.get("@id") or ""
    return ""


def _instruktioner(instr) -> list[str]:
    steg = []
    if isinstance(instr, str):
        return [instr.strip()] if instr.strip() else []
    if isinstance(instr, list):
        for s in instr:
            if isinstance(s, str):
                steg.append(s.strip())
            elif isinstance(s, dict):
                t = s.get("text") or s.get("name") or ""
                if t.strip():
                    steg.append(t.strip())
    return steg


def parsa_recept(url: str) -> dict | None:
    html = _hämta_text(url)
    if not html:
        return None

    objekt = None
    for block in re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    ):
        try:
            objekt = _hitta_recept_objekt(json.loads(block.strip()))
        except Exception:
            continue
        if objekt:
            break
    if not objekt:
        return None

    näring_rå = objekt.get("nutrition") or {}
    näring = {
        "kcal": _första_tal(näring_rå.get("calories")),
        "fett": _första_tal(näring_rå.get("fatContent")),
        "kolhydrater": _första_tal(näring_rå.get("carbohydrateContent")),
        "protein": _första_tal(näring_rå.get("proteinContent")),
        "salt": _första_tal(näring_rå.get("sodiumContent") or näring_rå.get("saltContent")),
    }

    ingredienser = [_parsa_ingrediens(i) for i in (objekt.get("recipeIngredient") or [])]

    betyg_rå = objekt.get("aggregateRating") or {}
    kategorier = objekt.get("recipeCategory") or []
    if isinstance(kategorier, str):
        kategorier = [kategorier]
    nyckelord = objekt.get("keywords") or ""
    if isinstance(nyckelord, list):
        nyckelord = ", ".join(nyckelord)

    namn = (objekt.get("name") or "").strip()
    # Söktaggar: namn + kategorier + nyckelord + ingrediensnamn (gemener).
    taggar = " ".join(filter(None, [
        namn.lower(),
        " ".join(kategorier).lower(),
        str(nyckelord).lower(),
        " ".join(i["namn"] for i in ingredienser).lower(),
    ]))

    return {
        "id": _recept_id(url),
        "url": url,
        "namn": namn,
        "beskrivning": (objekt.get("description") or "").strip(),
        "bild_url": _bild_url(objekt.get("image")),
        "bild_lokal": "",
        "portioner": _första_tal(str(objekt.get("recipeYield") or "")),
        "tid": objekt.get("totalTime") or objekt.get("cookTime") or "",
        "betyg": _första_tal(str(betyg_rå.get("ratingValue") or "")),
        "antal_betyg": int(_första_tal(str(betyg_rå.get("ratingCount") or "")) or 0),
        "kategorier": kategorier,
        "nyckelord": nyckelord,
        "ingredienser": ingredienser,
        "instruktioner": _instruktioner(objekt.get("recipeInstructions")),
        "naring": näring,
        "taggar": taggar,
    }


# ─────────────────────────────────────────────
# BILDER (valfritt — speglar lokalt)
# ─────────────────────────────────────────────

def ladda_ner_bild(url: str, recept_id: str) -> str:
    if not url:
        return ""
    BILD_DIR.mkdir(parents=True, exist_ok=True)
    fil = BILD_DIR / f"{recept_id}.jpg"
    if fil.exists():
        return f"/static/recept/{recept_id}.jpg"
    try:
        r = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=TIMEOUT)
        if r.status_code == 200:
            fil.write_bytes(r.content)
            return f"/static/recept/{recept_id}.jpg"
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────
# IO (resumebart via JSONL)
# ─────────────────────────────────────────────

def _redan_klara() -> set[str]:
    klara: set[str] = set()
    if JSONL_FIL.exists():
        with open(JSONL_FIL, encoding="utf-8") as f:
            for rad in f:
                try:
                    klara.add(json.loads(rad)["id"])
                except Exception:
                    continue
    return klara


def _spara_rad(recept: dict):
    with _LÅS:
        with open(JSONL_FIL, "a", encoding="utf-8") as f:
            f.write(json.dumps(recept, ensure_ascii=False) + "\n")


def konsolidera():
    """JSONL → data/ica_recept.json (en lista, dubblettfri på id)."""
    if not JSONL_FIL.exists():
        print("❌ Ingen recept.jsonl att konsolidera")
        return
    sett: dict[str, dict] = {}
    with open(JSONL_FIL, encoding="utf-8") as f:
        for rad in f:
            try:
                r = json.loads(rad)
                sett[r["id"]] = r
            except Exception:
                continue
    recept = list(sett.values())
    DATA_FIL.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FIL, "w", encoding="utf-8") as f:
        json.dump(recept, f, ensure_ascii=False)
    print(f"✅ {len(recept)} recept → {DATA_FIL}")


# ─────────────────────────────────────────────
# HUVUD
# ─────────────────────────────────────────────

def scrapa(max_recept: int | None, ladda_bilder: bool):
    urls = hämta_recept_urls()
    if not urls:
        return
    klara = _redan_klara()
    kvar = [u for u in urls if _recept_id(u) not in klara]
    if max_recept:
        kvar = kvar[:max_recept]
    print(f"📋 {len(urls)} recept totalt, {len(klara)} redan klara, hämtar {len(kvar)}\n")

    def jobb(url: str) -> bool:
        time.sleep(DELAY)
        recept = parsa_recept(url)
        if not recept or not recept["namn"]:
            return False
        if ladda_bilder:
            recept["bild_lokal"] = ladda_ner_bild(recept["bild_url"], recept["id"])
        _spara_rad(recept)
        return True

    klart = 0
    with ThreadPoolExecutor(max_workers=ARBETARE) as pool:
        framtider = {pool.submit(jobb, u): u for u in kvar}
        for fut in as_completed(framtider):
            klart += 1
            if klart % 50 == 0:
                print(f"   {klart}/{len(kvar)} hämtade", end="\r")
    print(f"\n✅ Klart: {klart} recept hämtade till {JSONL_FIL.name}")
    konsolidera()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="ICA receptskrapare")
    p.add_argument("--max", type=int, default=None, help="Max antal recept (test)")
    p.add_argument("--ladda-bilder", action="store_true",
                   help="Spegla bilder lokalt till static/recept/ (annars hotlink)")
    p.add_argument("--konsolidera", action="store_true",
                   help="Bygg bara data/ica_recept.json från recept.jsonl")
    args = p.parse_args()

    if args.konsolidera:
        konsolidera()
    else:
        scrapa(max_recept=args.max, ladda_bilder=args.ladda_bilder)

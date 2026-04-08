"""
produktdb.py  –  Puls-AR Lokal Produktdatabas
─────────────────────────────────────────────────────────────────
Läser produkter.csv och matchar Qwen-namn mot kända produkter
med fuzzy matching.
"""

import csv
import os
import json
from rapidfuzz import process, fuzz, utils

# ─────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────
CSV_FIL = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "produkter.csv")
MIN_MATCH_SCORE = 65

# ─────────────────────────────────────────────
# HJÄLPFUNKTIONER
# ─────────────────────────────────────────────

def normalisera(text: str) -> str:
    """Konverterar svenska tecken för bättre matchning."""
    return (text.lower()
        .replace("å", "a").replace("ä", "a").replace("ö", "o")
        .replace("é", "e").replace("ú", "u")
        .strip())

# ─────────────────────────────────────────────
# LADDA DATABASEN
# ─────────────────────────────────────────────

def ladda_databas() -> list[dict]:
    if not os.path.exists(CSV_FIL):
        print(f"⚠️  {CSV_FIL} hittades inte")
        return []
    produkter = []
    with open(CSV_FIL, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for rad in reader:
            produkter.append(rad)
    print(f"📦 Laddade {len(produkter)} produkter från {CSV_FIL}")
    return produkter

_databas = ladda_databas()

def bygg_sök_index(databas: list[dict]) -> list[tuple]:
    index = []
    for prod in databas:
        taggar = prod.get("taggar", "").replace(",", " ")
        sökbar = f"{prod.get('visningsnamn','')} {prod.get('varumarke','')} {taggar}"
        index.append((sökbar.lower().strip(), prod))
    return index

_sök_index = bygg_sök_index(_databas)

# Bygg varumärkeslista dynamiskt från databasen
_märken = list(set(
    normalisera(prod.get("varumarke", "").strip())
    for _, prod in _sök_index
    if prod.get("varumarke", "").strip()
))
_märken.sort(key=len, reverse=True)  # Längst först så "santa maria" matchas före "maria"

# Bygg normaliserat index en gång
_normaliserat_index = [(normalisera(s), prod) for s, prod in _sök_index]
_normaliserade_strängar = [s for s, _ in _normaliserat_index]
_vanliga_strängar = [s for s, _ in _sök_index]

# ─────────────────────────────────────────────
# SÖK-FUNKTION
# ─────────────────────────────────────────────

def slå_upp_produkt(query: str) -> dict:
    if not _sök_index:
        return _fallback(query)

    q      = query.lower().strip()
    q_norm = normalisera(q)

    # Steg 1: Exakt match mot visningsnamn
    for _, prod in _sök_index:
        if q in prod.get("visningsnamn", "").lower():
            return _bygg_resultat(prod, 100, query)

    # Steg 2: Normaliserad exakt match — löser å/ä/ö-problem
    for norm_s, prod in _normaliserat_index:
        if q_norm in norm_s:
            return _bygg_resultat(prod, 95, query)

    # Hitta varumärke i query
    query_märke = next((m for m in _märken if m in q_norm), None)

    # Steg 3: Fuzzy match normaliserad
    match_norm = process.extractOne(
        q_norm,
        _normaliserade_strängar,
        scorer=fuzz.token_set_ratio,
        processor=utils.default_process
    )

    # Steg 4: Fuzzy match original
    match_orig = process.extractOne(
        q,
        _vanliga_strängar,
        scorer=fuzz.token_set_ratio,
        processor=utils.default_process
    )

    # Välj bästa match
    bästa_prod  = None
    bästa_score = 0

    if match_norm and match_norm[1] >= MIN_MATCH_SCORE:
        idx = _normaliserade_strängar.index(match_norm[0])
        bästa_prod  = _normaliserat_index[idx][1]
        bästa_score = match_norm[1]

    if match_orig and match_orig[1] >= MIN_MATCH_SCORE and match_orig[1] > bästa_score:
        for s, prod in _sök_index:
            if s == match_orig[0]:
                bästa_prod  = prod
                bästa_score = match_orig[1]
                break

    if bästa_prod:
        prod_märke = normalisera(bästa_prod.get("varumarke", ""))

        # Om query har ett märke men produkten har fel märke → leta rätt märke
        if query_märke and query_märke not in prod_märke:
            märke_kandidater = [
                (norm_s, prod)
                for norm_s, prod in _normaliserat_index
                if query_märke in normalisera(prod.get("varumarke", ""))
            ]
            if märke_kandidater:
                märke_match = process.extractOne(
                    q_norm,
                    [s for s, _ in märke_kandidater],
                    scorer=fuzz.token_set_ratio
                )
                if märke_match and märke_match[1] >= 50:
                    for s, prod in märke_kandidater:
                        if s == märke_match[0]:
                            return _bygg_resultat(prod, märke_match[1], query)

        return _bygg_resultat(bästa_prod, bästa_score, query)

    # Steg 5: Varumärkesmatch som fallback
    if query_märke:
        for norm_s, prod in _normaliserat_index:
            if query_märke in normalisera(prod.get("varumarke", "")):
                return _bygg_resultat(prod, 40, query)

    return _fallback(query)


def _bygg_resultat(prod: dict, score: float, query: str) -> dict:
    taggar = [t.strip() for t in prod.get("taggar", "").split(",") if t.strip()]
    return {
        "kanoniskt_namn": prod.get("visningsnamn", query),
        "varumarke":      prod.get("varumarke", ""),
        "kategori":       prod.get("kategori", ""),
        "taggar":         taggar,
        "off_hittad":     True,
        "score":          round(score),
        "original_query": query,
    }

def _fallback(query: str) -> dict:
    return {
        "kanoniskt_namn": query,
        "varumarke":      "",
        "kategori":       "",
        "taggar":         [query.lower()],
        "off_hittad":     False,
        "score":          0,
        "original_query": query,
    }


if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "felix caesar"
    print(f"\n🔍 Söker: '{query}'\n")
    resultat = slå_upp_produkt(query)
    print(json.dumps(resultat, ensure_ascii=False, indent=2))
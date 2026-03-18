"""
produktdb.py  –  Puls-AR Lokal Produktdatabas
─────────────────────────────────────────────────────────────────
Läser produkter.csv och matchar Qwen-namn mot kända produkter
med fuzzy matching. Mycket snabbare och mer pålitligt än
att anropa externa API:er.

Användning:
    from produktdb import slå_upp_produkt

    resultat = slå_upp_produkt("Felix Caesar dressing")
    print(resultat["kanoniskt_namn"])   # "Felix Dressing Caesar"
    print(resultat["varumarke"])        # "Felix"
    print(resultat["kategori"])         # "Dressingar"
"""

import csv
import os
import json
from rapidfuzz import process, fuzz, utils

# ─────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────
CSV_FIL         = "produkter.csv"
MIN_MATCH_SCORE = 55    # Minsta fuzzy-score för att acceptera en match

# ─────────────────────────────────────────────
# LADDA DATABASEN
# ─────────────────────────────────────────────

def ladda_databas() -> list[dict]:
    """Läser produkter.csv och returnerar lista av produkter."""
    if not os.path.exists(CSV_FIL):
        print(f"⚠️  {CSV_FIL} hittades inte — skapa den med ica_scraper.py")
        return []

    produkter = []
    with open(CSV_FIL, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for rad in reader:
            produkter.append(rad)

    print(f"📦 Laddade {len(produkter)} produkter från {CSV_FIL}")
    return produkter

# Ladda en gång vid import
_databas = ladda_databas()

# Bygg sök-index: lista av (sökbar sträng, produkt)
# Sökbar sträng = visningsnamn + taggar + varumärke kombinerat
def bygg_sök_index(databas: list[dict]) -> list[tuple]:
    index = []
    for prod in databas:
        taggar     = prod.get("taggar", "").replace(",", " ")
        sökbar     = f"{prod.get('visningsnamn','')} {prod.get('varumarke','')} {taggar}"
        index.append((sökbar.lower().strip(), prod))
    return index

_sök_index = bygg_sök_index(_databas)


# ─────────────────────────────────────────────
# SÖK-FUNKTION
# ─────────────────────────────────────────────

def slå_upp_produkt(query: str) -> dict:
    """
    Matchar en Qwen-identifierad produktsträng mot den lokala databasen.

    Returnerar alltid ett dict:
    {
        "kanoniskt_namn": "Felix Dressing Caesar",
        "varumarke":      "Felix",
        "kategori":       "Dressingar",
        "taggar":         ["dressing", "caesar", ...],
        "off_hittad":     True,    ← True om vi hittade en match
        "score":          87,
        "original_query": "Felix Caesar"
    }
    """
    if not _sök_index:
        return _fallback(query)

    q = query.lower().strip()

    # Steg 1: Exakt/partial match mot visningsnamn (snabbast)
    for _, prod in _sök_index:
        if q in prod.get("visningsnamn", "").lower():
            return _bygg_resultat(prod, 100, query)

    
   # Steg 2: Fuzzy match — men kräv varumärkesmatch om varumärke finns i query
    märken = ["felix", "kavli", "heinz", "tabasco", "tiger", "bob", "hp"]
    query_märke = next((m for m in märken if m in q), None)

    bara_strängar = [s for s, _ in _sök_index]
    match = process.extractOne(
        q,
        bara_strängar,
        scorer=fuzz.token_set_ratio,
        processor=utils.default_process
    )

    if match and match[1] >= MIN_MATCH_SCORE:
        matchad_sträng = match[0]
        # Om query innehåller ett märke, acceptera bara träffar med samma märke
        for sök_str, prod in _sök_index:
            if sök_str == matchad_sträng:
                if query_märke and query_märke not in prod.get("varumarke","").lower():
                    break  # fel märke — använd fallback
                return _bygg_resultat(prod, match[1], query)

    # Steg 3: Varumärkesmatch som fallback
    for _, prod in _sök_index:
        märke = prod.get("varumarke", "").lower()
        if märke and märke in q:
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


# ─────────────────────────────────────────────
# TESTA MANUELLT
# python produktdb.py "caesar dressing"
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "felix caesar"
    print(f"\n🔍 Söker: '{query}'\n")
    resultat = slå_upp_produkt(query)
    print(json.dumps(resultat, ensure_ascii=False, indent=2))
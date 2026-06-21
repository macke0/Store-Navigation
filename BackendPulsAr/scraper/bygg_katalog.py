"""
bygg_katalog.py  –  Bygg sökkatalogen från scraper-CSV:n
─────────────────────────────────────────────────────────────────
Läser scraper/produkter.csv och skriver data/ica_produkter.json
(det format ProduktSök/claude_assistant läser). Bär nu med pris,
kampanjpris och kampanjtext så att assistenten kan svara på pris
och veckans erbjudanden.

Kör från BackendPulsAr/:
    python scraper/bygg_katalog.py
"""

import csv
import json
import os

CSV_FIL  = os.path.join(os.path.dirname(__file__), "produkter.csv")
JSON_FIL = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                        "data", "ica_produkter.json")


def bygg():
    if not os.path.exists(CSV_FIL):
        print(f"❌ Hittar inte {CSV_FIL} — kör ica_scraper.py först")
        return

    with open(CSV_FIL, encoding="utf-8") as f:
        rader = list(csv.DictReader(f))

    produkter = []
    for r in rader:
        produkter.append({
            "id":          r.get("id", ""),
            "namn":        r.get("visningsnamn", ""),
            "varumarke":   r.get("varumarke", ""),
            "kategori":    r.get("kategori", ""),
            "avdelning":   r.get("avdelning", ""),
            "pris":        r.get("pris", ""),
            "enhetspris":  r.get("enhetspris", ""),
            "kampanjpris": r.get("kampanjpris", ""),
            "kampanjtext": r.get("kampanjtext", ""),
            "bild_url":    r.get("bild_url", ""),
            "taggar":      r.get("taggar", ""),
        })

    os.makedirs(os.path.dirname(JSON_FIL), exist_ok=True)
    with open(JSON_FIL, "w", encoding="utf-8") as f:
        json.dump(produkter, f, ensure_ascii=False, indent=2)

    med_pris   = sum(1 for p in produkter if p["pris"])
    med_kampanj = sum(1 for p in produkter if p["kampanjpris"])
    print(f"✅ {len(produkter)} produkter → {JSON_FIL}")
    print(f"   {med_pris} med pris, {med_kampanj} med kampanj")


if __name__ == "__main__":
    bygg()

"""
produkt_lista.py — Lättvikts-endpoint för att skicka produktlistan till iOS-appen.
Appen laddar ner listan en gång vid start och söker lokalt.
"""

from fastapi import APIRouter
import csv
import os
import json

router = APIRouter(tags=["Produktlista"])

# Ladda produkter en gång
_produkter_cache = None

def _ladda_produkter():
    global _produkter_cache
    if _produkter_cache is not None:
        return _produkter_cache
    
    csv_fil = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "produkter.csv")
    if not os.path.exists(csv_fil):
        # Fallback: prova ica_produkter.json
        json_fil = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "ica_produkter.json")
        if os.path.exists(json_fil):
            with open(json_fil, 'r', encoding='utf-8') as f:
                data = json.load(f)
                _produkter_cache = [{
                    "id": p.get("id", ""),
                    "n": p.get("namn", p.get("visningsnamn", "")),
                    "v": p.get("varumarke", ""),
                    "k": p.get("kategori", ""),
                    "b": p.get("bild_url", ""),
                } for p in data]
                return _produkter_cache
        return []
    
    produkter = []
    with open(csv_fil, "r", encoding="utf-8") as f:
        for rad in csv.DictReader(f):
            # Skicka bara det appen behöver för sökning — minimalt
            produkter.append({
                "id": rad.get("id", ""),
                "n": rad.get("visningsnamn", ""),    # kort nyckel = mindre data
                "v": rad.get("varumarke", ""),
                "k": rad.get("kategori", ""),
                "b": rad.get("bild_url", ""),
            })
    
    _produkter_cache = produkter
    print(f"📦 Produktlista cachad: {len(produkter)} produkter")
    return produkter


@router.get("/produkter/lista")
def hämta_produktlista():
    """
    Returnerar alla produkter i kompakt format för lokal sökning i appen.
    Laddas en gång vid app-start (~1MB).
    """
    produkter = _ladda_produkter()
    return {
        "antal": len(produkter),
        "produkter": produkter
    }


@router.get("/produkter/version")
def produktlista_version():
    """Kollar om appen behöver uppdatera sin lokala lista."""
    produkter = _ladda_produkter()
    return {
        "antal": len(produkter),
        "version": len(produkter),  # Enkelt: antal = version
    }
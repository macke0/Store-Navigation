"""
matratt_cache.py - precache av maträttsförslag för vanliga sökningar
─────────────────────────────────────────────────────────────────
Många kunder söker samma sak (protein, kampanjer, vegetariskt, kyckling...).
I stället för att låta var och en vänta på Claude + berikning genererar vi
svaren för en uppsättning VANLIGA_FRÅGOR i förväg och serverar dem direkt
ur en JSON-fil. Det tar bort latensen för de vanligaste vägarna; ovanliga
fritextsökningar faller fortfarande igenom till live-generering.

Rätterna genereras med Haiku (samma som live). Bilderna genereras med Nano
Banana (matratt_bilder_ai) eftersom batchen körs offline och latens inte
spelar roll — live behåller Pexels.

Körs veckovis (t.ex. via cron) → cachen får nya recept varje vecka:
    python -c "from core.matratt_cache import bygg_cache; bygg_cache()"
"""

import json
import threading
import time
from pathlib import Path

from core.matratter import MODELL, foresla_matratter
from core.matratt_bilder_ai import generera_matbild

CACHE_FIL = Path(__file__).resolve().parent.parent / "data" / "matratt_cache.json"
MAX_ALDER_S = 8 * 24 * 3600  # ~en vecka + marginal innan nasta batch hinner kora

# De tre första är EXAKT appens förslagschips (MaträttView) → garanterade träffar.
# Resten täcker de vanligaste sökintentionerna.
VANLIGA_FRÅGOR = [
    "Maträtter med mycket protein som använder era kampanjer",
    "Billig vardagsmiddag för familjen",
    "Vegetariskt med dagens erbjudanden",
    "Snabb vardagsmiddag på 20 minuter",
    "Maträtter med kyckling",
    "Maträtter med lax eller fisk",
    "Veganskt med dagens kampanjer",
    "Barnvänlig middag",
    "Lyxig helgmiddag",
    "Lågkolhydrat / LCHF-middag",
    "Pastarätter",
    "Soppa eller gryta för kalla dagar",
    "Tacos och mexikansk mat",
    "Klassisk husmanskost",
    "Maträtter med köttfärs",
]

_lås = threading.Lock()


def _normalisera(fråga: str) -> str:
    return " ".join((fråga or "").lower().split())


def _läs() -> dict:
    try:
        return json.loads(CACHE_FIL.read_text("utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _skriv(cache: dict) -> None:
    CACHE_FIL.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FIL.write_text(json.dumps(cache, ensure_ascii=False, indent=2), "utf-8")


def hämta_cachad(fråga: str) -> dict | None:
    """Färsk cache-träff för frågan ({matratter: [...]}), annars None → live."""
    post = _läs().get(_normalisera(fråga))
    if not post or time.time() - post.get("ts", 0) > MAX_ALDER_S:
        return None
    return post.get("data")


def _byt_till_ai_bilder(data: dict) -> None:
    """Ersätt varje rätts Pexels-bild med en Nano Banana-bild (Pexels som fallback)."""
    for rätt in data.get("matratter", []):
        bild = generera_matbild(rätt.get("namn") or "", rätt.get("beskrivning") or "")
        if bild:
            rätt["bild_url"] = bild


def bygg_cache(model: str = MODELL, frågor: list[str] | None = None) -> None:
    """Generera och spara maträtter (+ AI-bilder) för alla vanliga frågor."""
    frågor = frågor or VANLIGA_FRÅGOR
    cache = _läs()
    for i, fråga in enumerate(frågor, 1):
        try:
            data = foresla_matratter(fråga, model=model)
        except Exception as e:
            print(f"⚠️  cache {i}/{len(frågor)}: '{fråga}' misslyckades: {e}")
            continue
        if not data.get("matratter"):
            print(f"⚠️  cache {i}/{len(frågor)}: '{fråga}' gav 0 rätter, hoppar över")
            continue
        _byt_till_ai_bilder(data)
        cache[_normalisera(fråga)] = {"ts": time.time(), "fråga": fråga, "data": data}
        # Spara löpande så ett avbrott inte tappar redan gjort arbete.
        with _lås:
            _skriv(cache)
        print(f"✅  cache {i}/{len(frågor)}: {fråga}")
    print(f"🍽️  cache klar: {len(frågor)} frågor på {model}")


if __name__ == "__main__":
    bygg_cache()

"""
matratter.py - Maträtts-/receptförslag för Puls-AR kundflöde
─────────────────────────────────────────────────────────────────
Kunden söker fritt ("maträtter med mycket protein som använder era
kampanjer just nu"). Claude komponerar maträtter; vi berikar varje
ingrediens med RIKTIGT pris/kampanj/bild/position från katalogen och
summerar total kostnad + besparing. Allt en generell AI inte vet.

Flöde:
  1. Plocka ut produkter som är på kampanj just nu (kampanjpris satt).
  2. Låt Claude föreslå maträtter (favoriserar kampanjvaror) → strikt JSON.
  3. Matcha varje ingrediens mot katalogen (sök) → pris, kampanj, bild.
  4. Summera total_pris, ordinarie_pris, besparing per maträtt.
"""

import json
import anthropic

from core.produkt_sok import get_produkt_sök
from core.produkt_skanning import läs_konsoliderade

client = anthropic.Anthropic()
MODELL = "claude-sonnet-4-20250514"


def _flyt(värde) -> float | None:
    """Tolka ett prissträngsvärde ('21.60' / '21,60') som float."""
    try:
        return float(str(värde).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _kampanjprodukter(sök, max_antal: int = 80) -> list[dict]:
    """Produkter som är på rea just nu (har kampanjpris)."""
    träffar = []
    for p in sök.produkter:
        if p.get("kampanjpris"):
            träffar.append(p)
            if len(träffar) >= max_antal:
                break
    return träffar


SYSTEM_PROMPT = """Du är en kreativ matinspiratör för ICA Maxi Bromma. Du föreslår \
maträtter utifrån vad kunden frågar efter. Du svarar ENDAST med giltig JSON, inga \
kommentarer eller markdown.

Du får en lista över varor som är PÅ KAMPANJ just nu. När det passar kundens önskemål \
ska du bygga maträtter runt dessa kampanjvaror så att kunden sparar pengar.

Returnera JSON enligt exakt detta schema:
{
  "matratter": [
    {
      "namn": "Kort aptitlig titel",
      "beskrivning": "1-2 meningar som säljer rätten",
      "portioner": 4,
      "protein_g_per_portion": 38,
      "ingredienser": [
        {"namn": "kycklingfilé", "mangd": "600 g"},
        {"namn": "broccoli", "mangd": "1 st"}
      ]
    }
  ]
}

Regler:
- 3-5 maträtter.
- Ingrediensnamn ska vara enkla sökord (t.ex. "kycklingfilé", "ris", "grädde") så att \
de går att matcha mot butikens sortiment. Undvik märkesnamn.
- protein_g_per_portion är din bästa uppskattning (heltal).
- Svara alltid på svenska. ENDAST JSON."""


def _bygg_kampanjkontext(kampanjer: list[dict]) -> str:
    rader = []
    for p in kampanjer:
        namn = p.get("namn", "")
        kp = p.get("kampanjpris", "")
        txt = p.get("kampanjtext", "")
        rader.append(f"- {namn}: {kp} kr ({txt})" if txt else f"- {namn}: {kp} kr")
    return "\n".join(rader)


def _matcha_ingrediens(sök, produkt_db: dict, namn: str, mangd: str) -> dict:
    träffar = sök.sök(namn, 1)
    if not träffar:
        return {"namn_ingrediens": namn, "mangd": mangd, "matchad": False}

    p = träffar[0]
    pos = produkt_db.get(p.get("id")) or {}
    return {
        "produkt_id":   p.get("id"),
        "namn_ingrediens": namn,
        "mangd":        mangd,
        "visningsnamn": p.get("namn"),
        "pris":         p.get("pris"),
        "enhetspris":   p.get("enhetspris"),
        "kampanjpris":  p.get("kampanjpris"),
        "kampanjtext":  p.get("kampanjtext"),
        "bild_url":     p.get("bild_url"),
        "x":            pos.get("x"),
        "y":            pos.get("y"),
        "z":            pos.get("z"),
        "matchad":      True,
    }


def foresla_matratter(meddelande: str, karta: str = "hela_butiken") -> dict:
    """Returnera {matratter: [...]} berikade med riktiga priser och besparing."""
    sök = get_produkt_sök()

    produkt_db = {
        p["id"]: {"x": p.get("x"), "y": p.get("y", 0), "z": p.get("z")}
        for p in läs_konsoliderade(karta)
        if p.get("id")
    }

    kampanjer = _kampanjprodukter(sök)
    kontext = _bygg_kampanjkontext(kampanjer)

    svar = client.messages.create(
        model=MODELL,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"Kundens önskemål: {meddelande}\n\n"
                f"Varor på kampanj just nu:\n{kontext}\n\n"
                "Föreslå maträtter som JSON enligt schemat."
            ),
        }],
    )

    text = "".join(b.text for b in svar.content if b.type == "text").strip()
    # Tål ev. ```json-staket.
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"matratter": []}

    matratter = []
    for rätt in data.get("matratter", []):
        ingredienser = [
            _matcha_ingrediens(sök, produkt_db, i.get("namn", ""), i.get("mangd", ""))
            for i in rätt.get("ingredienser", [])
        ]

        total = ordinarie = 0.0
        for ing in ingredienser:
            ord_pris = _flyt(ing.get("pris"))
            kampanj  = _flyt(ing.get("kampanjpris"))
            effektivt = kampanj if kampanj is not None else ord_pris
            if effektivt is not None:
                total += effektivt
            if ord_pris is not None:
                ordinarie += ord_pris

        bild = next((i.get("bild_url") for i in ingredienser if i.get("bild_url")), "")

        matratter.append({
            "namn":         rätt.get("namn"),
            "beskrivning":  rätt.get("beskrivning"),
            "portioner":    rätt.get("portioner"),
            "protein_g_per_portion": rätt.get("protein_g_per_portion"),
            "bild_url":     bild,
            "total_pris":   round(total, 2),
            "ordinarie_pris": round(ordinarie, 2),
            "besparing":    round(ordinarie - total, 2),
            "ingredienser": ingredienser,
        })

    return {"matratter": matratter}

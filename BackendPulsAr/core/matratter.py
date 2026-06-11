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

from core.matratt_bilder import hämta_matbild
from core.produkt_sok import get_produkt_sök
from core.produkt_skanning import läs_konsoliderade

client = anthropic.Anthropic()
# Haiku räcker gott för JSON-komposition av rätter och är ~2-3x snabbare +
# billigare än Sonnet. Latensen i detta anrop är nästan helt modellgenerering.
MODELL = "claude-haiku-4-5-20251001"


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

Du får en lista över varor som är PÅ KAMPANJ just nu. Kampanjvarorna är en BONUS — \
använd dem BARA när de naturligt hör hemma i en rätt som ändå passar kundens önskemål. \
Tvinga ALDRIG in en kampanjvara i en rätt där den inte hör hemma.

Returnera JSON enligt exakt detta schema:
{
  "matratter": [
    {
      "namn": "Kort aptitlig titel",
      "beskrivning": "1 kort mening som säljer rätten",
      "portioner": 4,
      "protein_g_per_portion": 38,
      "huvudingrediens": "kycklingfilé",
      "ingredienser": [
        {"namn": "kycklingfilé", "mangd": "600 g"},
        {"namn": "broccoli", "mangd": "1 st"}
      ]
    }
  ]
}

Regler:
- VIKTIGAST: rätterna ska vara kulinariskt rimliga och traditionella. Kombinera bara \
ingredienser som faktiskt hör ihop i en rätt en människa skulle vilja äta. Hellre en \
enkel klassisk rätt än en konstig kombination bara för att utnyttja kampanj.
- Utgå alltid från vad kunden faktiskt frågar efter (t.ex. "oxfilé") och bygg rätten \
runt det. Kampanjvaror läggs bara till om de passar.
- Föreslå exakt det antal maträtter som meddelandet ber om.
- Ingrediensnamn ska vara enkla sökord (t.ex. "kycklingfilé", "ris", "grädde") så att \
de går att matcha mot butikens sortiment. Undvik märkesnamn.
- huvudingrediens: rättens "hjälte" — proteinet/råvaran som bäst representerar rätten \
på bild (t.ex. "oxfilé", "lax", "kycklingfilé"). Måste vara exakt ett av ingrediensnamnen. \
Aldrig en pantry-vara som smördeg, mjöl, tomat eller kryddor.
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


def _välj_bästa(träffar: list[dict]) -> dict:
    """
    Sökträffarna är redan sorterade på namnrelevans (match_score). Lita på
    den ordningen — pris/kg är en dålig proxy för "rätt vara" (potatismjöl är
    billigare per kg än potatis). Enda justeringen: bland träffar som är
    ungefär lika relevanta som bästa, föredra kampanjvara (rättens syfte är
    besparing).
    """
    bästa = träffar[0]
    topp = bästa.get("match_score") or 0
    for t in träffar:
        if (t.get("match_score") or 0) >= topp - 8 and t.get("kampanjpris"):
            return t
    return bästa


def _välj_bild(ingredienser: list[dict], huvudingrediens: str | None) -> str:
    """
    Rättens bild = huvudingrediensens produktfoto (oxfilé/lax/kyckling) i stället
    för första bästa ingrediens (kunde bli smördeg/tomat). Fallback: första
    ingrediens med bild.
    """
    huvud = (huvudingrediens or "").lower().strip()
    if huvud:
        for i in ingredienser:
            if i.get("bild_url") and huvud in (i.get("namn_ingrediens") or "").lower():
                return i["bild_url"]
    return next((i.get("bild_url") for i in ingredienser if i.get("bild_url")), "")


def _matcha_ingrediens(sök, produkt_db: dict, namn: str, mangd: str) -> dict:
    träffar = sök.sök(namn, 5)
    if not träffar:
        return {"namn_ingrediens": namn, "mangd": mangd, "matchad": False}

    p = _välj_bästa(träffar)
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


# Tre teman → tre PARALLELLA enrätts-anrop i stället för ett långt 3-rätters-anrop.
# Varje anrop genererar ~1/3 så mycket text och körs samtidigt → väggtiden blir
# ungefär tiden för ETT anrop i stället för summan. Temana är medvetet skilda i
# KÖK och TILLAGNINGSSÄTT så rätterna divergerar tydligt (inte bara "grillad vs
# stekt + en ingrediens"). Varje anrop ser bara sitt eget tema.
TEMAN = [
    "en klassisk svensk husmanskostvariant, lagad i ugn eller på spis",
    "en rätt tydligt inspirerad av ett annat kök — t.ex. asiatiskt (wok/curry), "
    "italienskt (pasta/risotto) eller mexikanskt (tacos/gryta)",
    "en lite lyxigare helgrätt med ett annat tillagningssätt och andra "
    "tillbehör än de övriga förslagen",
]


def _generera_rätt(meddelande: str, kontext: str, tema: str) -> dict | None:
    """Ett Claude-anrop → exakt en rätt (rå dict från modellen) eller None."""
    svar = client.messages.create(
        model=MODELL,
        max_tokens=700,
        system=[{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{
            "role": "user",
            "content": (
                f"Kundens önskemål: {meddelande}\n\n"
                f"Varor på kampanj just nu:\n{kontext}\n\n"
                f"Föreslå EXAKT 1 maträtt — {tema}. Svara som JSON enligt schemat "
                "(matratter-listan med precis ett objekt)."
            ),
        }],
    )
    text = "".join(b.text for b in svar.content if b.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    rätter = data.get("matratter") or []
    return rätter[0] if rätter else None


def foresla_matratter(meddelande: str, karta: str = "hela_butiken") -> dict:
    """Returnera {matratter: [...]} berikade med riktiga priser och besparing."""
    import time
    import threading
    from concurrent.futures import ThreadPoolExecutor
    t0 = time.perf_counter()
    sök = get_produkt_sök()

    produkt_db = {
        p["id"]: {"x": p.get("x"), "y": p.get("y", 0), "z": p.get("z")}
        for p in läs_konsoliderade(karta)
        if p.get("id")
    }

    kampanjer = _kampanjprodukter(sök)
    kontext = _bygg_kampanjkontext(kampanjer)

    # Memoisera ingrediens-sökningar inom requesten — smör/vitlök/salt återkommer
    # mellan rätterna och behöver bara matchas en gång (mangd skiljer sig dock).
    match_cache: dict[str, dict] = {}
    cache_lås = threading.Lock()

    def _matcha(namn: str, mangd: str) -> dict:
        nyckel = (namn or "").lower().strip()
        with cache_lås:
            bas = match_cache.get(nyckel)
        if bas is None:
            bas = _matcha_ingrediens(sök, produkt_db, namn, "")
            with cache_lås:
                match_cache[nyckel] = bas
        ing = dict(bas)
        ing["mangd"] = mangd
        return ing

    def _berika_rätt(rätt: dict | None, index: int = 0) -> dict | None:
        if not rätt:
            return None
        ingredienser = [
            _matcha(i.get("namn", ""), i.get("mangd", ""))
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

        # Riktigt matfoto (Pexels) — IO, körs parallellt med andra rätters sök.
        # `index` ger snarlika rätter olika bild ur samma träfflista.
        bild = (
            hämta_matbild(rätt.get("namn") or "", index)
            or hämta_matbild(rätt.get("huvudingrediens") or "", index)
            or _välj_bild(ingredienser, rätt.get("huvudingrediens"))
        )
        return {
            "namn":         rätt.get("namn"),
            "beskrivning":  rätt.get("beskrivning"),
            "portioner":    rätt.get("portioner"),
            "protein_g_per_portion": rätt.get("protein_g_per_portion"),
            "bild_url":     bild,
            "total_pris":   round(total, 2),
            "ordinarie_pris": round(ordinarie, 2),
            "besparing":    round(ordinarie - total, 2),
            "ingredienser": ingredienser,
        }

    # Ett pipeline-spår per tema: generera rätten OCH berika den direkt i samma task.
    # Då göms en rätts berika (sök + Pexels) under de andra rätternas Claude-generering
    # → väggtiden blir ~det långsammaste enskilda spåret, inte claude + berika i sekvens.
    def _pipeline(index: int) -> dict | None:
        return _berika_rätt(_generera_rätt(meddelande, kontext, TEMAN[index]), index)

    with ThreadPoolExecutor(max_workers=len(TEMAN)) as pool:
        berikade = list(pool.map(_pipeline, range(len(TEMAN))))
    matratter = [m for m in berikade if m]

    print(f"⏱️  matratter: total={time.perf_counter()-t0:.1f}s "
          f"(pipeline {len(TEMAN)}x) konfig={MODELL} (rätter={len(matratter)})")
    return {"matratter": matratter}

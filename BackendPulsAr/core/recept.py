"""
recept.py - Receptdriven matinspiration för Puls-AR
─────────────────────────────────────────────────────────────────
I stället för att låta Claude HITTA PÅ rätter (matratter.py) söker vi i
~23 000 RIKTIGA ICA-recept (skrapade av scraper/ica_recept_scraper.py).
Det ger riktiga, beprövade rätter med riktiga foton och näringsvärden —
och nästan noll kostnad per sökning (ingen LLM-generering per rätt).

Flöde per sökning:
  1. Claude (Haiku) tolkar fritextfrågan ("ge mig något billigt" / "high
     protein") → strukturerade filter (ingredienser, diet, sortering). EN
     billig parsning, funkar på svenska och engelska.
  2. Filtrera de förmatchade recepten på dessa filter.
  3. Ranka: räkna ut FÄRSK besparing per recept från kampanjpriser just nu
     (kampanjer byts varje vecka, men ingrediens→produkt-matchningen är
     förbyggd → bara dict-uppslag, snabbt).
  4. Returnera topp N i SAMMA svarsformat som matratter.py så att iOS-appen
     inte behöver ändras.

Förmatchning (bygg_recept_index) körs offline efter varje skrap/katalog-
uppdatering: varje ingrediens matchas EN gång mot sortimentet och produkt-id
sparas på ingrediensen i data/ica_recept.json.
"""

import json
import math
import os
import re
import threading
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import anthropic

from core.produkt_sok import get_produkt_sök
from core.produkt_skanning import läs_konsoliderade

client = anthropic.Anthropic()
MODELL = "claude-haiku-4-5-20251001"

DATA_FIL = Path(__file__).resolve().parent.parent / "data" / "ica_recept.json"
_BAS_URL = os.environ.get("PUBLIC_BASE_URL", "http://100.84.130.65:8000").rstrip("/")

# Ingrediensord som diskvalificerar ett recept för en viss diet.
_KÖTT_FISK = {
    "kyckling", "fläsk", "fläskfilé", "fläskkarré", "nöt", "nötkött", "kött",
    "köttfärs", "färs", "bacon", "skinka", "korv", "kassler", "kalkon", "anka",
    "lamm", "oxfilé", "oxkött", "biff", "entrecote", "ryggbiff", "prosciutto",
    "salami", "chorizo", "lax", "fisk", "torsk", "sej", "räkor", "räka",
    "tonfisk", "skaldjur", "musslor", "kräft", "räk", "skagen", "sill",
    "makrill", "abborre",
    "sardin", "ansjovis", "hummer", "krabba", "scampi", "kaviar", "rom",
    "bläckfisk", "gädda", "rödspätta", "kolja", "hälleflundra", "öring",
    "vilt", "rådjur", "älg", "ren", "lever", "blodpudding", "leverpastej",
    "isterband", "falukorv", "medvurst", "pastrami", "rostbiff", "pancetta",
}
_DJUR = _KÖTT_FISK | {
    "ägg", "mjölk", "grädde", "smör", "ost", "yoghurt", "crème", "creme",
    "parmesan", "fetaost", "mozzarella", "honung", "filmjölk", "kvarg", "keso",
}
# Fisk/skaldjur ligger ofta INBÄDDADE i sammansättningar (äppelsill,
# wannameiräkor, gravlax, havskräftor) → \b-prefix missar dem. Dessa stavningar
# förekommer inte i icke-fisk-ord, så de är säkra att matcha som ren delsträng.
_INBÄDDAD_FISK = ("sill", "räk", "lax", "torsk", "makrill", "sardin", "kräft")

# Kategori-/nyckelord som visar att receptet INTE är en riktig måltid (sött,
# fika, dryck, tillbehör/sås). Filtreras bort om kunden inte uttryckligen ber
# om en sådan typ (annars rankas snabba efterrätter/dressingar över middagar).
_EJ_MÅLTID = {
    "efterrätt", "dessert", "glass", "sorbet", "tårta", "bakelse", "kladdkaka",
    "cheesecake", "muffins", "cupcake", "godis", "fika", "fikabröd", "kakor",
    "småkakor", "bulle", "bullar", "drink", "cocktail", "smoothie", "milkshake",
    "glögg", "sylt", "marmelad",
    "tillbehör", "dressing", "röra", "dipp", "marinad", "pesto", "chutney",
    "sås", "majonnäs", "tzatziki", "kryddsmör",
}

# Många ICA-recept saknar kategori/nyckelord → den enda signalen är NAMNET.
# Slutar namnet på ett av dessa ord är hela rätten det tillbehöret/efterrätten
# (t.ex. "Krämig citrondressing", "Vaniljglass"). Curated: INTE "bullar"/"kakor"
# (köttbullar/fiskkakor är måltider). Gate:as med " med " (komponerad rätt).
_EJ_MÅLTID_SUFFIX = (
    "dressing", "sås", "majonnäs", "majo", "pesto", "tzatziki", "chutney",
    "marmelad", "sylt", "tårta", "glass", "dipp", "smoothie", "milkshake",
    "cocktail", "glögg", "kladdkaka", "cheesecake", "sorbet",
    "drink", "shot", "lemonad", "macka", "smörgås", "toast",
)

# ICA:s receptkorpus innehåller även icke-mat (skönhets-/DIY-recept). Substr-
# match på namnet (t.ex. "Apelsindoftande handpeeling") → uteslut alltid.
_ICKE_MAT = (
    "peeling", "scrub", "skrubb", "tvål", "badbomb", "schampo", "balsam",
    "ansiktsmask", "kroppslotion", "handkräm", "deodorant",
)

# En riktig måltid mättar. Recept med känt lågt energiinnehåll per portion är
# tilltugg/tillbehör/små sallader (t.ex. grillade pimientos 216 kcal) — filtrera
# bort dem när kunden vill ha mat (men inte när hen bett om efterrätt).
_MIN_KCAL_MÅLTID = 250
# Känt rejält energiinnehåll = nästan säkert en middag → lyft i rankningen så
# matiga rätter slår lätta recept utan näringsdata (kcal=None passerar golvet).
_MÄTTANDE_KCAL = 350


# ─────────────────────────────────────────────
# LADDNING (cacheas i RAM)
# ─────────────────────────────────────────────
_recept_cache: list[dict] | None = None
_cache_lås = threading.Lock()


def _ladda_recept() -> list[dict]:
    global _recept_cache
    with _cache_lås:
        if _recept_cache is None:
            if DATA_FIL.exists():
                with open(DATA_FIL, encoding="utf-8") as f:
                    _recept_cache = json.load(f)
            else:
                _recept_cache = []
        return _recept_cache


def ladda_om_recept() -> int:
    """Tvinga omladdning (efter ny scrape/index). Returnerar antal recept."""
    global _recept_cache
    with _cache_lås:
        _recept_cache = None
    return len(_ladda_recept())


def recept_finns() -> bool:
    return bool(_ladda_recept())


# ─────────────────────────────────────────────
# FÖRMATCHNING (offline)
# ─────────────────────────────────────────────

def _matcha_namn_chunk(namn_lista: list[str]) -> dict[str, str | None]:
    """
    Processpool-arbetare: matcha en grupp unika ingrediensnamn mot sortimentet.
    Varje process laddar sin egen ProduktSök-singleton (en gång) och kör den
    GIL-bundna fuzzy-sökningen — så flera kärnor jobbar parallellt.
    """
    sök = get_produkt_sök()
    ut: dict[str, str | None] = {}
    for namn in namn_lista:
        träffar = sök.sök(namn, 1)
        ut[namn] = träffar[0].get("id") if träffar else None
    return ut


def bygg_recept_index() -> int:
    """
    Matcha varje ingrediens i varje recept mot sortimentet EN gång och spara
    produkt_id på ingrediensen. Memoiserar på ingrediensnamn (samma "vetemjöl"
    återkommer i tusentals recept) och parallelliserar den tunga fuzzy-
    matchningen över processer. Skriver tillbaka till data/ica_recept.json.
    """
    if not DATA_FIL.exists():
        print("❌ data/ica_recept.json saknas — kör scrapern först")
        return 0
    with open(DATA_FIL, encoding="utf-8") as f:
        recept = json.load(f)

    # Samla unika ingrediensnamn (gemener, trimmat) — matcha varje EN gång.
    unika = sorted({
        nyckel
        for r in recept
        for ing in r.get("ingredienser", [])
        if (nyckel := (ing.get("namn") or "").lower().strip())
    })
    print(f"🔎 {len(unika)} unika ingredienser att matcha mot sortimentet")

    # Fuzzy-sökningen är GIL-bunden ren Python → parallellisera över kärnor.
    arbetare = max(1, os.cpu_count() or 2)
    storlek = max(1, math.ceil(len(unika) / arbetare))
    chunkar = [unika[i:i + storlek] for i in range(0, len(unika), storlek)]
    cache: dict[str, str | None] = {}
    klar = 0
    with ProcessPoolExecutor(max_workers=arbetare) as pool:
        for delresultat in pool.map(_matcha_namn_chunk, chunkar):
            cache.update(delresultat)
            klar += len(delresultat)
            print(f"   matchat {klar}/{len(unika)} unika ingredienser")

    for r in recept:
        for ing in r.get("ingredienser", []):
            ing["produkt_id"] = cache.get((ing.get("namn") or "").lower().strip())

    with open(DATA_FIL, "w", encoding="utf-8") as f:
        json.dump(recept, f, ensure_ascii=False)
    ladda_om_recept()
    print(f"✅ Förmatchade {len(recept)} recept ({len(unika)} unika ingredienser) → {DATA_FIL.name}")
    return len(recept)


# ─────────────────────────────────────────────
# FRÅGETOLKNING (Haiku → strukturerade filter)
# ─────────────────────────────────────────────

_PARSE_PROMPT = """Du tolkar en kunds fritextfråga om matinspiration till ett \
JSON-filter. Frågan kan vara på svenska eller engelska. Svara ENDAST med giltig \
JSON, inget annat.

Schema:
{
  "ingredienser_med": [],   // råvaror som MÅSTE ingå (t.ex. ["kyckling"]). Översätt till svenska, gemener.
  "diet": null,             // "vegetariskt", "veganskt" eller null
  "sortering": "relevans",  // "billigt" om kunden vill ha billigt/spara/kampanj; "protein" om proteinrikt; "snabbt" om snabbt/få minuter; annars "relevans"
  "max_tid_min": null,      // heltal om kunden anger en tidsgräns, annars null
  "vill_efterrätt_dryck": false, // true ENDAST om kunden uttryckligen vill ha efterrätt/dessert/bakverk/fika/dryck/drink. Annars false (kunden vill ha vanlig mat/måltid).
  "nyckelord": []           // övriga sökord på svenska, gemener (t.ex. ["middag","gryta"]). Tom om inga.
}

Exempel:
"ge mig något billigt" → {"ingredienser_med":[],"diet":null,"sortering":"billigt","max_tid_min":null,"vill_efterrätt_dryck":false,"nyckelord":[]}
"high protein chicken dinner" → {"ingredienser_med":["kyckling"],"diet":null,"sortering":"protein","max_tid_min":null,"vill_efterrätt_dryck":false,"nyckelord":["middag"]}
"vegetariskt på 20 minuter" → {"ingredienser_med":[],"diet":"vegetariskt","sortering":"snabbt","max_tid_min":20,"vill_efterrätt_dryck":false,"nyckelord":[]}
"en god efterrätt" → {"ingredienser_med":[],"diet":null,"sortering":"relevans","max_tid_min":null,"vill_efterrätt_dryck":true,"nyckelord":["efterrätt"]}"""


def _parsa_fraga(meddelande: str, model: str = MODELL) -> dict:
    standard = {"ingredienser_med": [], "diet": None, "sortering": "relevans",
                "max_tid_min": None, "vill_efterrätt_dryck": False, "nyckelord": []}
    try:
        svar = client.messages.create(
            model=model,
            max_tokens=200,
            system=[{"type": "text", "text": _PARSE_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": meddelande}],
        )
        text = "".join(b.text for b in svar.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{"):]
        filt = json.loads(text)
        return {**standard, **{k: filt.get(k, standard[k]) for k in standard}}
    except Exception:
        return standard


# ─────────────────────────────────────────────
# PRISSÄTTNING + RANKNING
# ─────────────────────────────────────────────

def _flyt(värde) -> float | None:
    try:
        return float(str(värde).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _prissatt(recept: dict, sök) -> tuple[float, float, float, int]:
    """(total, ordinarie, besparing, antal_kampanjvaror) från färska priser."""
    total = ordinarie = 0.0
    kampanjer = 0
    for ing in recept.get("ingredienser", []):
        pid = ing.get("produkt_id")
        if not pid:
            continue
        p = sök.id_index.get(pid)
        if not p:
            continue
        ord_pris = _flyt(p.get("pris"))
        kampanj = _flyt(p.get("kampanjpris"))
        effektivt = kampanj if kampanj is not None else ord_pris
        if effektivt is not None:
            total += effektivt
        if ord_pris is not None:
            ordinarie += ord_pris
        if kampanj is not None:
            kampanjer += 1
    return round(total, 2), round(ordinarie, 2), round(ordinarie - total, 2), kampanjer


def _matchar_diet(recept: dict, diet: str | None) -> bool:
    if not diet:
        return True
    förbjudna = _DJUR if diet == "veganskt" else _KÖTT_FISK
    # Skanna ingrediensnamnen (mest pålitliga signalen) tillsammans med taggar —
    # taggar saknar ofta råvaran (t.ex. "sardin"), så enbart taggar släpper
    # igenom kött/fisk i vegetariska träffar.
    text = (recept.get("taggar", "") + " " + " ".join(
        (ing.get("namn") or "") for ing in recept.get("ingredienser", [])
    )).lower()
    if any(re.search(rf"\b{re.escape(ord)}", text) for ord in förbjudna):
        return False
    # Fisk inbäddad i sammansättning (äppelsill, wannameiräkor) — gäller båda dieter.
    if any(o in text for o in _INBÄDDAD_FISK):
        return False
    # Sammansatt ost (ädelostsallad, getost, prästost) har "ost" inbäddat → \bost
    # missar dem. För veganskt: avvisa "ost" var som helst UTOM efter "r"
    # (annars skulle "rostad"/"rostbiff"-grönsaker felaktigt åka ut).
    if diet == "veganskt" and re.search(r"(?<!r)ost", text):
        return False
    return True


def _är_ej_måltid(recept: dict) -> bool:
    """True om receptet är efterrätt/bakverk/fika/dryck/tillbehör. Använder
    kategorier+nyckelord (men INTE ingredienser — annars skulle 'vaniljglass' i
    en middag flagga den) och, eftersom ICA ofta lämnar kategorin tom, namnets
    sista ord (en rätt som HETER '...dressing'/'...glass' ÄR tillbehöret)."""
    text = (" ".join(recept.get("kategorier") or []) + " "
            + str(recept.get("nyckelord") or "")).lower()
    if any(re.search(rf"\b{re.escape(ord)}", text) for ord in _EJ_MÅLTID):
        return True
    namn = (recept.get("namn") or "").lower()
    if " med " in namn:        # komponerad rätt, t.ex. "pasta med tomatsås"
        return False
    delar = namn.split()
    sista = delar[-1] if delar else ""
    return sista.endswith(_EJ_MÅLTID_SUFFIX)


def _innehåller_alla(recept: dict, ord_lista: list[str]) -> bool:
    taggar = recept.get("taggar", "")
    return all(o.lower() in taggar for o in ord_lista)


def _relevans(recept: dict, filt: dict, besparing: float, kampanjer: int,
              mättnadsbonus: bool = True) -> float:
    poäng = 0.0
    taggar = recept.get("taggar", "")
    for o in filt.get("nyckelord", []):
        if o.lower() in taggar:
            poäng += 10
    poäng += (recept.get("betyg") or 0) * 2        # 0..10
    # Populära recept (många betyg) är nästan alltid riktiga middagar, inte
    # småtilltugg → premiera dem så att "matiga" rätter rankas över snacks.
    poäng += min(recept.get("antal_betyg") or 0, 200) * 0.02   # 0..4
    # Mättande rätt (känt rejält kcal) lyfts över lätta/None-kcal recept — men
    # INTE när kunden bett om efterrätt (då skulle högkalori-middagar smita in).
    if mättnadsbonus and ((recept.get("naring") or {}).get("kcal") or 0) >= _MÄTTANDE_KCAL:
        poäng += 6
    poäng += min(kampanjer, 5) * 3                  # premiera kampanjtäckning
    poäng += min(besparing, 50) * 0.4
    return poäng


def _tid_band(recept: dict) -> int:
    """Grov tidsklass så "snabbt" inte rankar den snabbaste minimaträtten över
    en strax långsammare men bättre middag. Okänd tid hamnar sist."""
    t = _tid_min(recept)
    if t is None:
        return 9
    if t <= 20:
        return 0
    if t <= 35:
        return 1
    if t <= 50:
        return 2
    return 3


def _sortera(scored: list[dict], sortering: str) -> list[dict]:
    if sortering == "billigt":
        scored.sort(key=lambda s: (-s["besparing"], s["total"]))
    elif sortering == "protein":
        scored.sort(key=lambda s: -(s["recept"]["naring"].get("protein") or 0))
    elif sortering == "snabbt":
        # Tidsband först, men inom samma band vinner relevans (betyg/popularitet)
        # → en populär 20-min-middag slår en 8-min-dressing.
        scored.sort(key=lambda s: (_tid_band(s["recept"]), -s["relevans"]))
    else:
        scored.sort(key=lambda s: (-s["relevans"], -s["besparing"]))
    return scored


def _tid_min(recept: dict) -> int | None:
    """ISO8601-varaktighet 'PT30M' / 'PT1H15M' → minuter."""
    t = recept.get("tid") or ""
    m = re.search(r"PT(?:(\d+)H)?(?:(\d+)M)?", t)
    if not m:
        return None
    h = int(m.group(1) or 0)
    mn = int(m.group(2) or 0)
    return h * 60 + mn or None


# ─────────────────────────────────────────────
# ENRICHMENT → matratter-format (iOS oförändrad)
# ─────────────────────────────────────────────

def _bild_url(recept: dict) -> str:
    lokal = recept.get("bild_lokal")
    if lokal:
        return f"{_BAS_URL}{lokal}" if lokal.startswith("/") else lokal
    return recept.get("bild_url") or ""


def _till_matratt(recept: dict, sök, produkt_db: dict,
                  total: float, ordinarie: float, besparing: float) -> dict:
    ingredienser = []
    for ing in recept.get("ingredienser", []):
        pid = ing.get("produkt_id")
        p = sök.id_index.get(pid) if pid else None
        pos = produkt_db.get(pid) or {}
        mangd = " ".join(filter(None, [ing.get("mangd", ""), ing.get("enhet", "")])).strip() \
            or ing.get("text", "")
        ingredienser.append({
            "produkt_id":      pid if p else None,
            "namn_ingrediens": ing.get("namn", ""),
            "mangd":           mangd,
            "visningsnamn":    p.get("namn") if p else None,
            "pris":            p.get("pris") if p else None,
            "enhetspris":      p.get("enhetspris") if p else None,
            "kampanjpris":     p.get("kampanjpris") if p else None,
            "kampanjtext":     p.get("kampanjtext") if p else None,
            "bild_url":        p.get("bild_url") if p else None,
            "x":               pos.get("x"),
            "y":               pos.get("y"),
            "z":               pos.get("z"),
            "matchad":         bool(p),
        })
    näring = recept.get("naring") or {}
    return {
        "namn":         recept.get("namn"),
        "beskrivning":  recept.get("beskrivning") or "",
        "portioner":    int(recept.get("portioner") or 4),
        "protein_g_per_portion":     näring.get("protein"),
        "kolhydrater_g_per_portion": näring.get("kolhydrater"),
        "fett_g_per_portion":        näring.get("fett"),
        "kcal_per_portion":          näring.get("kcal"),
        "bild_url":     _bild_url(recept),
        "total_pris":   total,
        "ordinarie_pris": ordinarie,
        "besparing":    besparing,
        "ingredienser": ingredienser,
    }


def sok_recept(meddelande: str, karta: str = "hela_butiken",
               antal: int = 12, model: str = MODELL) -> dict:
    """Sök riktiga ICA-recept → {matratter:[...]} i matratter-format."""
    recept = _ladda_recept()
    if not recept:
        return {"matratter": []}

    sök = get_produkt_sök()
    produkt_db = {
        p["id"]: {"x": p.get("x"), "y": p.get("y", 0), "z": p.get("z")}
        for p in läs_konsoliderade(karta) if p.get("id")
    }

    filt = _parsa_fraga(meddelande, model)
    med = filt.get("ingredienser_med") or []
    diet = filt.get("diet")
    max_tid = filt.get("max_tid_min")
    vill_efterrätt = bool(filt.get("vill_efterrätt_dryck"))

    scored: list[dict] = []
    for r in recept:
        if med and not _innehåller_alla(r, med):
            continue
        # Skönhets-/DIY-recept är inte mat — uteslut alltid.
        if any(o in (r.get("namn") or "").lower() for o in _ICKE_MAT):
            continue
        # Visa bara riktiga måltider om kunden inte uttryckligen bett om
        # efterrätt/dryck — annars rankas snabba desserter/tilltugg över middagar.
        if not vill_efterrätt:
            if _är_ej_måltid(r):
                continue
            kcal = (r.get("naring") or {}).get("kcal")
            if kcal is not None and kcal < _MIN_KCAL_MÅLTID:
                continue
        if not _matchar_diet(r, diet):
            continue
        if max_tid:
            t = _tid_min(r)
            if t and t > max_tid:
                continue
        total, ordinarie, besparing, kampanjer = _prissatt(r, sök)
        scored.append({
            "recept": r, "total": total, "ordinarie": ordinarie,
            "besparing": besparing,
            "relevans": _relevans(r, filt, besparing, kampanjer,
                                  mättnadsbonus=not vill_efterrätt),
        })

    sortering = filt.get("sortering") or "relevans"
    # "Billigt"/besparing kräver att vi faktiskt kunnat prissätta receptet —
    # annars skulle oprissatta recept (total=0) felaktigt hamna överst.
    if sortering == "billigt":
        scored = [s for s in scored if s["total"] > 0]

    _sortera(scored, sortering)
    topp = scored[:antal]
    matratter = [
        _till_matratt(s["recept"], sök, produkt_db,
                      s["total"], s["ordinarie"], s["besparing"])
        for s in topp
    ]
    return {"matratter": matratter}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "index":
        bygg_recept_index()
    else:
        fråga = sys.argv[1] if len(sys.argv) > 1 else "ge mig något billigt"
        import json as _j
        print(_j.dumps(sok_recept(fråga), ensure_ascii=False, indent=2)[:2000])

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
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

import anthropic

from core.produkt_sok import get_produkt_sök, _BÖJNINGS_SUFFIX
from core.produkt_skanning import läs_konsoliderade

client = anthropic.Anthropic()
MODELL = "claude-haiku-4-5-20251001"

DATA_FIL = Path(__file__).resolve().parent.parent / "data" / "ica_recept.json"
_BAS_URL = os.environ.get("PUBLIC_BASE_URL", "http://100.84.130.65:8000").rstrip("/")

# Ingrediensord som diskvalificerar ett recept för en viss diet.
_KÖTT_FISK = {
    "kyckling", "fläsk", "fläskfilé", "fläskkarré", "nöt", "nötkött", "kött",
    "köttfärs", "färs", "bacon", "skinka", "korv", "kassler", "kalkon", "anka",
    "lamm", "oxfilé", "oxkött", "biff", "entrecote", "ryggbiff", "högrev", "prosciutto",
    "salami", "chorizo", "lax", "fisk", "torsk", "sej", "räkor", "räka",
    "tonfisk", "skaldjur", "musslor", "kräft", "räk", "skagen", "sill",
    "makrill", "abborre",
    "sardin", "ansjovis", "hummer", "krabba", "scampi", "kaviar", "rom",
    "bläckfisk", "gädda", "rödspätta", "kolja", "hälleflundra", "öring",
    "vilt", "rådjur", "älg", "ren", "lever", "blodpudding", "leverpastej",
    "isterband", "falukorv", "medvurst", "pastrami", "rostbiff", "pancetta",
    "revben", "revbensspjäll", "blandfärs", "fläskfärs", "karré", "griskarré",
    "strömming", "krabb", "hamburgare", "bresaola", "serrano", "parmaskinka",
}
_DJUR = _KÖTT_FISK | {
    "ägg", "mjölk", "grädde", "smör", "ost", "yoghurt", "crème", "creme",
    "parmesan", "fetaost", "mozzarella", "honung", "filmjölk", "kvarg", "keso",
    "halloumi", "paneer", "ricotta", "mascarpone",
}

# Färdigrätter/produkter har ofta ENGELSKA namn ("Chicken curry") som de svenska
# ordlistorna missar. Dessa stavningar finns inte i veg-produkter → säkra delsträngar.
_ENGELSK_KÖTT = ("chicken", "pork", "bacon", "salmon", "tuna", "shrimp", "prawn")
# Fisk/skaldjur ligger ofta INBÄDDADE i sammansättningar (äppelsill,
# wannameiräkor, gravlax, havskräftor) → \b-prefix missar dem. Dessa stavningar
# förekommer inte i icke-fisk-ord, så de är säkra att matcha som ren delsträng.
_INBÄDDAD_FISK = ("sill", "räk", "lax", "torsk", "makrill", "sardin", "kräft", "mussl")

# Kategori-/nyckelord som visar att receptet INTE är en riktig måltid (sött,
# fika, dryck, tillbehör/sås). Filtreras bort om kunden inte uttryckligen ber
# om en sådan typ (annars rankas snabba efterrätter/dressingar över middagar).
_EJ_MÅLTID = {
    "efterrätt", "dessert", "glass", "sorbet", "tårta", "bakelse", "kladdkaka",
    "cheesecake", "muffins", "cupcake", "godis", "fika", "fikabröd", "kakor",
    "småkakor", "bulle", "bullar", "drink", "drinkar", "cocktail", "mocktail",
    "smoothie", "milkshake", "dryck", "drycker", "toddy", "punsch", "shot",
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
    "cocktail", "mocktail", "glögg", "kladdkaka", "cheesecake", "sorbet",
    "drink", "shot", "lemonad", "macka", "smörgås", "toast", "mumma", "toddy",
)

# ICA:s receptkorpus innehåller även icke-mat (skönhets-/DIY-recept). Substr-
# match på namnet (t.ex. "Apelsindoftande handpeeling") → uteslut alltid.
_ICKE_MAT = (
    "peeling", "scrub", "skrubb", "tvål", "badbomb", "schampo", "balsam",
    "ansiktsmask", "kroppslotion", "handkräm", "deodorant",
)

# Skafferivaror som kunden redan har hemma. Att matcha dem mot sortimentet ger
# (a) brus i inköpslistan och (b) skräpträffar — "olja" → "Baby Olja" (babyolja!),
# "peppar" → "Pepparbiff", "salt" → "Salt Himalaya", "vatten" → "Vatten Stilla".
# Vi prissätter/visar dem därför INTE som produkter (ingrediensen listas ändå).
_SKAFFERI = {
    "salt", "flingsalt", "havssalt", "salt och peppar", "salt & peppar",
    "salt och svartpeppar", "flingsalt och svartpeppar",
    "peppar", "svartpeppar", "vitpeppar", "grönpeppar",
    "nymalen svartpeppar", "nymald svartpeppar", "svartpeppar nymald",
    "vatten", "kallt vatten", "varmt vatten", "ljummet vatten",
    "socker", "strösocker", "florsocker", "råsocker",
    "olja", "matolja", "neutral olja", "olja till stekning", "stekolja",
}

# En riktig måltid mättar. Recept med känt lågt energiinnehåll per portion är
# tilltugg/tillbehör/små sallader (t.ex. grillade pimientos 216 kcal) — filtrera
# bort dem när kunden vill ha mat (men inte när hen bett om efterrätt).
_MIN_KCAL_MÅLTID = 250
# Känt rejält energiinnehåll = nästan säkert en middag → lyft i rankningen så
# matiga rätter slår lätta recept utan näringsdata (kcal=None passerar golvet).
_MÄTTANDE_KCAL = 350

# I "kampanj"-läget ska rätten vara MÄRKBART billigare än vanligt. En enskild
# liten rabattvara i en stor korg ger bara nån enstaka procent rabatt — det är
# ingen "kampanjmåltid". Kräv minst denna relativa rabatt på hela korgen.
_MIN_KAMPANJANDEL = 0.10

# Fuzzy-matchningen baka(d)s in vid indexering (match_score per ingrediens). En
# svag träff = sannolikt fel/skräpprodukt (t.ex. tonfisk→lax, "edamer ost"→något
# helt annat) → visa/prissätt den inte. Tröskeln tillämpas vid SÖKNING (inget
# nytt index krävs för att justera den) men kräver att indexet bakat match_score.
# Recept utan match_score (äldre index) släpps igenom oförändrat.
_MIN_MATCH_SCORE = 55

# Kampanj-preferensen (välj nedsatt kandidat) får BARA slå till bland kandidater
# som är nästan lika bra namnmatch som den bästa — inom så här många poäng. Annars
# vinner en nedsatt MEN sämre match (morot→morotskaka, potatis→potatismjöl).
_KAMPANJ_MARGINAL = 8

# Huvudproteinkälla per recept — härleds gratis ur namn+ingredienser (ingen LLM).
# Används för att SPRIDA träffarna: utan den blir t.ex. "billigt" bara kyckling
# (kyckling är billigt just nu), trots att andra billiga proteiner finns. Ordning
# = prioritet (mer specifikt först). Fisk/skaldjur matchas som delsträng (de
# ligger ofta inbäddade: gravlax, wannameiräkor); kötten kräver \b-prefix.
_PROTEINKÄLLA: list[tuple[str, tuple[str, ...], bool]] = [
    ("kyckling",    ("kyckling",), False),
    ("kalkon",      ("kalkon",), False),
    ("fläsk",       ("fläsk", "bacon", "skinka", "kassler", "karré", "revben", "pancetta"), False),
    ("nötkött",     ("nöt", "biff", "oxfilé", "oxkött", "entrecote", "ryggbiff", "högrev", "rostbiff", "köttfärs"), False),
    ("korv",        ("korv", "chorizo", "salami", "isterband", "medvurst"), False),
    ("lamm",        ("lamm",), False),
    ("vilt",        ("vilt", "rådjur", "älg", "ren ", "renstek"), False),
    ("skaldjur",    ("räk", "kräft", "musslor", "hummer", "krabba", "scampi", "skagen", "bläckfisk"), True),
    ("fisk",        ("lax", "torsk", "fisk", "makrill", "sill", "abborre", "kolja", "öring", "tonfisk", "gädda", "rödspätta", "hälleflundra", "sardin", "ansjovis"), True),
    ("baljväxt",    ("böna", "bönor", "linser", "lins", "kikärt", "kikärtor", "ärtor"), False),
    ("vegoprotein", ("tofu", "quorn", "sojafärs", "sojabit", "tempeh", "seitan"), False),
    ("ägg",         ("ägg",), False),
    ("ost",         ("halloumi", "fetaost", "paneer"), False),
]


def _proteinkälla(recept: dict) -> str:
    """Bästa gissning på rättens huvudprotein (för spridning). 'övrigt' om okänt."""
    text = ((recept.get("namn") or "") + " " + " ".join(
        (ing.get("namn") or "") for ing in recept.get("ingredienser", [])
    )).lower()
    for källa, ord_lista, delsträng in _PROTEINKÄLLA:
        if delsträng:
            if any(o in text for o in ord_lista):
                return källa
        elif any(re.search(rf"\b{re.escape(o)}", text) for o in ord_lista):
            return källa
    return "övrigt"


def _diversifiera(scored: list[dict], antal: int) -> list[dict]:
    """Sprid topplistan över proteinkällor med REN ROUND-ROBIN (inget tak): ta
    bästa återstående rätt ur varje källa, varv för varv, tills listan är full.
    Det begränsar automatiskt varje källa till ~antal/antal_källor — så en enskild
    källa (t.ex. kyckling när den är billig) inte fyller listan — men använder
    ALLA källor, så även räkor/nötkött/fisk får plats tidigt om de finns i
    träfflistan. Varje varv besöks källorna i ordning efter sin bästa återstående
    rätt (global rankordning) så starka källor kommer tidigt. När en källa tar
    slut faller den bort (automatisk utfyllnad). Bevarar rankning inom varje källa."""
    grupper: dict[str, list[dict]] = {}
    for rang, s in enumerate(scored):      # global rankordning bevaras inom källan
        s["_rang"] = rang
        grupper.setdefault(s["proteinkälla"], []).append(s)

    köer = [q for q in grupper.values()]
    ut: list[dict] = []
    while len(ut) < antal and köer:
        köer = [q for q in köer if q]               # släng tomma köer
        köer.sort(key=lambda q: q[0]["_rang"])      # källa med bästa kvarvarande rätt först
        for q in köer:
            ut.append(q.pop(0))
            if len(ut) >= antal:
                break
    return ut[:antal]


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

def _matcha_namn_chunk(namn_lista: list[str]) -> dict[str, list[dict]]:
    """
    Processpool-arbetare: matcha en grupp unika ingrediensnamn mot sortimentet.
    Varje process laddar sin egen ProduktSök-singleton (en gång) och kör den
    GIL-bundna fuzzy-sökningen — så flera kärnor jobbar parallellt. Returnerar
    en LISTA med de bästa kandidaterna (id + match_score) per ingrediens, inte
    bara top-1: så kan sökningen vid körning välja den kandidat som är på KAMPANJ
    just nu (priserna byts varje vecka, indexet ligger fast). Svaga träffar
    (< golvet) sållas bort vid sökning, inte här.
    """
    sök = get_produkt_sök()
    ut: dict[str, list[dict]] = {}
    for namn in namn_lista:
        # Sök på FLERA termer (helnamn + alternativ + huvudord, se _sök_termer) och
        # UNIONa kandidaterna: så 'finskuren gräslök'/'smör till stekning'/'smör
        # eller margarin' ändå hittar råvaran utan ordlista. Top-12 (inte 5):
        # form-vetot (_är_avledd_form) kan såll bort flera avledda toppträffar
        # (morot → morotsjuice/-soppa/-kaka...) innan den rena råvaran dyker upp.
        bäst: dict[str, float] = {}
        for term in _sök_termer(namn):
            for t in sök.sök(term, 12):
                pid, score = t.get("id"), t.get("match_score") or 0.0
                if pid is not None and score > bäst.get(pid, -1.0):
                    bäst[pid] = score
        topp = sorted(bäst.items(), key=lambda kv: kv[1], reverse=True)[:12]
        ut[namn] = [{"id": pid, "score": score} for pid, score in topp]
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
    cache: dict[str, list[dict]] = {}
    klar = 0
    with ProcessPoolExecutor(max_workers=arbetare) as pool:
        for delresultat in pool.map(_matcha_namn_chunk, chunkar):
            cache.update(delresultat)
            klar += len(delresultat)
            print(f"   matchat {klar}/{len(unika)} unika ingredienser")

    for r in recept:
        for ing in r.get("ingredienser", []):
            kandidater = cache.get((ing.get("namn") or "").lower().strip()) or []
            # Top-N kandidater så sökningen kan välja kampanjvaran; produkt_id/
            # match_score = top-1, kvar för bakåtkompatibilitet (äldre konsumenter).
            ing["produkt_kandidater"] = kandidater
            ing["produkt_id"] = kandidater[0]["id"] if kandidater else None
            ing["match_score"] = kandidater[0]["score"] if kandidater else None

    with open(DATA_FIL, "w", encoding="utf-8") as f:
        json.dump(recept, f, ensure_ascii=False)
    ladda_om_recept()
    print(f"✅ Förmatchade {len(recept)} recept ({len(unika)} unika ingredienser) → {DATA_FIL.name}")
    return len(recept)


# ─────────────────────────────────────────────
# DIET-TAGGNING (offline — Haiku läser hela receptet)
# ─────────────────────────────────────────────
# Ordlistorna (_KÖTT_FISK m.fl.) är whack-a-mole: de skannar ord och läcker hela
# tiden (bresaola, salsiccia, dashi, ostronsås...). I stället låter vi Haiku läsa
# HELA receptets ingredienser EN gång offline och baka in en ren diet-tagg. Vid
# sökning blir dietfiltret då ett exakt tagg-uppslag (noll läckor) — ordlistorna
# behålls bara som skyddsnät för ännu otaggade recept.
_DIET_GILTIGA = {"kött", "fisk", "vegetariskt", "veganskt"}

_DIET_TAGG_PROMPT = """Du klassar ICA-recept efter kost. För VARJE recept väljer \
du EXAKT en kategori utifrån ingredienserna OCH rättens namn:
- "kött": innehåller kött, fågel, charkuteri eller vilt
- "fisk": innehåller fisk eller skaldjur men inget kött/fågel
- "vegetariskt": inget kött/fågel/fisk/skaldjur, men innehåller mejeri och/eller ägg och/eller honung
- "veganskt": helt fritt från animaliska produkter (inget kött, fisk, mejeri, ägg eller honung)

Regler:
- Om NAMNET tydligt anger en djurprodukt (t.ex. "fiskgratäng", "äppelsill", "kycklingwok", "köttbullar") räknas den som kött/fisk — ÄVEN om ingredienslistan är kort eller ofullständig.
- UNDANTAG: när namnet anger en växtbaserad variant ("vegansk kyckling", "vego-bolognese", "växtbaserad färs") är det INTE animaliskt — bedöm efter de växtbaserade ingredienserna.
- Kött-/fiskbuljong, fisksås, ostronsås, ansjovis, worcestershiresås → kött resp. fisk.
- Gelatin, ister, löjrom, honung, ägg, smör, grädde, ost, mjölk, yoghurt → animaliskt (ej veganskt; mejeri/ägg/honung utan kött/fisk = vegetariskt).
- Växtbaserat (havredryck, sojayoghurt, vegansk majonnäs, tofu, vegansk quorn) → räknas inte som animaliskt.
- Charkvaror som bresaola, salami, chorizo, serrano, prosciutto, salsiccia → kött.

Svara ENDAST med en JSON-array, ett objekt per recept i samma ordning:
[{"i":0,"diet":"kött"},{"i":1,"diet":"veganskt"}]"""


def _tagga_batch(batch: list[dict], model: str) -> dict[str, str]:
    """Klassa en grupp recept → {recept_id: diet}. Tom dict vid fel/parsfel."""
    rader = []
    for i, r in enumerate(batch):
        ing = ", ".join((x.get("namn") or "") for x in r.get("ingredienser", []))[:600]
        rader.append(f"{i}. {r.get('namn', '')} | ingredienser: {ing}")
    try:
        svar = client.messages.create(
            model=model,
            max_tokens=1500,
            system=[{"type": "text", "text": _DIET_TAGG_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": "Recept:\n" + "\n".join(rader)}],
        )
        text = "".join(b.text for b in svar.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("["):]
        data = json.loads(text)
        ut: dict[str, str] = {}
        for obj in data:
            idx = obj.get("i")
            diet = obj.get("diet")
            if isinstance(idx, int) and 0 <= idx < len(batch) and diet in _DIET_GILTIGA:
                ut[batch[idx]["id"]] = diet
        return ut
    except Exception:
        return {}


def tagga_recept(model: str = MODELL, batch: int = 20, workers: int = 8) -> int:
    """
    Dietklassa alla OTAGGADE recept med Haiku och baka in diet_tagg i
    data/ica_recept.json. Resumebart (recept med diet_tagg hoppas över) och
    parallellt (Anthropic-klienten är trådsäker). Skriver löpande till disk så
    att en avbruten körning kan återupptas. Körs offline efter varje scrape.
    """
    if not DATA_FIL.exists():
        print("❌ data/ica_recept.json saknas — kör scrapern först")
        return 0
    with open(DATA_FIL, encoding="utf-8") as f:
        recept = json.load(f)

    otaggade = [r for r in recept if not r.get("diet_tagg") and r.get("id")]
    print(f"🏷️  {len(otaggade)}/{len(recept)} recept att dietklassa (Haiku, batch {batch})")
    if not otaggade:
        return 0

    batchar = [otaggade[i:i + batch] for i in range(0, len(otaggade), batch)]
    per_id: dict[str, str] = {}

    def spara():
        for r in recept:
            t = per_id.get(r.get("id"))
            if t and not r.get("diet_tagg"):
                r["diet_tagg"] = t
        with open(DATA_FIL, "w", encoding="utf-8") as f:
            json.dump(recept, f, ensure_ascii=False)

    klar = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        framtider = {pool.submit(_tagga_batch, b, model): b for b in batchar}
        for fut in as_completed(framtider):
            per_id.update(fut.result())
            klar += 1
            if klar % 50 == 0:
                spara()                       # checkpoint → resumebart
            if klar % 10 == 0 or klar == len(batchar):
                print(f"   {klar}/{len(batchar)} batchar ({len(per_id)} taggade)", end="\r")
    print()
    spara()
    ladda_om_recept()
    print(f"✅ Dietklassade {len(per_id)} recept → {DATA_FIL.name}")
    return len(per_id)


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
  "sortering": "relevans",  // "kampanj" om kunden vill ha rätter byggda på KAMPANJER/erbjudanden/rabatter/dagens fynd (måltider som blir billigare än vanligt); "billigt" om billigast totalt/spara pengar utan att nämna kampanj; "protein" om proteinrikt; "snabbt" om snabbt/få minuter; annars "relevans"
  "max_tid_min": null,      // heltal om kunden anger en tidsgräns, annars null
  "svårighet": null,        // "enkelt" om kunden vill ha lätt/snabblagat/nybörjare; "avancerat" om kunden vill laga något krångligt/festligt/utmanande; annars null
  "vill_efterrätt_dryck": false, // true ENDAST om kunden uttryckligen vill ha efterrätt/dessert/bakverk/fika/dryck/drink. Annars false (kunden vill ha vanlig mat/måltid).
  "ekologiskt": false,      // true om kunden vill ha ekologiska/KRAV-märkta/organic-varor. Annars false.
  "nyckelord": []           // övriga sökord på svenska, gemener (t.ex. ["middag","gryta"]). Tom om inga.
}

Exempel:
"ge mig något billigt" → {"ingredienser_med":[],"diet":null,"sortering":"billigt","max_tid_min":null,"svårighet":null,"vill_efterrätt_dryck":false,"ekologiskt":false,"nyckelord":[]}
"high protein chicken dinner" → {"ingredienser_med":["kyckling"],"diet":null,"sortering":"protein","max_tid_min":null,"svårighet":null,"vill_efterrätt_dryck":false,"ekologiskt":false,"nyckelord":["middag"]}
"maträtter som använder dagens kampanjer" → {"ingredienser_med":[],"diet":null,"sortering":"kampanj","max_tid_min":null,"svårighet":null,"vill_efterrätt_dryck":false,"ekologiskt":false,"nyckelord":[]}
"enkel vegetarisk middag på 20 minuter" → {"ingredienser_med":[],"diet":"vegetariskt","sortering":"snabbt","max_tid_min":20,"svårighet":"enkelt","vill_efterrätt_dryck":false,"ekologiskt":false,"nyckelord":["middag"]}
"ekologisk middag med kyckling" → {"ingredienser_med":["kyckling"],"diet":null,"sortering":"relevans","max_tid_min":null,"svårighet":null,"vill_efterrätt_dryck":false,"ekologiskt":true,"nyckelord":["middag"]}
"en god efterrätt" → {"ingredienser_med":[],"diet":null,"sortering":"relevans","max_tid_min":null,"svårighet":null,"vill_efterrätt_dryck":true,"ekologiskt":false,"nyckelord":["efterrätt"]}"""


def _parsa_fraga(meddelande: str, model: str = MODELL) -> dict:
    standard = {"ingredienser_med": [], "diet": None, "sortering": "relevans",
                "max_tid_min": None, "svårighet": None,
                "vill_efterrätt_dryck": False, "ekologiskt": False,
                "nyckelord": []}
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


def _ing_mangd(ing: dict) -> str:
    """Receptmängd som text ('2 dl', '200 g') ur ett ingrediens-dict."""
    return " ".join(filter(None, [ing.get("mangd", ""), ing.get("enhet", "")])).strip() \
        or ing.get("text", "")


def _prissatt(recept: dict, sök, diet: str | None = None,
              kampanj_läge: bool = False,
              ekologiskt: bool = False) -> tuple[float, float, float, int, int, float]:
    """(total, ordinarie, besparing, antal_kampanjvaror, antal_prissatta,
    viktad_besparing) från färska priser. antal_prissatta = ingredienser vi kunde
    sätta pris på, för att räkna ut hur STOR ANDEL av korgen som är på kampanj.
    viktad_besparing = rabatten VIKTAD med hur stor del av förpackningen receptet
    faktiskt använder — så en 20 kr-rabatt på en vara man bara använder en skvätt
    av inte räknas som full besparing för måltiden (vilseledande, se _anvand_andel).
    Produkter som bryter mot dieten räknas INTE (de visas inte heller)."""
    total = ordinarie = viktad_besparing = 0.0
    kampanjer = 0
    prissatta = 0
    for ing in _unika_ingredienser(recept):
        p = _matchad_produkt(ing, sök, diet, kampanj_läge, ekologiskt)
        if not p:
            continue
        ord_pris = _flyt(p.get("pris"))
        kampanj = _flyt(p.get("kampanjpris"))
        effektivt = kampanj if kampanj is not None else ord_pris
        if effektivt is not None:
            total += effektivt
            prissatta += 1
        if ord_pris is not None:
            ordinarie += ord_pris
        if kampanj is not None:
            kampanjer += 1
            viktad_besparing += _aktuell_besparing(p) * _anvand_andel(_ing_mangd(ing), p.get("namn", ""))
    return (round(total, 2), round(ordinarie, 2), round(ordinarie - total, 2),
            kampanjer, prissatta, round(viktad_besparing, 2))


def _kampanjpoäng(besparing: float, ordinarie: float, kampanjer: int,
                  antal_prissatta: int, total: float) -> float:
    """Hur bra ett recept KOMBINERAR kampanjvaror till en måltid som blir
    billigare än vanligt. Belönar (a) stor RELATIV rabatt (billigare än normalt),
    (b) hög ANDEL av korgen på kampanj (flera kombinerade fynd) och (c) rejäl
    absolut besparing — och håller samtidigt slutpriset nere."""
    if ordinarie <= 0:
        return 0.0
    relativ = besparing / ordinarie                  # 0..1, "billigare än vanligt"
    # Täckning mäts mot en MÅLTIDSGOLV (minst 3 varor) så ett recept där bara EN
    # vara matchat (och råkar vara på rea) inte får full täckning = 1.0 och toppar.
    täckning = kampanjer / max(antal_prissatta, 3)    # 0..1, kombinerar flera fynd
    # Belöna ANTALET kombinerade fynd absolut → en måltid byggd på flera kampanj-
    # varor slår en tunn rätt där enbart smör är på rea.
    flera_fynd = min(kampanjer, 5) * 5
    return (relativ * 60) + (täckning * 25) + flera_fynd + min(besparing, 60) * 0.4 - min(total, 250) * 0.03


def _är_skafferi(ing_namn: str) -> bool:
    """True om ingrediensen är en skafferivara (salt/peppar/vatten/olja/socker)
    som inte ska matchas mot sortimentet — undviker skräpträffar + listbrus.
    Kollar både rå- och rensat namn ('olja (till formen)' → 'olja')."""
    rå = (ing_namn or "").lower().strip()
    if rå in _SKAFFERI:
        return True
    return _rensa_ingrediensnamn(ing_namn) in _SKAFFERI


def _produkt_strider_mot_diet(produkt: dict, diet: str | None) -> bool:
    """True om en MATCHAD produkt bryter mot dieten. Receptets ingrediensnamn kan
    vara helt vegetariskt ("peppar", "buljong") men fuzzy-matchas till en KÖTT-
    produkt ("Pepparbiff", "Kycklingbuljong") — _matchar_diet kollar bara
    receptets text, inte produkten, så köttprodukter slank in i veg-rätter. Här
    validerar vi själva produkten (namn + kategori) mot samma ordlistor."""
    if not diet:
        return False
    förbjudna = _DJUR if diet == "veganskt" else _KÖTT_FISK
    text = ((produkt.get("namn") or "") + " "
            + (produkt.get("kategori") or "")).lower()
    if any(re.search(rf"\b{re.escape(ord)}", text) for ord in förbjudna):
        return True
    if any(o in text for o in _INBÄDDAD_FISK):
        return True
    if any(o in text for o in _ENGELSK_KÖTT):
        return True
    if diet == "veganskt" and re.search(r"(?<!r)ost", text):
        return True
    # Vanlig majonnäs/crème fraiche innehåller ägg/mjölk → ej veganskt. Den vegana
    # varianten heter explicit "...Vegansk" → släpp bara igenom den.
    if diet == "veganskt" and "majonnäs" in text and "vegan" not in text:
        return True
    return False


# Ord som markerar att en produkt är en BEREDD/avledd form, inte råvaran. En
# råvaru-ingrediens ("morot") fuzzy-matchar tyvärr ofta dessa högre än den rena
# varan (singular "morot" träffar inte plural "Morötter", men ÄR delsträng i
# "Morotskaka"/"Morotsjuice"/"Morotssoppa") → en KAKA hamnar i en sallad. Vi
# vetar bort dem — men BARA när form-ordet saknas i själva ingrediensnamnet, så
# att recept som faktiskt vill ha den formen ("tomatsås", "morotssoppa") behålls.
_AVLEDDA_FORMER = (
    "kaka", "kakor", "tårta", "paj", "bulle", "bullar", "kex", "glass",
    "sorbet", "godis", "kola", "smoothie", "juice", "saft", "läsk", "nektar",
    "lemonad", "soppa", "sås", "röra", "puré", "mos", "sallad", "mix",
    "surkål", "inlagd", "inlagda", "pickles", "chips",
)

# KATEGORI-baserat veto: den mest tillförlitliga och GENERELLA signalen. ICA-
# katalogens kategoritaxonomi är SLUTEN — en helt ny, aldrig-tidigare-sedd kaka/
# läsk/barnmat hamnar ändå i samma kategori → vetas utan att vi behöver lägga
# till dess NAMN. Bara kategorier som ALDRIG är en råvara att laga med (efterrätt/
# godis/snacks/läsk/färdigmat/barn). MEDVETET EXKLUDERADE: växtmjölk ("Havredryck"
# /"Sojadryck" = riktiga ingredienser), såser, inlagd sill (kan vara ingrediens).
# Substrängmatchas mot kategorin; samma skydd som namn-vetot (ordet får ej finnas
# i ingrediensnamnet, så ingrediensen "glass"/"choklad"/"barnmat" behåller sin produkt).
_AVLEDDA_KATEGORIER = (
    "glass", "sorbet", "bakels", "kondis", "godis", "choklad", "pralin",
    "chips", "snacks", "riskakor", "energidryck", "sportdryck", "fruktdryck",
    "läsk", "drinkmix", "smaksatt vatten", "barnmat", "barn ", "klämmis",
    "färdig", "fryst enportion", "fryst pizza", "snabbnudlar", "proteinbar",
    # Avledda produkter med EGEN kategori → fångas generellt (alla marmelader,
    # alla nudlar, alla redningar...), inte per produkt. "redning"=Potatismjöl &
    # Redning (potatismjöl för "potatis"), "nudlar"=Äggnudlar (för "ägg"),
    # "marmelad"/"sylt"=Apelsinmarmelad (för "apelsin"), "torkad lök"=Rostad lök.
    # "sallad"=Potatissallad/grönsakssallad (beredd rätt, inte råvara; ingrediensen
    # "sallad"/"sallat" behåller sin produkt via samma ej-i-namnet-skydd).
    "marmelad", "sylt", "nudlar", "redning", "torkad lök", "sallad",
)

# Hela ICA-AVDELNINGAR (toppkategorin i sökvägen) som ALDRIG är en mat-ingrediens.
# En råvara utan riktig katalogträff fuzzy-matchar annars skräp över _MIN_MATCH_SCORE
# (sky→Mascara, kalvinnanlår→Kattmat, silverkulor→Ballong). Avdelning är en sluten
# taxonomi → vetar generellt, inte per produkt. EXAKT-match (ej delsträng) eftersom
# "Fisk & Skaldjur"/"Vegetariskt" är mat. Behåller medvetet Kök (folie/bakplåtspapper
# matchar rätt), Grill, Träning & Återhämtning, Midsommar, Nyheter (mat/blandat).
_NONFOOD_AVDELNINGAR = frozenset({
    "Apotek, Hälsa & Skönhet", "Barn", "Blommor & Trädgård", "Djur", "Fritid",
    "Hem & Inredning", "Kläder & Accessoarer", "Städ, Tvätt & Papper", "Tobak",
})


def _är_avledd_form(produkt: dict, ing_namn: str) -> bool:
    """True om produkten är en beredd/avledd form (kaka/juice/soppa/läsk...) av en
    ingrediens som inte bad om den formen → fel produkt för en råvara. Kollar
    KATEGORI först (sluten taxonomi → fångar även okända produkter) och faller
    tillbaka på NAMN-vetot. Samma skydd: form-ordet får inte finnas i ingrediens-
    namnet (så ingrediensen "glass"/"tomatsås"/"barnmat" behåller sin produkt)."""
    namn = (produkt.get("namn") or "").lower()
    kat = (produkt.get("kategori") or "").lower()
    ing = (ing_namn or "").lower()
    # Ingrediensen bad UTTRYCKLIGEN om just den här produkten: alla ingrediens-ord
    # finns i produktnamnet OCH produktnamnets första ord finns i ingrediensen →
    # råvaran ÄR den efterfrågade, inte en avledd form. Fångar t.ex. ingrediens
    # "rostad lök" → produkt "Rostad lök" trots hyllkategorin "Torkad lök", men
    # släpper INTE igenom "lök" → "Rostad lök" (då saknas "rostad" i ingrediensen).
    ing_ord = set(re.findall(r"[a-zåäöéè]+", ing))
    namn_ord = re.findall(r"[a-zåäöéè]+", namn)
    if ing_ord and namn_ord and ing_ord <= set(namn_ord) and namn_ord[0] in ing_ord:
        return False
    if any(k in kat and k.strip() not in ing for k in _AVLEDDA_KATEGORIER):
        return True
    return any(f in namn and f not in ing for f in _AVLEDDA_FORMER)


def _giltig_kandidat(p: dict | None, diet: str | None, ing_namn: str = "") -> bool:
    """En kandidatprodukt är användbar om den finns, inte tillhör en non-food-
    avdelning, inte bryter mot dieten och inte är en avledd form (kaka/juice/...)
    av en råvaru-ingrediens."""
    return bool(p) and p.get("avdelning") not in _NONFOOD_AVDELNINGAR \
        and not _produkt_strider_mot_diet(p, diet) \
        and not _är_avledd_form(p, ing_namn)


def _aktuell_besparing(p: dict) -> float:
    """Hur mycket den här produkten är nedsatt JUST NU (0 om ingen kampanj)."""
    kampanj = _flyt(p.get("kampanjpris"))
    if kampanj is None:
        return 0.0
    ord_pris = _flyt(p.get("pris"))
    return max(0.0, ord_pris - kampanj) if ord_pris is not None else 0.0


# Ekologi-markörer i ICA:s sortiment: "ekologisk(t/a)", KRAV-märkning och ICA:s
# eko-varumärke "I Love Eco". "eko" ensamt är för kort/riskabelt (delsträng i
# t.ex. "ekorre", "rekord") → vi kräver hela ordet/frasen.
_EKO_MARKÖRER = ("ekologisk", "krav", "i love eco")


def _är_ekologisk(p: dict | None) -> bool:
    """True om produkten är ekologisk (namn/kategori/taggar nämner eko/KRAV/Eco)."""
    if not p:
        return False
    text = " ".join([
        p.get("namn") or "", p.get("kategori") or "",
        " ".join(p.get("taggar") or []),
    ]).lower()
    return any(m in text for m in _EKO_MARKÖRER)


# Stapel-kategorier (substräng på huvudkategorin) där ALLA varianter är fritt
# utbytbara mot varandra även om de inte delar något ord: pasta (penne↔spaghetti),
# kött- och fiskstyckningar (fläskkarré↔fläskkotlett, lax↔torsk). Här räcker SAMMA
# huvudkategori för ett byte. Övriga ingredienser kräver dessutom att kampanjvaran
# delar råvarans HUVUDORD (gul lök→rödlök, potatis→färskpotatis) — så ett byte
# aldrig blir konstigt (morot↛rabatterad rödbeta, äpple↛banan).
_STAPEL_KAT = (
    "pasta", "fläsk", "gris", "nötkött", "kött", "färs", "korv", "chark",
    "kyckling", "fågel", "kalkon", "lamm", "fisk", "lax", "torsk", "skaldjur",
    "räkor",
)
_kampanj_per_kat: dict | None = None


def _huvudkat(kategori: str) -> str:
    """Huvudkategori = första delen före komma ('Fläskkött, färsk' → 'fläskkött')."""
    return (kategori or "").lower().split(",")[0].strip()


def _kampanjindex(sök) -> dict:
    """Uppslag huvudkategori → produkter på kampanj just nu (byggs en gång per
    process; kampanjerna är desamma tills sortimentet laddas om vid omstart)."""
    global _kampanj_per_kat
    if _kampanj_per_kat is None:
        idx: dict = {}
        for p in sök.produkter:
            if _flyt(p.get("kampanjpris")) is None:
                continue
            idx.setdefault(_huvudkat(p.get("kategori", "")), []).append(p)
        _kampanj_per_kat = idx
    return _kampanj_per_kat


def _byt_till_kampanjvara(val: dict, sök, diet: str | None, ing_namn: str,
                          ekologiskt: bool = False) -> dict:
    """Byt den matchade produkten mot en KAMPANJVARA i SAMMA huvudkategori om den
    sparar mer — för ALLA ingredienser, men bara när bytet är en ÄKTA motsvarighet
    så rätten inte blir konstig. Två godkända fall (utöver samma huvudkategori +
    diet-/avledd-grind): (1) en stapel-kategori där alla varianter är utbytbara
    (kött/fisk/pasta: fläskkarré→fläskfilé, penne→spaghetti), eller (2) kampanjvaran
    namnger råvaran som ett HELT ORD (poäng >= 2: 'riven ost'→annan 'Riven Ost' på
    rea). Annars hoppas bytet över.

    En kampanjvara som bara har råvaran som SAMMANSÄTTNINGS-suffix (poäng 1) räcker
    INTE för icke-stapel-byten — då är det en egen smaksatt specialvara, inte en
    motsvarighet (riven ost↛Brännvinsost, gul lök↛rödlök). Det håller 'maximera
    kampanjer' till varor man faktiskt kan byta rakt av, så ingen rätt blir konstig.

    Fri stapel-byte tillåts BARA om grundmatchen verkligen REPRESENTERAR råvaran
    (råvaran är huvudordet i grundproduktens namn). Annars — svag/fel grundmatch
    (t.ex. "rökt paprikapulver" som fastnat på en chark-produkt) — krävs att
    kampanjvaran namnger råvaran, så ett byte inte förvärrar en redan fel match
    (paprikapulver↛salsiccia). Vid ekologiskt-önskemål byts bara till eko-varor."""
    huvudkat = _huvudkat(val.get("kategori", ""))
    if not huvudkat:
        return val
    huvud = _ingrediens_huvudord(ing_namn)
    stapel = any(o in huvudkat for o in _STAPEL_KAT)
    fri_stapel = stapel and _huvudord_poäng(val, huvud) >= 2
    bästa, bästa_besp = val, _aktuell_besparing(val)
    for kp in _kampanjindex(sök).get(huvudkat, []):
        if kp.get("id") == val.get("id") or not _giltig_kandidat(kp, diet, ing_namn):
            continue
        if ekologiskt and not _är_ekologisk(kp):
            continue                       # eko-önskemål → byt bara till eko-vara
        if not fri_stapel and _huvudord_poäng(kp, huvud) < 2:
            continue                       # ej stapel + namnger ej råvaran → konstigt byte
        besp = _aktuell_besparing(kp)
        if besp > bästa_besp:
            bästa, bästa_besp = kp, besp
    return bästa


# Brus i ingrediensnamn som stör fuzzy-matchningen mot sortimentet. Vi tar bort
# mängd/enhet/parentes/behållarord/alternativ — men INTE adjektiv/particip som kan
# definiera en egen produkt (rostad lök, torkad lök, riven ost) → de lämnas orörda.
_ING_PARENTES = re.compile(r"\([^)]*\)")
_ING_TAL_ENHET = re.compile(r"\b\d+[\d.,/]*\s*(?:g|kg|hg|dl|cl|ml|l|msk|tsk|krm|st|pkt|förp)?\b")
_ING_MÄNGDORD = re.compile(
    r"\b(?:à|ca|cirka|ungefär|drygt|knappt|förp|förpackning|paket|pkt|burk|burkar|"
    r"påse|påsar|knippe|knippen|bunt|buntar|nypa|stänk|skvätt)\b")
_ING_KVALIFICERARE = re.compile(
    r"\b(?:med|utan)\s+(?:skinn|ben|kärnor)\b|\b(?:urkärnad|i bitar|i klyftor|i skivor)\b")
# "smör till stekning" / "olja till formen" / "ägg till pensling" → råvaran;
# tillagnings-/serverings-svans bär ingen produktidentitet.
_ING_TILL = re.compile(r"\btill\s+.*$")
_ING_FILLER = re.compile(r"\b(?:ev|gärna|förslagsvis|t\s*ex)\b")
# Kvalitets-/sortord utan produktidentitet ("potatis av mjölig SORT", "lök av
# fast SLAG") — de drar matchningen mot fel varor (sort→"Compact Sort"-back) utan
# att beskriva råvaran. "av" är alltid preposition i ingredienslistor → ofarlig.
_ING_KVALITETSORD = re.compile(r"\b(?:av|sorter|sorters|sort|sorts|slags?|typ(?:er)?)\b")
# Alternativ-separatorer (eller/alt/alternativt//) → matcha varje för sig.
_ALT_SEP = re.compile(r"\s+(?:eller|alt|alternativt)\s+|\s*/\s*")


def _rensa_ingrediensnamn(namn: str) -> str:
    """Ta bort mängd/enhet/parentes/behållar-/svans-brus ur ett ingrediens-namn så
    matchningen ser RÅVARAN: 'ankbröst (à 600 g)'->'ankbröst', 'förp
    ankbröst'->'ankbröst', 'citron (rivet skal och saft)'->'citron', 'smör till
    stekning'->'smör'. 'alt/eller' lämnas kvar (huvudordet kan komma EFTER, t.ex.
    'hackad eller smält mjölkchoklad') → fuzzy-matchningen väljer den starkaste.
    Visningsnamnet (namn_ingrediens) lämnas orört."""
    s = (namn or "").lower()
    s = _ING_PARENTES.sub(" ", s)
    s = _ING_TILL.sub(" ", s)
    s = _ING_TAL_ENHET.sub(" ", s)
    s = _ING_MÄNGDORD.sub(" ", s)
    s = _ING_KVALIFICERARE.sub(" ", s)
    s = _ING_FILLER.sub(" ", s)
    s = _ING_KVALITETSORD.sub(" ", s)
    s = re.sub(r"[^a-zåäöéè\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _parentes_alternativ(namn: str) -> list[str]:
    """Råvaru-ALTERNATIV ur parenteser: 'skogssvamp (t ex karljohans eller
    kantareller)' → ['karljohans','kantareller']. _rensa_ingrediensnamn slänger
    parenteser, men en alternativ vara som FINNS i sortimentet (kantareller) bör
    komma med bland sökkandidaterna istället för att råvaran fastnar på skräp
    (skogssvamp→Servett 'Skog'). Bara parenteser som tydligt listar alternativ
    (eller/alt/t ex/gärna) tas med — inte mängd-/instruktionsparenteser
    ('(à 600 g)', '(rivet skal och saft)')."""
    ut: list[str] = []
    for grupp in re.findall(r"\(([^)]*)\)", (namn or "").lower()):
        if not re.search(r"\b(?:eller|alt|alternativt|t\s*ex|tex|gärna)\b", grupp):
            continue
        g = re.sub(r"\b(?:t\s*ex|tex|gärna|ca|ungefär|motsvarar)\b", " ", grupp)
        for del_ in re.split(r"\s*,\s*|" + _ALT_SEP.pattern, g):
            del_ = re.sub(r"[^a-zåäöéè\s]", " ", del_ or "").strip()
            if del_ and del_ not in ut:
                ut.append(del_)
    return ut


def _sök_termer(namn: str) -> list[str]:
    """Sökord för en ingrediens vid index-matchning: rensat helnamn + varje
    alternativ (eller/alt//) + parentes-alternativ + HUVUDORDET (sista alfaordet).
    Så prep-/behållar-brus ('finskuren gräslök'→gräslök, 'knippa dill'→dill, 'smör
    eller margarin'→smör+margarin) och parentes-alternativ ('svamp (t ex
    kantareller)'→kantareller) ändå hittar råvaran, utan ordlista. Helnamnet ligger
    kvar först → produktvarianter ('rostad lök'→Rostad lök) finns bland kandidat-
    erna och vinner på täcknings-/huvudord-omrankningen vid körning."""
    rensat = _rensa_ingrediensnamn(namn) or (namn or "").lower().strip()
    termer = [rensat]
    for del_ in _ALT_SEP.split(rensat):
        del_ = del_.strip()
        if del_ and del_ not in termer:
            termer.append(del_)
    for alt in _parentes_alternativ(namn):
        if alt not in termer:
            termer.append(alt)
    ord_ = re.findall(r"[a-zåäöéè]+", rensat)
    if ord_ and ord_[-1] not in termer:
        termer.append(ord_[-1])
    return termer


def _unika_ingredienser(recept: dict) -> list[dict]:
    """Receptingredienser med dubbletter borttagna. Samma råvara listas ofta i
    flera tillagningssteg (olivolja till stekning + till dressing, smör i deg +
    till stekning) — för en inköpslista räcker EN post, och priset ska inte
    dubbelräknas. Nyckel = rensat namn så 'olivolja' och 'olivolja 500ml' slås
    ihop; första förekomsten (med sin mängd) behålls."""
    sedda: set[str] = set()
    ut: list[dict] = []
    for ing in recept.get("ingredienser", []):
        nyckel = _rensa_ingrediensnamn(ing.get("namn", "")) or (ing.get("namn") or "").lower().strip()
        if nyckel in sedda:
            continue
        sedda.add(nyckel)
        ut.append(ing)
    return ut


def _ingrediens_huvudord(namn: str) -> str:
    """Råvarans huvudord = sista alfabetiska ordet (svenska sammansättningar har
    substantivet sist: 'hel vitlök'→vitlök, 'riven prästost'→prästost)."""
    ord = re.findall(r"[a-zåäöéè]+", (namn or "").lower())
    return ord[-1] if ord else ""


def _huvudord_poäng(produkt: dict, huvud: str) -> int:
    """Hur väl produktNAMNET har råvaran som huvudord. 3 = produkten HETER råvaran
    (Ägg…, Morot…, Vitlök…), 2 = råvaran är ett helt ord (…med vitlök), 1 = samman-
    sättning som ÄR en typ av råvaran (vetemjöl⊇mjöl, arborioris⊇ris), 0 = råvaran
    bara prefix av ett annat ord (äggvita, mjölkdryck, islåda) → ratas vid lika.
    Bryter delsträngs-bias i fuzzy-sökningen utan att röra själva sökmotorn."""
    if not huvud:
        return 0
    ord = re.findall(r"[a-zåäöéè]+", (produkt.get("namn") or "").lower())
    if not ord:
        return 0
    if ord[0] == huvud:
        return 3
    if huvud in ord:
        return 2
    if any(o.endswith(huvud) and len(o) > len(huvud) for o in ord):
        return 1
    # Råvaran är en SAMMANSÄTTNING/böjning vars BAS är produktnamnets huvudord
    # (citronsaft→Citron, limesaft→Lime, citroner→Citron, vitlöksklyfta→Vitlök):
    # produktens första ord är ett prefix-rot av huvudordet OCH resten är antingen
    # en böjning (-er/-ar...) eller ett eget morfem (>=3 tecken). Skiljer rätt
    # citron⊂citronsaft från fel mjöl⊂mjölk ('k' är varken böjning eller morfem) —
    # så en kampanjvara som bara råkar ha råvaran som icke-huvudord (lax m. citron)
    # inte fäller den faktiska basvaran via kampanj-tie-breaken.
    bas = ord[0]
    if len(bas) >= 4 and huvud.startswith(bas) and len(huvud) > len(bas):
        rest = huvud[len(bas):]
        if rest in _BÖJNINGS_SUFFIX or len(rest) >= 3:
            return 1
    return 0


def _matchad_produkt(ing: dict, sök, diet: str | None,
                     kampanj_läge: bool = False,
                     ekologiskt: bool = False) -> dict | None:
    """Den produkt en ingrediens ska prissättas/visas med — eller None. Sållar
    bort (a) skafferivaror (olja/salt/peppar), (b) för svaga fuzzy-träffar
    (skräpprodukter, < _MIN_MATCH_SCORE) och (c) produkter som bryter mot dieten.
    Bland de plausibla kandidaterna väljs den med STÖRST aktuell rabatt — så att
    veckans nedsatta varor (lammrack, flintastek...) driver fram fynd-rätterna
    istället för att en icke-nedsatt syskonprodukt låses fast vid indexering.
    En enda grind så att _prissatt och _till_matratt alltid är samstämmiga."""
    if _är_skafferi(ing.get("namn", "")):
        return None

    # Matcha mot RÅVARAN, inte mängd/parentes/kvalificerare ("ankbröst (à 600 g)").
    rensat = _rensa_ingrediensnamn(ing.get("namn", "")) or ing.get("namn", "")

    kandidater = ing.get("produkt_kandidater")
    if kandidater is None:
        # Äldre index utan kandidatlista → fall tillbaka på enskild top-1-träff.
        ms = ing.get("match_score")
        if ms is not None and ms < _MIN_MATCH_SCORE:    # äldre index saknar nyckeln → släpp igenom
            return None
        pid = ing.get("produkt_id")
        if not pid:
            return None
        p = sök.id_index.get(pid)
        return p if _giltig_kandidat(p, diet, rensat) else None

    # Nytt index: top-N kandidater. Behåll bara de tillräckligt starka och
    # diet-giltiga (kandidaterna kommer sorterade fallande på match_score från sök).
    giltiga: list[tuple[dict, float]] = []
    for k in kandidater:
        ms = k.get("score")
        if ms is not None and ms < _MIN_MATCH_SCORE:
            continue
        p = sök.id_index.get(k.get("id"))
        if _giltig_kandidat(p, diet, rensat):
            giltiga.append((p, ms if ms is not None else 100.0))
    if not giltiga:
        return None
    # Eko-önskemål: begränsa till ekologiska kandidater om någon finns (annars
    # behåll alla — bättre en konventionell träff än ingen vara alls).
    if ekologiskt:
        eko = [g for g in giltiga if _är_ekologisk(g[0])]
        if eko:
            giltiga = eko
    # Re-ranka kandidaterna på en (täckning, huvudord)-nyckel:
    #  • täckning = hur många av RÅVARANS ord produkten har som helt ord — så att en
    #    varietet som matchar hela råvaran ("Gul lök" för "gul lök") slår en annan
    #    varietet som bara delar huvudordet ("Lök röd").
    #  • huvudord = bryter delsträngs-biasen i fuzzy-sökningen (ägg→äggvita,
    #    mjöl→mjölkdryck, is→islåda) när täckningen är lika.
    # Stabil sort bevarar match_score-ordningen inom samma nyckel, och när ingen
    # kandidat sticker ut (alla lika) blir resultatet oförändrat = ofarlig fallback.
    huvud = _ingrediens_huvudord(rensat)
    ing_ord = set(re.findall(r"[a-zåäöéè]+", rensat.lower()))

    def _ranknyckel(p: dict) -> tuple[int, int]:
        pord = set(re.findall(r"[a-zåäöéè]+", (p.get("namn") or "").lower()))
        return (len(ing_ord & pord), _huvudord_poäng(p, huvud))

    rankade = sorted(
        ((p, score, _ranknyckel(p)) for p, score in giltiga),
        key=lambda t: t[2], reverse=True,
    )
    # Default = bästa namnmatchen i den bästa rank-gruppen. Kampanj är BARA en
    # tie-break bland kandidater med lika bra rank-nyckel OCH nästan lika bra
    # namnmatch (inom _KAMPANJ_MARGINAL) — annars skulle en nedsatt men sämre/fel
    # vara vinna (morot→morotskaka, ägg→äggvita).
    bäst_p, bäst_score, bäst_nyckel = rankade[0]
    val, val_besp = bäst_p, _aktuell_besparing(bäst_p)
    for p, score, nyckel in rankade[1:]:
        if nyckel < bäst_nyckel:
            break
        if score < bäst_score - _KAMPANJ_MARGINAL:
            continue
        besp = _aktuell_besparing(p)
        if besp > val_besp:
            val, val_besp = p, besp
    # Kampanjläge: låt ingrediensen byta till en kampanjvara (alla ingredienser,
    # vettig grind) om det sparar mer → rätten BYGGS på veckans fynd.
    if kampanj_läge:
        return _byt_till_kampanjvara(val, sök, diet, ing.get("namn", ""), ekologiskt)
    return val


# Namnmarkörer som visar att en rätt ÄR en växtbaserad variant — då är ett köttord
# i namnet bara imitationens namn ("Vegansk kyckling", "Vegobolognese") och
# ordliste-vetot ska INTE slå till.
_VEGO_MARKÖRER = ("vegansk", "vegan", "vego", "växtbaserad", "växtbaserat")

# Vego-prefixade FRASER ("växtbaserad ost", "vegansk kyckling", "vegobitar") tas
# bort INNAN ordliste-vetot skannar, så imitationsprodukter inte triggar kött/-
# fisk/ost-vetot. En FRISTÅENDE djurprodukt (alaska pollock, fisk i "fiskgratäng")
# utan vego-prefix står kvar och vetas korrekt. Matchar markören + ev. nästa ord.
_VEGO_FRAS = re.compile(r"(?:växtbasera\w*|vegansk\w*|vegan|vego)[\s-]*[a-zåäö]*")


def _ordlista_vetar(recept: dict, diet: str | None) -> bool:
    """True om recepttexten innehåller ett förbjudet kött/fisk/djur-ord. Skannar
    rättens NAMN + taggar + ingrediensnamn, så 'fiskgratäng' och 'äppelsill' fångas.
    Vego-prefixade fraser strippas först så imitationer ('vegansk kyckling') överlever.
    Pålitligaste signalen; används både som fallback för otaggade recept och som
    skyddsnät ovanpå LLM-taggen."""
    förbjudna = _DJUR if diet == "veganskt" else _KÖTT_FISK
    # Skannar NAMN + taggar + ingrediensnamn. Namnet tas med EXPLICIT eftersom
    # taggar inte alltid innehåller rättens namn (t.ex. "Fiskgratäng" slank igenom).
    text = (recept.get("namn", "") + " " + recept.get("taggar", "") + " " + " ".join(
        (ing.get("namn") or "") for ing in recept.get("ingredienser", [])
    )).lower()
    text = _VEGO_FRAS.sub(" ", text)
    if any(re.search(rf"\b{re.escape(ord)}", text) for ord in förbjudna):
        return True
    # Fisk inbäddad i sammansättning (äppelsill, wannameiräkor) — gäller båda dieter.
    if any(o in text for o in _INBÄDDAD_FISK):
        return True
    # Sammansatt ost (ädelostsallad, getost) har "ost" inbäddat → \bost missar dem.
    # För veganskt: avvisa "ost" var som helst UTOM efter "r" (så "rostad" överlever).
    if diet == "veganskt" and re.search(r"(?<!r)ost", text):
        return True
    return False


def _matchar_diet(recept: dict, diet: str | None) -> bool:
    if not diet:
        return True
    # Förbyggd diet-tagg (Haiku läste hela receptet offline) är PRIMÄR — en vegansk
    # rätt duger för både veganskt och vegetariskt, en vegetarisk bara för
    # vegetariskt. Men Haiku feltaggar ibland uppenbara fiskrätter (fiskgratäng,
    # äppelsill) som veg/vegan → kör ordliste-VETO ovanpå som skyddsnät. Vetot
    # strippar själv vego-prefixade fraser ("Vegansk kyckling") så imitationer
    # överlever men en fristående fisk/kött-produkt fastnar.
    tagg = recept.get("diet_tagg")
    if tagg:
        tillåten = tagg == "veganskt" if diet == "veganskt" else tagg in ("vegetariskt", "veganskt")
        if not tillåten:
            return False
        return not _ordlista_vetar(recept, diet)
    # Fallback för ännu otaggade recept: ren ordlista (skyddsnät).
    return not _ordlista_vetar(recept, diet)


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


# Drycker (cocktails/drinkar) saknar ofta kategori OCH har namn utan dryckesord
# (t.ex. "Aquapolitan") → varken kategori- eller namn-vetot fångar dem. En drink
# består dock till STÖRSTA delen av drycker/sprit; en middag som använder EN skvätt
# vin/konjak gör det inte. Vi flaggar därför recept där >=3 ingredienser är drycker.
_DRYCK_INGREDIENS = (
    "champagne", "prosecco", "mousserande", "vermouth", "sherry", "portvin",
    "brännvin", "vodka", "whisky", "whiskey", "bourbon", "rom (", "ljus rom",
    "mörk rom", "cognac", "konjak", "likör", "snaps", "akvavit", "aquavit",
    "tequila", "absint", "campari", "aperol",
    "club soda", "tonic", "sockerdricka", "sodavatten", "lemonad",
    "grapefruktjuice", "apelsinjuice", "ananasjuice", "tranbärsjuice",
    "lingondricka", "måltidsdryck", "glögg",
)


def _är_dryck(recept: dict) -> bool:
    """True om receptet är en drink/cocktail: minst tre ingredienser är drycker/sprit.
    En måltid med en skvätt vin/konjak triggar aldrig (för få dryckesingredienser)."""
    namn = [(ing.get("namn") or "").lower() for ing in recept.get("ingredienser", [])]
    antal = sum(1 for n in namn if any(d in n for d in _DRYCK_INGREDIENS))
    return antal >= 3


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
        # Premiera HELA korgens kampanjtäckning, inte bara EN stort rabatterad
        # vara: en rätt med flera kampanjvaror (eller hög total besparing) och
        # lågt slutpris ska vinna över en dyr rätt som råkar dela EN rabattvara.
        scored.sort(key=lambda s: (
            -(s["besparing"] + min(s["kampanjer"], 5) * 6), s["total"]))
    elif sortering == "kampanj":
        # Bäst KOMBINATION av kampanjvaror: störst relativ rabatt + flest fynd i
        # samma korg → måltider som blir rejält billigare än vanligt.
        scored.sort(key=lambda s: -s["kampanjpoäng"])
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


def _svårighet(recept: dict) -> str:
    """Grov svårighetsgrad härledd GRATIS ur antal steg + ingredienser + tid
    (ingen LLM). 'enkelt' / 'medel' / 'avancerat'. Trösklarna är gissningar —
    justera utifrån verkliga batchar."""
    steg = len(recept.get("instruktioner") or [])
    antal_ing = len(recept.get("ingredienser") or [])
    tid = _tid_min(recept) or 0
    poäng = steg + antal_ing * 0.4 + tid / 12
    if poäng <= 9:
        return "enkelt"
    if poäng <= 16:
        return "medel"
    return "avancerat"


# ─────────────────────────────────────────────
# ENRICHMENT → matratter-format (iOS oförändrad)
# ─────────────────────────────────────────────

def _bild_url(recept: dict) -> str:
    # Spegla lokalt BARA om filen faktiskt finns på disk (static/ kan ha rensats);
    # annars hotlinka ICA:s CDN (bild_url finns alltid i recept-datan).
    lokal = recept.get("bild_lokal")
    if lokal and os.path.exists(lokal.lstrip("/")):
        return f"{_BAS_URL}{lokal}" if lokal.startswith("/") else lokal
    return recept.get("bild_url") or ""


# ── Åtgång/rest: hur mycket av en köpt förpackning receptet faktiskt använder ──
# Recept anger fri-text-mängd ("2 dl", "200 g", "1 1/2 dl"); produktnamnet bär
# förpackningsstorleken ("Olivolja 500ml", "Färs 500g", "Ägg 20-p"). När båda
# går att tolka i SAMMA dimension (vikt/volym/antal) räknar vi ut hur många
# förpackningar man behöver + hur mycket som blir över efter matlagningen.
_VIKT = {"g": 1.0, "gram": 1.0, "hg": 100.0, "kg": 1000.0}
_VOLYM = {"ml": 1.0, "cl": 10.0, "dl": 100.0, "l": 1000.0, "liter": 1000.0,
          "msk": 15.0, "tsk": 5.0, "krm": 1.0}
_ANTAL = {"st": 1.0, "styck": 1.0, "stycken": 1.0}
_FRAK = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3, "⅛": 0.125}


def _enhet_dim(enhet: str):
    if enhet in _VIKT:  return "vikt", _VIKT[enhet]
    if enhet in _VOLYM: return "volym", _VOLYM[enhet]
    if enhet in _ANTAL: return "antal", _ANTAL[enhet]
    return None, None


def _parsa_tal(s: str):
    """'2', '2,5', '1/2', '2 1/2', '½' → float (None om ej tal)."""
    s = (s or "").strip()
    for f, v in _FRAK.items():
        s = s.replace(f, f" {v} ")
    s = s.strip()
    m = re.match(r"^(\d+)\s+(\d+)\s*/\s*(\d+)$", s)          # "2 1/2"
    if m: return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    m = re.match(r"^(\d+)\s*/\s*(\d+)$", s)                  # "1/2"
    if m: return int(m.group(1)) / int(m.group(2))
    m = re.match(r"^(\d+(?:[.,]\d+)?)(?:\s+(\d+(?:[.,]\d+)?))?$", s)  # "2", "2,5", "2 5"
    if m:
        tot = float(m.group(1).replace(",", "."))
        if m.group(2): tot += float(m.group(2).replace(",", "."))
        return tot
    return None


def _parsa_mängd(text: str):
    """Receptmängd → (mängd_i_basenhet, dim) annars (None, None)."""
    t = (text or "").lower().strip()
    m = re.search(r"([\d.,/\s½¼¾⅓⅔⅛]+?)\s*"
                  r"(kg|hg|gram|g|ml|cl|dl|liter|l|msk|tsk|krm|st|styck|stycken)\b", t)
    if not m: return None, None
    tal = _parsa_tal(m.group(1))
    if tal is None: return None, None
    dim, faktor = _enhet_dim(m.group(2))
    if not dim: return None, None
    return tal * faktor, dim


def _paket_storlek(namn: str):
    """Förpackningsstorlek ur produktnamn → (storlek_i_basenhet, dim) annars (None, None).
    'Olivolja 500ml'→(500,volym), 'Färs 500g'→(500,vikt), 'Ägg 20-p'→(20,antal)."""
    t = (namn or "").lower()
    bästa = None
    for m in re.finditer(r"(\d+(?:[.,]\d+)?)\s*(kg|hg|ml|cl|dl|liter|l|g)\b", t):
        tal = float(m.group(1).replace(",", "."))
        dim, faktor = _enhet_dim(m.group(2))
        if dim: bästa = (tal * faktor, dim)   # sista/mest specifika storleken vinner
    if bästa: return bästa
    m = re.search(r"(\d+)\s*-?\s*p\b", t)      # "20-p", "12 p"
    if m: return float(m.group(1)), "antal"
    return None, None


def _fmt_mängd(bas: float, dim: str) -> str:
    if dim == "vikt":
        return f"{bas / 1000:g} kg" if bas >= 1000 else f"{int(round(bas))} g"
    if dim == "volym":
        if bas >= 1000: return f"{bas / 1000:g} l"
        if bas >= 100 and bas % 100 == 0: return f"{int(bas / 100)} dl"
        return f"{int(round(bas))} ml"
    return f"{int(round(bas))} st"


def _åtgång(mangd: str, produktnamn: str) -> dict | None:
    """{antal_paket, rest, paket} om recept-mängd och förpackning går att jämföra
    i samma dimension, annars None. rest = vad som blir kvar efter matlagningen."""
    åt, d1 = _parsa_mängd(mangd)
    pak, d2 = _paket_storlek(produktnamn)
    if åt is None or pak is None or d1 != d2 or pak <= 0:
        return None
    antal = max(1, math.ceil(åt / pak))
    rest = antal * pak - åt
    return {
        "antal_paket": antal,
        "paket":       _fmt_mängd(pak, d2),
        "rest":        _fmt_mängd(rest, d2) if rest > 0 else None,
    }


def _anvand_andel(mangd: str, produktnamn: str) -> float:
    """Hur stor del av EN förpackning receptet använder (kan vara >1 vid flera
    förpackningar). Används för att VIKTA kampanj-besparingen: använder receptet
    bara en skvätt av en rabatterad storförpackning ska inte hela rabatten räknas
    som måltidens besparing. Returnerar 1.0 när mängd/förpackning inte går att
    jämföra (t.ex. '1 förp', hel styckning) → räkna då hela rabatten."""
    åt, d1 = _parsa_mängd(mangd)
    pak, d2 = _paket_storlek(produktnamn)
    if åt is None or pak is None or d1 != d2 or pak <= 0:
        return 1.0
    return åt / pak


def _till_matratt(recept: dict, sök, produkt_db: dict,
                  total: float, ordinarie: float, besparing: float,
                  diet: str | None = None, kampanj_läge: bool = False,
                  ekologiskt: bool = False) -> dict:
    ingredienser = []
    for ing in _unika_ingredienser(recept):
        # Samma grind som prissättningen: dölj skafferivaror, svaga fuzzy-träffar
        # och produkter som bryter mot dieten (olja→babyolja, peppar→pepparbiff,
        # kött i veg-rätt) → de visas som omatchade i inköpslistan.
        p = _matchad_produkt(ing, sök, diet, kampanj_läge, ekologiskt)
        pid = p.get("id") if p else None
        pos = produkt_db.get(pid) or {}
        mangd = _ing_mangd(ing)
        åtg = _åtgång(mangd, p.get("namn", "")) if p else None
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
            "skafferi":        _är_skafferi(ing.get("namn", "")),
            "antal_paket":     åtg["antal_paket"] if åtg else None,
            "paket":           åtg["paket"] if åtg else None,
            "rest":            åtg["rest"] if åtg else None,
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
        "recept_url":   recept.get("url"),
        "betyg":        recept.get("betyg"),
        "antal_betyg":  recept.get("antal_betyg"),
        "tid_min":      _tid_min(recept),
        "svårighet":    _svårighet(recept),
        "diet_tagg":    recept.get("diet_tagg"),
        "total_pris":   total,
        "ordinarie_pris": ordinarie,
        "besparing":    besparing,
        "ingredienser": ingredienser,
    }


def sok_recept(meddelande: str, karta: str = "hela_butiken",
               antal: int = 15, model: str = MODELL) -> dict:
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
    önskad_svårighet = filt.get("svårighet")
    vill_efterrätt = bool(filt.get("vill_efterrätt_dryck"))
    # I kampanjläget får varje ingrediens byta till en kampanjvara i samma
    # stapel-kategori (kött/fisk/pasta) → priser, ranking OCH inköpslista byggs
    # på veckans fynd. Påverkar inga andra sorteringar.
    kampanj_läge = (filt.get("sortering") == "kampanj")
    # Eko-önskemål: föredra ekologiska/KRAV-produkter vid varje ingrediens-match.
    ekologiskt = bool(filt.get("ekologiskt"))

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
            if _är_ej_måltid(r) or _är_dryck(r):
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
        # Svårighetsfilter: "enkelt" släpper bara enkla, "avancerat" bara
        # avancerade (recept med okänd tid/steg hamnar i "medel" → utesluts då).
        if önskad_svårighet and _svårighet(r) != önskad_svårighet:
            continue
        total, ordinarie, besparing, kampanjer, prissatta, viktad_besparing = \
            _prissatt(r, sök, diet, kampanj_läge, ekologiskt)
        # Inget matchat = tom inköpslista → värdelös träff i kund-flödet.
        if prissatta == 0:
            continue
        scored.append({
            "recept": r, "total": total, "ordinarie": ordinarie,
            "besparing": besparing, "viktad_besparing": viktad_besparing,
            "kampanjer": kampanjer, "prissatta": prissatta,
            "proteinkälla": _proteinkälla(r),
            # Ranking + visad besparing utgår från den VIKTADE besparingen → en
            # rätt vars enda fynd används till en skvätt rankas/visas inte som
            # storfynd.
            "kampanjpoäng": _kampanjpoäng(viktad_besparing, ordinarie, kampanjer,
                                          prissatta, total),
            "relevans": _relevans(r, filt, viktad_besparing, kampanjer,
                                  mättnadsbonus=not vill_efterrätt),
        })

    sortering = filt.get("sortering") or "relevans"
    # "Billigt"/besparing kräver att vi faktiskt kunnat prissätta receptet —
    # annars skulle oprissatta recept (total=0) felaktigt hamna överst.
    if sortering == "billigt":
        scored = [s for s in scored if s["total"] > 0]
    # "Kampanj": kunden vill ha rätter BYGGDA på kampanjvaror → kräv en RIKTIG
    # måltid som blir märkbart billigare än vanligt, mätt på den VIKTADE
    # besparingen, så en rätt som "sparar 20 kr" på en vara man bara använder en
    # skvätt av inte räknas som ett storfynd. Annars toppar tunna rätter där bara
    # en skafferivara (t.ex. smör) råkar vara på rea. Vi FÖREDRAR rätter som
    # kombinerar minst TRE kampanjfynd, men faller tillbaka till minst två om för
    # få sådana finns (annars blir listan i princip tom vissa veckor).
    elif sortering == "kampanj":
        # Föredra rätter byggda på MÅNGA kampanjfynd, men trappa ned kraven så
        # listan inte blir tom — särskilt för smala dieter (vegetariskt/veganskt)
        # där få recept råkar ha tre nedsatta varor samtidigt. Varje steg är en
        # supermängd av det föregående (lättar antingen antalet fynd eller, sista
        # steget, andelsgolvet). Vi tar det STRIKTASTE steg som ger nog med rätter,
        # annars det lösaste (sista) — så kunden alltid får en fyllig lista.
        def _kampanj_ok(s, min_kampanjer, kräv_golv):
            return (s["total"] > 0 and s["prissatta"] >= 3
                    and s["kampanjer"] >= min_kampanjer and s["ordinarie"] > 0
                    and (not kräv_golv
                         or s["viktad_besparing"] / s["ordinarie"] >= _MIN_KAMPANJANDEL))
        vald: list[dict] = []
        for min_k, golv in ((3, True), (2, True), (1, True), (1, False)):
            vald = [s for s in scored if _kampanj_ok(s, min_k, golv)]
            if len(vald) >= antal:
                break
        scored = vald

    _sortera(scored, sortering)
    # Sprid över proteinkällor så toppen inte blir t.ex. bara kyckling — men
    # bara när kunden INTE krävt en viss råvara (då ska alla träffar ha den).
    topp = scored[:antal] if med else _diversifiera(scored, antal)
    matratter = [
        _till_matratt(s["recept"], sök, produkt_db,
                      s["total"], s["ordinarie"], s["viktad_besparing"],
                      diet, kampanj_läge, ekologiskt)
        for s in topp
    ]
    return {"matratter": matratter}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "index":
        bygg_recept_index()
    elif len(sys.argv) > 1 and sys.argv[1] == "tagga":
        tagga_recept()
    else:
        fråga = sys.argv[1] if len(sys.argv) > 1 else "ge mig något billigt"
        import json as _j
        print(_j.dumps(sok_recept(fråga), ensure_ascii=False, indent=2)[:2000])

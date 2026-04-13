"""
sok.py  –  Puls-AR Smart Sökning
─────────────────────────────────────────────────────────────────────────────
Viktigaste regeln: Claude får BARA rekommendera produkter som faktiskt
finns i butikens databas. Aldrig hitta på egna förslag.

Tre söktyper:

  TYP 1  –  FUZZY NAMNMATCH  (ingen AI)
             "kechup" → "Felix Ketchup"
             Hanteras av RapidFuzz lokalt, snabbt och gratis.

  TYP 2  –  KONTEXTUELL SÖKNING  (Claude)
             "något som fungerar som soja i en marinad"
             "glutenfritt alternativ till pasta"
             "ingredienser till köttgryta"
             Claude ser butikens sortiment och väljer bland det.

Flöde:
    1. Fuzzy-match körs alltid först
    2. Om stark träff (≥75p) → returnera direkt, ingen Claude
    3. Annars → skicka till Claude med sortimentslistan

Integreras i server.py med:
    from sok import sök_router, sätt_databas
    app.include_router(sök_router)
─────────────────────────────────────────────────────────────────────────────
"""

import json
import anthropic
from rapidfuzz import fuzz, process, utils
from fastapi import APIRouter

# ─────────────────────────────────────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

FUZZY_DIREKT_TRÖSKEL = 75    # Poäng för att returnera direkt utan Claude
FUZZY_MÖJLIG_TRÖSKEL = 40    # Poäng för att skicka som kontext till Claude
MAX_RESULTAT         = 5     # Max antal produkter att returnera

# ─────────────────────────────────────────────────────────────────────────────
# INITIERING
# ─────────────────────────────────────────────────────────────────────────────

claude     = anthropic.Anthropic()
sök_router = APIRouter()

# Delas med server.py via sätt_databas()
_databas: dict = {}

def sätt_databas(databas: dict):
    """Kallas från server.py varje gång en produkt sparas eller tas bort."""
    global _databas
    _databas = databas


# ─────────────────────────────────────────────────────────────────────────────
# FUZZY-SÖKNING
# ─────────────────────────────────────────────────────────────────────────────

def fuzzy_sök(q: str) -> list[dict]:
    """
    Söker i databasen med fuzzy matching.
    Bygger en sökbar sträng per produkt: namn + varumärke + taggar.
    Returnerar träffar sorterade på relevans.
    """
    if not _databas:
        return []

    q_lower    = q.lower().strip()
    träffar    = []

    for prod in _databas.values():
        taggar_str = " ".join(prod.get("taggar", []))
        sökbar     = f"{prod.get('visningsnamn', '')} {prod.get('varumarke', '')} {taggar_str}"

        poäng = fuzz.token_set_ratio(
            q_lower,
            sökbar.lower(),
            processor=utils.default_process
        )

        if poäng >= FUZZY_MÖJLIG_TRÖSKEL:
            kopia          = dict(prod)
            kopia["_poäng"] = poäng
            träffar.append(kopia)

    träffar.sort(key=lambda p: p["_poäng"], reverse=True)
    return träffar[:MAX_RESULTAT]


# ─────────────────────────────────────────────────────────────────────────────
# CLAUDE-SÖKNING
# ─────────────────────────────────────────────────────────────────────────────

def bygg_sortimentslista() -> str:
    """
    Bygger en kompakt lista av butikens sortiment för Claude-prompten.
    Inkluderar status så Claude vet vad som faktiskt finns i lager.

    Format:
        - Felix Ketchup [I lager]
        - Heinz BBQ Sås [I lager]
        - Blå Band Béarnaisesås [Slut]
    """
    rader = []
    for prod in _databas.values():
        namn   = prod.get("visningsnamn", "")
        status = prod.get("status", "I lager")
        rader.append(f"- {namn} [{status}]")
    return "\n".join(sorted(rader))  # Alfabetisk ordning för läsbarhet


def claude_sök(q: str, fuzzy_förslag: list[dict]) -> dict:
    """
    Skickar sökningen till Claude tillsammans med butikens sortiment.

    Claude instrueras att:
    1. BARA rekommendera produkter från sortimentslistan
    2. Prioritera produkter med status "I lager"
    3. Förstå kontexten (marinad vs burgare ger olika substitut)
    4. Förklara varför varje produkt passar
    """
    sortiment = bygg_sortimentslista()

    # Fuzzy-förslag som extra ledtråd för Claude
    fuzzy_kontext = ""
    if fuzzy_förslag:
        namn = [p.get("visningsnamn", "") for p in fuzzy_förslag]
        fuzzy_kontext = f"""
Fuzzy-matchning hittade dessa möjliga träffar som kan vara relevanta:
{chr(10).join(f"- {n}" for n in namn)}
"""

    prompt = f"""Du är en hjälpsam assistent i en svensk matbutik (ICA Maxi).
En kund söker efter något och du ska hjälpa dem hitta rätt bland det butiken faktiskt har.

KUNDENS SÖKNING:
"{q}"
{fuzzy_kontext}
BUTIKENS SORTIMENT (dessa produkter och inga andra får du rekommendera):
{sortiment}

VIKTIGA REGLER:
1. Du får ENBART rekommendera produkter som finns i sortimentslistan ovan
2. Hittar du ingen bra match — säg det ärligt, hitta inte på produkter
3. Prioritera produkter med [I lager] framför [Slut]
4. Om kunden söker ett substitut — ta hänsyn till sammanhanget
   Exempel: "soja till marinad" → umami och salt är viktigt
            "soja till sushi" → smak och konsistens är viktigt
5. Förklara KORT på svenska varför varje produkt passar

Svara ENBART med JSON, inga backticks, inga förklaringar utanför JSON:
{{
    "typ": "direkt" | "substitut" | "filter" | "recept" | "ingen_match",
    "produkter": ["Exakt produktnamn från sortimentet", "..."],
    "förklaring": "Övergripande förklaring på svenska (max 2 meningar)",
    "per_produkt": {{
        "Exakt produktnamn": "Varför denna passar kundens behov"
    }}
}}"""

    try:
        resp = claude.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )

        text = resp.content[0].text.strip()
        # Ta bort backticks om Claude ändå lade till dem
        text = text.replace("```json", "").replace("```", "").strip()

        ai_svar = json.loads(text)

        # Slå upp fullständig produktdata för varje namn Claude returnerade
        # — detta garanterar att koordinater och all annan data följer med
        produkter = []
        per_produkt = ai_svar.get("per_produkt", {})

        for namn in ai_svar.get("produkter", []):
            # Fuzzy-match mot databasen för att hitta exakt rätt produkt
            # (Claude kan stava lite annorlunda än databasen)
            bästa_poäng = 0
            bästa_prod  = None

            for prod in _databas.values():
                poäng = fuzz.token_set_ratio(
                    namn.lower(),
                    prod.get("visningsnamn", "").lower(),
                    processor=utils.default_process
                )
                if poäng > bästa_poäng:
                    bästa_poäng = poäng
                    bästa_prod  = prod

            if bästa_prod and bästa_poäng >= 60:
                kopia = dict(bästa_prod)
                # Lägg till Claude's förklaring för just den här produkten
                kopia["_förklaring"] = per_produkt.get(namn, "")
                kopia["_poäng"]      = bästa_poäng
                produkter.append(kopia)

        return {
            "typ":        ai_svar.get("typ", "direkt"),
            "produkter":  produkter,
            "förklaring": ai_svar.get("förklaring", ""),
            "källa":      "claude"
        }

    except json.JSONDecodeError:
        # Claude svarade inte med ren JSON — fallback till fuzzy-resultaten
        return {
            "typ":        "direkt",
            "produkter":  fuzzy_förslag,
            "förklaring": "Liknande produkter i sortimentet",
            "källa":      "fuzzy_fallback"
        }

    except Exception as e:
        print(f"⚠️  Claude-sök fel: {e}")
        return {
            "typ":        "direkt",
            "produkter":  fuzzy_förslag,
            "förklaring": "",
            "källa":      "fuzzy_fallback"
        }


# ─────────────────────────────────────────────────────────────────────────────
# KLASSIFICERING — avgör om Claude behövs
# ─────────────────────────────────────────────────────────────────────────────

def behöver_claude(q: str) -> bool:
    """
    Kollar om sökningen innehåller nyckelord som kräver kontextuell förståelse.
    Om ja → Claude. Om nej → fuzzy räcker.
    """
    nyckelord = [
        "som fungerar som", "istället för", "alternativ", "ersätt",
        "liknande", "substitut", "billigare", "nyttigare", "hälsosammare",
        "glutenfri", "glutenfritt", "laktosfri", "laktosfritt",
        "vegansk", "veganskt", "vegetarisk", "sockerfri", "sockerfritt",
        "till", "recept", "ingrediens", "laga", "göra", "baka",
        "behöver", "vad kan", "finns det", "något som", "kan jag",
        "passar till", "använd", "används"
    ]
    q_lower = q.lower()
    return any(nyckelord in q_lower for nyckelord in nyckelord)


# ─────────────────────────────────────────────────────────────────────────────
# HUVUDFUNKTION
# ─────────────────────────────────────────────────────────────────────────────

def smart_sök(q: str) -> dict:
    """
    Huvudingång för all sökning.

    Returnerar alltid:
    {
        "typ":        str,
        "produkter":  [{ produktdata + _förklaring }],
        "förklaring": str,
        "källa":      "fuzzy" | "claude" | "fuzzy_fallback" | "ingen"
    }
    """
    q = q.strip()

    if not q:
        return {
            "typ":       "tom",
            "produkter": [],
            "förklaring": "",
            "källa":     "ingen"
        }

    # Steg 1 — fuzzy alltid först (gratis, snabbt)
    fuzzy_resultat = fuzzy_sök(q)

    # Steg 2 — stark fuzzy-träff, returnera direkt
    if fuzzy_resultat and fuzzy_resultat[0].get("_poäng", 0) >= FUZZY_DIREKT_TRÖSKEL:
        # Ta bort intern poäng-nyckel innan vi skickar ut
        for p in fuzzy_resultat:
            p.pop("_poäng", None)
        return {
            "typ":        "direkt",
            "produkter":  fuzzy_resultat,
            "förklaring": "",
            "källa":      "fuzzy"
        }

    # Steg 3 — kontextuell fråga → Claude
    if behöver_claude(q):
        resultat = claude_sök(q, fuzzy_förslag=fuzzy_resultat)
        for p in resultat.get("produkter", []):
            p.pop("_poäng", None)
        return resultat

    # Steg 4 — svag fuzzy-träff, inget Claude-nyckelord
    for p in fuzzy_resultat:
        p.pop("_poäng", None)
    return {
        "typ":        "direkt",
        "produkter":  fuzzy_resultat,
        "förklaring": "Liknande produkter i sortimentet" if fuzzy_resultat else "",
        "källa":      "fuzzy"
    }


# ─────────────────────────────────────────────────────────────────────────────
# FASTAPI ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

@sök_router.get("/sok")
def sök_endpoint(q: str = ""):
    """
    Smart sök-endpoint.

    Exempel:
        GET /sok?q=ketchup
        GET /sok?q=något som fungerar som soja i en marinad
        GET /sok?q=glutenfritt alternativ till pasta
        GET /sok?q=ingredienser till köttgryta
        GET /sok?q=billigare alternativ till Felix dressing
    """
    if not q:
        return {"fel": "Ange sökterm med ?q=..."}
    return smart_sök(q)
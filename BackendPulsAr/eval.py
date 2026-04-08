"""
eval.py  –  Puls-AR Modell-utvärdering
─────────────────────────────────────────────────────────────────
Kör scannern i eval-läge: visar exakt vad varje steg producerar,
hur väl Claude rättar OCR-fel, varumärkesmatch-kvot, tagg-kvalitet
och en sammanfattning i slutet.

Kör:
    python eval.py hylla.jpg
    python eval.py hylla.jpg --spara rapport.json
"""

import os
import sys
import json
import time
import argparse
import anthropic
import easyocr
import cv2
import numpy as np
from rapidfuzz import process, utils
from dataclasses import dataclass, field, asdict
from datetime import datetime

# ─────────────────────────────────────────────
# KONFIGURATION (samma som scanner.py)
# ─────────────────────────────────────────────
OCR_CONFIDENCE  = 0.30
BRAND_SCORE     = 78
Y_GROUP_PIXELS  = 50

BRANDS = [
    "Arla", "Garant", "Kungsörnen", "ICA", "Skånemejerier", "Pågen",
    "Felix", "Abba", "Zeta", "Santa Maria", "Scan", "Oatly",
    "Fazer", "Findus", "Knorr", "Nestlé", "Heinz", "Kellog",
    "Barilla", "President", "Valio", "Alpro", "Ramlösa", "Loka",
    "Estrella", "OLW", "Carlsberg", "Pripps", "Norrlands",
]

# ─────────────────────────────────────────────
# DATASTRUKTURER
# ─────────────────────────────────────────────

@dataclass
class ProduktResultat:
    grupp_index:       int
    råtext:            list[str]          # vad OCR faktiskt läste
    filtrerad_råtext:  list[str]          # efter tillit-filter
    claude_namn:       str                # vad Claude kallar produkten
    varumarke:         str                # fuzzy-matchat märke
    varumarke_score:   float              # hur säker matchningen var
    taggar:            list[str]
    ocr_conf_snitt:    float              # snittillit för OCR i gruppen
    claude_ändrade:    bool               # rättade Claude något?
    tid_ms:            float              # hur lång tid tog gruppen


@dataclass
class EvalRapport:
    bild:              str
    datum:             str
    total_tid_s:       float
    ocr_strängar:      int                # totalt antal strängar OCR hittade
    grupper_totalt:    int
    produkter_hittade: int
    märke_matchat:     int
    märke_ej_matchat:  int
    claude_rättelser:  int                # hur många gånger Claude ändrade råtexten
    snitt_taggar:      float
    snitt_ocr_conf:    float
    produkter:         list[dict] = field(default_factory=list)


# ─────────────────────────────────────────────
# INITIERING
# ─────────────────────────────────────────────
print("🔬 Puls-AR Eval startar...")
print("   Laddar EasyOCR...")
reader = easyocr.Reader(['sv', 'en'], gpu=True)
claude_client = anthropic.Anthropic()
print("   ✅ Redo!\n")


# ─────────────────────────────────────────────
# BILDFÖRBEHANDLING (identisk med scanner.py)
# ─────────────────────────────────────────────

def förbehandla_bild(bildpath: str) -> str:
    img     = cv2.imread(bildpath)
    lab     = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe   = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l       = clahe.apply(l)
    img     = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    gaussian = cv2.GaussianBlur(img, (0, 0), sigmaX=2.0)
    img     = cv2.addWeighted(img, 1.6, gaussian, -0.6, 0)
    img     = cv2.bilateralFilter(img, d=5, sigmaColor=55, sigmaSpace=55)
    temp    = bildpath.replace(".", "_eval_preprocessed.")
    cv2.imwrite(temp, img)
    return temp

def gruppera_efter_y(ocr_results: list) -> list:
    if not ocr_results:
        return []
    sorterad = sorted(ocr_results, key=lambda r: r[0][0][1])
    grupper, aktuell = [], [sorterad[0]]
    for item in sorterad[1:]:
        if abs(item[0][0][1] - aktuell[-1][0][0][1]) <= Y_GROUP_PIXELS:
            aktuell.append(item)
        else:
            grupper.append(aktuell)
            aktuell = [item]
    grupper.append(aktuell)
    return grupper

def slug(text: str) -> str:
    ersätt = {"å": "a", "ä": "a", "ö": "o", "Å": "A", "Ä": "A", "Ö": "O"}
    t = text.lower()
    for k, v in ersätt.items():
        t = t.replace(k, v)
    return "".join(c if c.isalnum() else "-" for c in t).strip("-")


# ─────────────────────────────────────────────
# EVAL-PIPELINE
# ─────────────────────────────────────────────

def extrahera_produktnamn_eval(ocr_strängar: list[str]) -> tuple[str | None, bool]:
    """
    Returnerar (namn, claude_ändrade).
    claude_ändrade = True om Claude returnerade något annat än råtexten.
    """
    if not ocr_strängar:
        return None, False
    if len(ocr_strängar) == 1:
        return ocr_strängar[0], False

    råkonkat = " ".join(ocr_strängar).strip()

    prompt = f"""Du analyserar text som en OCR-scanner läste av en svensk matvaruförpackning.

OCR-text (kan innehålla stavfel och skräp):
{json.dumps(ocr_strängar, ensure_ascii=False)}

Din uppgift:
1. Ignorera förpackningstext: ingredienser, näringsvärde, volym, vikt, datum, juridik, återvinning, "öppnas här" etc.
2. Rätta uppenbara OCR-stavfel (t.ex. "Tom4tsås" → "Tomatsås", "Aria" → "Arla")
3. Returnera ENBART produktnamnet på svenska, t.ex. "Arla Mellanmjölk" eller "Felix Tomatsås"

Svara med ENBART produktnamnet. Inga förklaringar. Inga citattecken."""

    try:
        resp  = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=60,
            messages=[{"role": "user", "content": prompt}]
        )
        namn = resp.content[0].text.strip().strip('"').strip("'")
        if namn and len(namn) < 80:
            ändrade = namn.lower() != råkonkat.lower()
            return namn, ändrade
    except Exception as e:
        print(f"      ⚠️  Claude-fel: {e}")

    return max(ocr_strängar, key=len), False


def generera_taggar_eval(visningsnamn: str, varumarke: str) -> list[str]:
    prompt = f"""Du hjälper en svensk matbutiks AR-app.
Produkt: "{visningsnamn}"
Varumärke: "{varumarke}"

Ge mig en JSON-lista med 6–10 svenska söktermer. Svara ENBART med en JSON-array."""
    try:
        resp   = claude_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}]
        )
        taggar = json.loads(resp.content[0].text.strip())
        return [t.lower() for t in taggar if isinstance(t, str)]
    except Exception:
        return [visningsnamn.lower()]


def analysera_grupp(grupp: list, index: int) -> ProduktResultat | None:
    t_start = time.time()

    råtext = [text for (_, text, _) in grupp]
    konf   = [conf for (_, _, conf) in grupp]

    # Tillit-filter
    filtrerad = [
        text for (_, text, conf) in grupp
        if conf >= OCR_CONFIDENCE and len(text.strip()) > 1
    ]
    if not filtrerad:
        return None

    snitt_conf = sum(konf) / len(konf)

    # Claude-namnfilter
    namn, ändrade = extrahera_produktnamn_eval(filtrerad)
    if not namn:
        return None

    # Varumärkesmatch
    varumarke       = ""
    varumarke_score = 0.0
    for ord in namn.split():
        m = process.extractOne(ord, BRANDS, processor=utils.default_process)
        if m and m[1] >= BRAND_SCORE:
            varumarke       = m[0]
            varumarke_score = m[1]
            break

    # Taggar
    taggar = generera_taggar_eval(namn, varumarke)

    tid_ms = (time.time() - t_start) * 1000

    return ProduktResultat(
        grupp_index       = index,
        råtext            = råtext,
        filtrerad_råtext  = filtrerad,
        claude_namn       = namn,
        varumarke         = varumarke,
        varumarke_score   = varumarke_score,
        taggar            = taggar,
        ocr_conf_snitt    = round(snitt_conf, 3),
        claude_ändrade    = ändrade,
        tid_ms            = round(tid_ms, 1),
    )


# ─────────────────────────────────────────────
# UTSKRIFT
# ─────────────────────────────────────────────

GRÖN   = "\033[92m"
GUL    = "\033[93m"
RÖD    = "\033[91m"
BLÅ    = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def färg_conf(score: float) -> str:
    if score >= 0.6: return f"{GRÖN}{score:.2f}{RESET}"
    if score >= 0.35: return f"{GUL}{score:.2f}{RESET}"
    return f"{RÖD}{score:.2f}{RESET}"

def färg_märke(märke: str, score: float) -> str:
    if märke:
        return f"{GRÖN}{märke} ({score:.0f}%){RESET}"
    return f"{RÖD}(okänt märke){RESET}"

def skriv_produkt(res: ProduktResultat, num: int, total: int):
    status = f"{GRÖN}✅{RESET}" if res.varumarke else f"{GUL}⚠️ {RESET}"
    print(f"\n{BOLD}[{num}/{total}] {status} {res.claude_namn}{RESET}")

    # Visa om Claude rättade något
    råkonkat = " | ".join(res.råtext)
    if res.claude_ändrade:
        print(f"  📝 OCR råtext:   {GUL}{råkonkat[:90]}{RESET}")
        print(f"  ✏️  Claude fixade: {GRÖN}{res.claude_namn}{RESET}  ← rättade stavfel/skräp")
    else:
        print(f"  📝 OCR råtext:   {råkonkat[:90]}")
        print(f"  ✏️  Claude ändrade: ingenting (råtext var redan ren)")

    print(f"  🏢 Varumärke:    {färg_märke(res.varumarke, res.varumarke_score)}")
    print(f"  📊 OCR-tillit:   snitt {färg_conf(res.ocr_conf_snitt)}  "
          f"(filter: >{OCR_CONFIDENCE})")
    print(f"  🏷️  Taggar ({len(res.taggar)}):  {', '.join(res.taggar)}")
    print(f"  ⏱️  Tid:          {res.tid_ms:.0f}ms")


def skriv_sammanfattning(rapport: EvalRapport):
    tot = rapport.produkter_hittade
    print(f"\n{'═'*55}")
    print(f"{BOLD}📊 SAMMANFATTNING  —  {rapport.bild}{RESET}")
    print(f"{'═'*55}")

    print(f"  OCR-strängar totalt:     {rapport.ocr_strängar}")
    print(f"  Produktgrupper:          {rapport.grupper_totalt}")
    print(f"  Produkter identifierade: {BOLD}{rapport.produkter_hittade}{RESET}")

    if tot > 0:
        märke_pct = rapport.märke_matchat / tot * 100
        märke_färg = GRÖN if märke_pct >= 70 else GUL if märke_pct >= 40 else RÖD
        print(f"  Varumärke matchat:       "
              f"{märke_färg}{rapport.märke_matchat}/{tot} ({märke_pct:.0f}%){RESET}")

        rät_pct = rapport.claude_rättelser / tot * 100
        print(f"  Claude rättade stavfel:  {rapport.claude_rättelser}/{tot} ({rät_pct:.0f}%)")
        print(f"  Snitt taggar/produkt:    {rapport.snitt_taggar:.1f}")
        print(f"  Snitt OCR-tillit:        {rapport.snitt_ocr_conf:.2f}  "
              f"(1.0 = perfekt)")

    print(f"  Total körtid:            {rapport.total_tid_s:.1f}s")
    print(f"{'═'*55}")

    # Råd baserat på resultaten
    print(f"\n{BOLD}💡 Rekommendationer:{RESET}")
    if tot == 0:
        print(f"  {RÖD}• Inga produkter hittades — kontrollera bildkvalitet "
              f"och OCR_CONFIDENCE-tröskel{RESET}")
    else:
        if rapport.märke_matchat / tot < 0.5:
            print(f"  {GUL}• Låg varumärkesmatchning — lägg till fler märken "
                  f"i BRANDS-listan i scanner.py{RESET}")
        if rapport.snitt_ocr_conf < 0.45:
            print(f"  {GUL}• Låg OCR-tillit — pröva bättre belysning eller "
                  f"högre upplösning{RESET}")
        if rapport.claude_rättelser / max(tot, 1) > 0.6:
            print(f"  {GUL}• Claude rättar mycket — OCR kämpar, "
                  f"överväg att öka bildkontrasten{RESET}")
        if rapport.snitt_taggar < 5:
            print(f"  {GUL}• Få taggar genereras — kontrollera Claude API-anslutning{RESET}")
        if rapport.märke_matchat / max(tot, 1) >= 0.7 and rapport.snitt_ocr_conf >= 0.5:
            print(f"  {GRÖN}• Modellen ser bra ut! Redo för nästa steg.{RESET}")
    print()


# ─────────────────────────────────────────────
# HUVUDFUNKTION
# ─────────────────────────────────────────────

def kör_eval(bildpath: str, spara_till: str | None = None):
    if not os.path.exists(bildpath):
        print(f"❌ Bilden '{bildpath}' hittades inte!")
        sys.exit(1)

    t_start_total = time.time()
    img           = cv2.imread(bildpath)
    höjd, bredd   = img.shape[:2]

    print(f"📷 Bild: {bildpath}  ({bredd}×{höjd}px)\n")
    print("🎨 Förbehandlar bild...")
    temp_path = förbehandla_bild(bildpath)

    print("🔍 Kör OCR...")
    alla = reader.readtext(temp_path)
    print(f"   {len(alla)} textsträngar hittade.\n")

    grupper = gruppera_efter_y(alla)
    print(f"📦 {len(grupper)} produktgrupper att analysera.\n")
    print("═" * 55)

    resultat: list[ProduktResultat] = []

    for i, grupp in enumerate(grupper):
        print(f"  Analyserar grupp {i+1}/{len(grupper)}...", end="\r")
        res = analysera_grupp(grupp, i + 1)
        if res:
            resultat.append(res)
            skriv_produkt(res, len(resultat), len(grupper))

    total_tid = time.time() - t_start_total

    # Bygg rapport
    hittade = len(resultat)
    rapport = EvalRapport(
        bild              = bildpath,
        datum             = datetime.now().strftime("%Y-%m-%d %H:%M"),
        total_tid_s       = round(total_tid, 2),
        ocr_strängar      = len(alla),
        grupper_totalt    = len(grupper),
        produkter_hittade = hittade,
        märke_matchat     = sum(1 for r in resultat if r.varumarke),
        märke_ej_matchat  = sum(1 for r in resultat if not r.varumarke),
        claude_rättelser  = sum(1 for r in resultat if r.claude_ändrade),
        snitt_taggar      = round(sum(len(r.taggar) for r in resultat) / max(hittade, 1), 1),
        snitt_ocr_conf    = round(sum(r.ocr_conf_snitt for r in resultat) / max(hittade, 1), 3),
        produkter         = [asdict(r) for r in resultat],
    )

    skriv_sammanfattning(rapport)

    # Spara JSON om begärt
    if spara_till:
        with open(spara_till, "w", encoding="utf-8") as f:
            json.dump(asdict(rapport), f, ensure_ascii=False, indent=2)
        print(f"💾 Rapport sparad: {spara_till}\n")

    # Städa temp-fil
    if os.path.exists(temp_path):
        os.remove(temp_path)


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Puls-AR Modell-utvärdering")
    parser.add_argument("bild", nargs="?", default="hylla.jpg")
    parser.add_argument("--spara", metavar="FIL",
                        help="Spara detaljerad rapport som JSON (t.ex. rapport.json)")
    args = parser.parse_args()

    kör_eval(args.bild, spara_till=args.spara)
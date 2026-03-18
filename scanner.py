"""
scanner.py  –  Puls-AR Vision v8
─────────────────────────────────────────────────────────────────
Förbättringar mot v7:
  1. vLLM istället för Ollama — utnyttjar 5090:an maximalt
  2. Parallell inference — alla rutor processas samtidigt
  3. 8×8 rutnät (64 rutor) — varje ruta ≈ en produkt
  4. Deduplicering — samma produkt sparas bara en gång

Kör:
    python scanner.py
    python scanner.py IMG_5432.jpeg --dry-run
    python scanner.py IMG_5432.jpeg --rader 6 --kolumner 6
"""

import os
import sys
import json
import argparse
import base64
import concurrent.futures
import requests
import anthropic
import cv2
import numpy as np
from produktdb import slå_upp_produkt

# ─────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────
SERVER_URL      = "http://127.0.0.1:8000/produkt/"
VLLM_URL        = "http://127.0.0.1:8001/v1/chat/completions"
MODELL          = "Qwen/Qwen2.5-VL-7B-Instruct"   # byt till 72B om du har VRAM
MAX_WORKERS     = 16      # antal parallella Qwen-anrop
RADER           = 8      # rutnätets höjd
KOLUMNER        = 8      # rutnätets bredd
MIN_CONF        = 0.0    # alla rutor skickas till Qwen


# ─────────────────────────────────────────────
# INITIERING
# ─────────────────────────────────────────────
print("🚀 Puls-AR Scanner v8 startar...")

# Kolla om vLLM körs
vllm_tillgänglig = False
try:
    r = requests.get("http://127.0.0.1:8001/health", timeout=2)
    if r.status_code == 200:
        vllm_tillgänglig = True
        print("   ✅ vLLM online")
except Exception:
    pass

# Fallback till Ollama om vLLM inte körs
if not vllm_tillgänglig:
    print("   ⚠️  vLLM inte igång — faller tillbaka på Ollama")
    print("   💡 Starta vLLM med: python start_vllm.py")
    OLLAMA_URL   = "http://127.0.0.1:11434/api/generate"
    OLLAMA_MODELL = "qwen2.5vl"
    try:
        requests.get("http://127.0.0.1:11434", timeout=2)
        print("   ✅ Ollama online (fallback)")
    except Exception:
        print("   ❌ Varken vLLM eller Ollama svarar!")
        sys.exit(1)

claude = anthropic.Anthropic()
print("   ✅ Claude API redo\n")


# ─────────────────────────────────────────────
# BILDFÖRBEHANDLING
# ─────────────────────────────────────────────

def förbehandla_bild(bildpath: str) -> np.ndarray:
    img      = cv2.imread(bildpath)
    lab      = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b  = cv2.split(lab)
    clahe    = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l        = clahe.apply(l)
    img      = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    gaussian = cv2.GaussianBlur(img, (0, 0), sigmaX=2.0)
    img      = cv2.addWeighted(img, 1.6, gaussian, -0.6, 0)
    img      = cv2.bilateralFilter(img, d=5, sigmaColor=55, sigmaSpace=55)
    return img


# ─────────────────────────────────────────────
# RUTNÄT
# ─────────────────────────────────────────────

def dela_i_rutnät(img: np.ndarray, rader: int, kolumner: int) -> list[tuple]:
    """Delar bilden i rader×kolumner rutor med lite överlapp."""
    h, w      = img.shape[:2]
    överlapp  = 0.1   # 10% överlapp mellan rutor för att inte missa kanter
    ruta_h    = h // rader
    ruta_w    = w // kolumner
    pad_h     = int(ruta_h * överlapp)
    pad_w     = int(ruta_w * överlapp)

    boxar = []
    for r in range(rader):
        for k in range(kolumner):
            x1 = max(0, k * ruta_w - pad_w)
            y1 = max(0, r * ruta_h - pad_h)
            x2 = min(w, (k + 1) * ruta_w + pad_w)
            y2 = min(h, (r + 1) * ruta_h + pad_h)
            boxar.append((x1, y1, x2, y2))

    return boxar


# ─────────────────────────────────────────────
# QWEN VIA vLLM  (snabb, parallell)
# ─────────────────────────────────────────────

def img_till_base64(img_array: np.ndarray) -> str:
    # Skala ner till max 512px för snabbare inference
    h, w = img_array.shape[:2]
    if max(h, w) > 512:
        skala      = 512 / max(h, w)
        img_array  = cv2.resize(img_array, (int(w*skala), int(h*skala)))
    _, buf = cv2.imencode(".jpg", img_array, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf).decode("utf-8")

def fråga_qwen_vllm(crop: np.ndarray, ruta_index: int) -> str | None:
    """Anropar vLLM med OpenAI-kompatibelt API."""
    b64 = img_till_base64(crop)

    payload = {
        "model": MODELL,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                },
                {
                    "type": "text",
                    "text": (
                        "This is a section of a Swedish grocery store shelf. "
                        "What product or products do you see? "
                        "Reply with ONLY the Swedish product name(s), one per line. "
                        "Example: 'Felix Dressing Caesar' or 'Tabasco Röd'. "
                        "If the section is empty or unclear, reply: OKÄND"
                    )
                }
            ]
        }],
        "max_tokens": 100,
        "temperature": 0.1,
    }

    try:
        resp = requests.post(VLLM_URL, json=payload, timeout=30)
        resp.raise_for_status()
        svar = resp.json()["choices"][0]["message"]["content"].strip()
        if svar and "OKÄND" not in svar.upper():
            return svar
    except Exception as e:
        print(f"   ⚠️  vLLM-fel (ruta {ruta_index}): {e}")

    return None

def fråga_qwen_ollama(crop: np.ndarray, ruta_index: int) -> str | None:
    """Fallback till Ollama om vLLM inte körs."""
    b64 = img_till_base64(crop)
    payload = {
        "model":   OLLAMA_MODELL,
        "prompt":  (
            "This is a section of a Swedish grocery store shelf. "
            "What product do you see? Reply with ONLY the Swedish product name. "
            "Example: 'Felix Dressing Caesar'. If unclear, reply: OKÄND"
        ),
        "images":  [b64],
        "stream":  False,
        "options": {"temperature": 0.1},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
        svar = resp.json().get("response", "").strip()
        if svar and "OKÄND" not in svar.upper() and len(svar) < 100:
            return svar
    except Exception as e:
        print(f"   ⚠️  Ollama-fel (ruta {ruta_index}): {e}")
    return None

def fråga_qwen(crop: np.ndarray, ruta_index: int) -> str | None:
    """Väljer vLLM eller Ollama automatiskt."""
    if vllm_tillgänglig:
        return fråga_qwen_vllm(crop, ruta_index)
    return fråga_qwen_ollama(crop, ruta_index)


# ─────────────────────────────────────────────
# PARALLELL INFERENCE
# ─────────────────────────────────────────────

def analysera_ruta(args: tuple) -> dict | None:
    """Analyserar en enskild ruta — körs parallellt."""
    i, box, img = args
    x1, y1, x2, y2 = box

    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        return None

    svar = fråga_qwen(crop, i)
    if not svar:
        return None

    # Hantera flera produkter per ruta (en per rad)
    produktnamn = svar.split("\n")[0].strip()   # ta första raden
    if not produktnamn or len(produktnamn) < 2:
        return None

    return {
        "ruta":      i,
        "box":       box,
        "qwen_svar": produktnamn,
    }


# ─────────────────────────────────────────────
# HJÄLPFUNKTIONER
# ─────────────────────────────────────────────

def slug(text: str) -> str:
    ersätt = {"å": "a", "ä": "a", "ö": "o", "Å": "A", "Ä": "A", "Ö": "O"}
    t = text.lower()
    for k, v in ersätt.items():
        t = t.replace(k, v)
    return "".join(c if c.isalnum() else "-" for c in t).strip("-")

def generera_taggar(kanoniskt_namn: str, varumarke: str, kategori: str, db_taggar: list) -> list[str]:
    """Använder Claude för taggar om API-nyckeln finns, annars db-taggar."""
    if db_taggar:
        return db_taggar   # använd taggar från produktdb direkt

    prompt = f"""Produkt: "{kanoniskt_namn}", Varumärke: "{varumarke}", Kategori: "{kategori}"
Ge 6-8 svenska söktermer som JSON-array. Svara ENBART med arrayen."""
    try:
        resp   = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        taggar = json.loads(resp.content[0].text.strip())
        return [t.lower() for t in taggar if isinstance(t, str)]
    except Exception:
        return list(filter(None, [kanoniskt_namn.lower(), varumarke.lower(), kategori.lower()]))


# ─────────────────────────────────────────────
# SERVER
# ─────────────────────────────────────────────

def skicka_till_server(payload: dict, dry_run: bool = False):
    if dry_run:
        print(f"   [DRY-RUN] {payload['visningsnamn']} @ ({payload['x']:.2f}, {payload['y']:.2f})")
        return
    try:
        resp = requests.post(SERVER_URL, json=payload, timeout=3)
        if resp.status_code == 200:
            print(f"   📡 {resp.json().get('message', 'OK')}")
        else:
            print(f"   ⚠️  Server {resp.status_code}")
    except requests.exceptions.ConnectionError:
        print("   ⚠️  Ingen serveranslutning — kör server.py?")
    except Exception as e:
        print(f"   ⚠️  {e}")


# ─────────────────────────────────────────────
# HUVUDFUNKTION
# ─────────────────────────────────────────────

def skanna_bild(bildpath: str, rader: int, kolumner: int,
                dry_run: bool = False, hoppa_över_förbehandling: bool = False):
    if not os.path.exists(bildpath):
        print(f"❌ '{bildpath}' hittades inte!")
        sys.exit(1)

    original        = cv2.imread(bildpath)
    bildhöjd, bildbredd = original.shape[:2]
    print(f"📷 Bild: {bildpath}  ({bildbredd}×{bildhöjd}px)")
    print(f"📐 Rutnät: {rader}×{kolumner} = {rader*kolumner} rutor\n")

    img = original if hoppa_över_förbehandling else förbehandla_bild(bildpath)
    if not hoppa_över_förbehandling:
        print("🎨 Förbehandlad ✅\n")

    boxar = dela_i_rutnät(img, rader, kolumner)

    # ── Parallell inference ──────────────────────────────
    print(f"🤖 Kör Qwen på {len(boxar)} rutor parallellt (workers: {MAX_WORKERS})...\n")

    args_lista = [(i+1, box, img) for i, box in enumerate(boxar)]
    råa_resultat = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(analysera_ruta, args): args[0] for args in args_lista}
        for future in concurrent.futures.as_completed(futures):
            ruta_nr = futures[future]
            try:
                res = future.result()
                if res:
                    råa_resultat.append(res)
                    print(f"   [{ruta_nr:2}/{len(boxar)}] 👁️  {res['qwen_svar']}")
                else:
                    print(f"   [{ruta_nr:2}/{len(boxar)}] ⚪ Ingen produkt")
            except Exception as e:
                print(f"   [{ruta_nr:2}/{len(boxar)}] ⚠️  Fel: {e}")

    print(f"\n📦 {len(råa_resultat)} rutor med produkter — matchar mot databas...\n")
    print("=" * 55)

    # ── Matcha och deduplicera ───────────────────────────
    sparade    = {}   # id → payload  (undviker dubletter)

    for res in sorted(råa_resultat, key=lambda r: r["ruta"]):
        qwen_namn = res["qwen_svar"]
        x1, y1, x2, y2 = res["box"]

        off = slå_upp_produkt(qwen_namn)
        kanoniskt  = off["kanoniskt_namn"]
        varumarke  = off["varumarke"]
        kategori   = off["kategori"]
        db_taggar  = off.get("taggar", [])
        prod_id    = slug(kanoniskt)

        # Om vi redan sparat den här produkten — lägg bara till som alias
        if prod_id in sparade:
            if qwen_namn not in sparade[prod_id]["ocr_alias"]:
                sparade[prod_id]["ocr_alias"].append(qwen_namn)
            print(f"⏭️  Dubblett: '{kanoniskt}' — lägger till alias")
            continue

        taggar = generera_taggar(kanoniskt, varumarke, kategori, db_taggar)

        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        payload = {
            "id":             prod_id,
            "visningsnamn":   kanoniskt,
            "varumarke":      varumarke,
            "kategori":       kategori,
            "taggar":         taggar,
            "ocr_alias":      [qwen_namn],
            "x":              round(cx / bildbredd, 4),
            "y":              round(cy / bildhöjd,  4),
            "z":              2.5,
            "status":         "I lager",
            "off_verifierad": off["off_hittad"],
        }

        print(f"✅ {kanoniskt:40} @ ({payload['x']:.2f}, {payload['y']:.2f})")
        sparade[prod_id] = payload

    # ── Spara till server ────────────────────────────────
    print(f"\n💾 Sparar {len(sparade)} unika produkter...\n")
    for payload in sparade.values():
        skicka_till_server(payload, dry_run=dry_run)

    print(f"\n✅ Klar! {len(sparade)} produkter:")
    for namn in sparade:
        print(f"   • {sparade[namn]['visningsnamn']}")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Puls-AR Scanner v8")
    parser.add_argument("bild",      nargs="?", default="IMG_5432.jpeg")
    parser.add_argument("--rader",   type=int,  default=RADER)
    parser.add_argument("--kolumner",type=int,  default=KOLUMNER)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ingen-förbehandling", action="store_true")
    args = parser.parse_args()

    skanna_bild(
        args.bild,
        rader                  = args.rader,
        kolumner               = args.kolumner,
        dry_run                = args.dry_run,
        hoppa_över_förbehandling = args.ingen_förbehandling,
    )
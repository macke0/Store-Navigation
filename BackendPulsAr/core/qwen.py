"""
qwen.py  –  Qwen/vLLM-anrop v2
─────────────────────────────────────────────────────────────────
Förbättringar:
  - Dual-mode: butik vs test/debug
  - Bättre prompt för svenska produkter
  - Fallback för generell objektigenkänning
  - Retry-logik vid timeout
qwen.py  –  Qwen/vLLM-anrop
"""
import base64
import requests
import cv2
import numpy as np
import os

VLLM_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY", "")
MODELL = "qwen/qwen2.5-vl-72b-instruct"

# ─────────────────────────────────────────────
# BILDKONVERTERING
# ─────────────────────────────────────────────

def img_till_base64(img: np.ndarray, max_dim: int = 1024) -> str:
    """Konverterar bild till base64, skalar ned om nödvändigt.

    Ökad från 512 till 1024 för bättre läsbarhet av hylletiketter
    vid skanning av butikshyllor.
    """
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        skala = max_dim / max(h, w)
        img = cv2.resize(img, (int(w * skala), int(h * skala)),
                         interpolation=cv2.INTER_LANCZOS4)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return base64.b64encode(buf).decode("utf-8")


# ─────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────

BUTIK_PROMPT = """You are scanning a Swedish grocery store shelf (ICA Maxi).
Your task is to identify the product name from what you see.

PRIORITY ORDER:
1. Read the shelf price tag (white label at bottom of shelf)
2. If no price tag, read the product packaging directly
3. Look for the brand name + product name

RESPOND WITH ONLY: "Brand Productname" in Swedish.

RULES:
- Always include brand name (ICA, Felix, Barilla, Arla, etc.)
- No markdown, asterisks, or numbering
- No explanations or descriptions
- If unclear or no product visible: OKÄND

EXAMPLES:
- ICA Kikärtor
- Felix Ketchup
- Barilla Pasta Penne
- Arla Mjölk 3%
- Oatly Havremjölk"""

DEBUG_PROMPT = """Describe what you see in this image in 2-3 words.
Focus on the main object or scene.
Reply in Swedish if possible, otherwise English.
Examples: "Soffa grå", "Bokhylla", "Skrivbord med dator", "Växt i kruka"
If nothing clear is visible: OKÄND"""

OCR_PROMPT = """Read ALL visible text in this image.
Return each piece of text on a new line.
Include: labels, signs, packaging text, price tags.
If no text visible: INGEN TEXT"""

HYLLA_PROMPT = """You are scanning a section of a Swedish grocery store shelf (ICA Maxi).
Your task is to identify ALL products visible in this image section.

PRIORITY ORDER for each product:
1. Read the shelf price tag (white label at bottom of shelf)
2. If no price tag, read the product packaging directly
3. Look for the brand name + product name

RESPOND WITH one product per line, format: "Brand Productname"
If multiple products are visible, list each on its own line.

RULES:
- Always include brand name (ICA, Felix, Barilla, Arla, Oatly, etc.)
- One product per line, no numbering or bullets
- No markdown, asterisks, or explanations
- If a product is partially visible or unclear, skip it
- If no products visible: OKÄND

EXAMPLES:
ICA Kikärtor
Felix Ketchup
Barilla Pasta Penne"""


# ─────────────────────────────────────────────
# HUVUDFUNKTIONER
# ─────────────────────────────────────────────

def fråga_qwen_vllm(img: np.ndarray, ruta_index: int = 0, 
                    mode: str = "butik", timeout: int = 30) -> str | None:
    """
    Skickar bild till Qwen för analys.
    
    Modes:
      - "butik": Letar efter produktnamn (standard)
      - "debug": Generell beskrivning av bilden
      - "ocr":   Läser all text i bilden
    """
    b64 = img_till_base64(img)
    
    # Välj prompt baserat på mode
    if mode == "debug":
        prompt = DEBUG_PROMPT
    elif mode == "ocr":
        prompt = OCR_PROMPT
    elif mode == "hylla":
        prompt = HYLLA_PROMPT
    else:
        prompt = BUTIK_PROMPT
    
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
                    "text": prompt
                }
            ]
        }],
        "max_tokens": 100,
        "temperature": 0.0,
    }
    
    # Försök upp till 2 gånger vid timeout
    for försök in range(2):
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json"
            }
            resp = requests.post(VLLM_URL, json=payload, timeout=timeout, headers=headers)
            resp.raise_for_status()
            svar = resp.json()["choices"][0]["message"]["content"].strip()
            
            # Rensa svaret
            svar = svar.replace("*", "").replace("#", "").strip()
            
            if svar and "OKÄND" not in svar.upper():
                return svar
            return None
            
        except requests.exceptions.Timeout:
            if försök == 0:
                print(f"   ⏱️  Timeout (ruta {ruta_index}), försöker igen...")
                continue
            print(f"   ⚠️  Timeout (ruta {ruta_index}): gav upp efter 2 försök")
            return None
            
        except requests.exceptions.ConnectionError:
            print(f"   ⚠️  vLLM ej tillgänglig — kör start_vllm.py först!")
            return None
            
        except Exception as e:
            print(f"   ⚠️  vLLM-fel (ruta {ruta_index}): {e}")
            return None
    
    return None


def fråga_qwen_hylla(img: np.ndarray, ruta_index: int = 0,
                     timeout: int = 45) -> list[str]:
    """
    Skickar en hyllsektion till Qwen och returnerar ALLA produktnamn
    som en lista av strängar. Returnerar tom lista om inget hittas.
    """
    b64 = img_till_base64(img)

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
                    "text": HYLLA_PROMPT
                }
            ]
        }],
        "max_tokens": 300,
        "temperature": 0.0,
    }

    for försök in range(2):
        try:
            headers = {
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json"
            }
            resp = requests.post(VLLM_URL, json=payload, timeout=timeout, headers=headers)
            resp.raise_for_status()
            svar = resp.json()["choices"][0]["message"]["content"].strip()
            svar = svar.replace("*", "").replace("#", "").strip()

            if not svar or "OKÄND" in svar.upper():
                return []

            # Parsa rader — en produkt per rad
            produkter = []
            for rad in svar.split("\n"):
                rad = rad.strip().lstrip("0123456789.-) ")
                if rad and len(rad) > 2 and "OKÄND" not in rad.upper():
                    produkter.append(rad)
            return produkter

        except requests.exceptions.Timeout:
            if försök == 0:
                print(f"   ⏱️  Timeout hylla (ruta {ruta_index}), försöker igen...")
                continue
            return []
        except requests.exceptions.ConnectionError:
            print(f"   ⚠️  vLLM ej tillgänglig — kör start_vllm.py först!")
            return []
        except Exception as e:
            print(f"   ⚠️  vLLM-fel hylla (ruta {ruta_index}): {e}")
            return []

    return []


def analysera_bild_debug(img: np.ndarray) -> dict:
    """
    Debug-funktion som kör alla modes och returnerar resultaten.
    Användbar för att testa vad Qwen ser i en bild.
    """
    return {
        "butik": fråga_qwen_vllm(img, mode="butik"),
        "debug": fråga_qwen_vllm(img, mode="debug"),
        "ocr":   fråga_qwen_vllm(img, mode="ocr"),
    }


def är_vllm_igång() -> bool:
    """Kollar om vLLM-servern är tillgänglig."""
    try:
        resp = requests.get("http://127.0.0.1:8001/health", timeout=2)
        return resp.status_code == 200
    except:
        return False


# ─────────────────────────────────────────────
# TEST
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    
    if not är_vllm_igång():
        print("❌ vLLM är inte igång! Kör: python start_vllm.py")
        sys.exit(1)
    
    if len(sys.argv) < 2:
        print("Användning: python qwen.py <bild.jpg> [mode]")
        print("Modes: butik (default), debug, ocr, alla")
        sys.exit(1)
    
    bild_path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "butik"
    
    img = cv2.imread(bild_path)
    if img is None:
        print(f"❌ Kunde inte läsa: {bild_path}")
        sys.exit(1)
    
    print(f"🔍 Analyserar: {bild_path}")
    print(f"   Mode: {mode}\n")
    
    if mode == "alla":
        resultat = analysera_bild_debug(img)
        for m, svar in resultat.items():
            print(f"   [{m:6}] {svar or 'OKÄND'}")
    else:
        svar = fråga_qwen_vllm(img, mode=mode)
        print(f"   Resultat: {svar or 'OKÄND'}")

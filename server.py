"""
server.py  –  Puls-AR Backend v3.2
─────────────────────────────────────────────────────────────────────────────
Nytt mot v3.1:
  - Smart sökning via sok.py
  - GET /sok?q=... hanterar fuzzy + Claude-sökning
  - Gammal GET /sok/{query} finns kvar för bakåtkompatibilitet
─────────────────────────────────────────────────────────────────────────────
"""


import json
from scanner import fråga_qwen_vllm, slug

import socket
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from rapidfuzz import fuzz

from sok import sök_router, sätt_databas, smart_sök

import os
import shutil
from fastapi import UploadFile, File, Form
import time
from typing import List

# ─────────────────────────────────────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Puls-AR API", version="3.2")
app.include_router(sök_router)

databas: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────────────────────
# DATAMODELL
# ─────────────────────────────────────────────────────────────────────────────

class Produkt(BaseModel):
    id:             str
    visningsnamn:   str
    varumarke:      str       = ""
    kategori:       str       = ""
    taggar:         list[str] = []
    ocr_alias:      list[str] = []
    x:              float
    y:              float
    z:              float     = 2.5
    status:         str       = "I lager"
    off_verifierad: bool      = False


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/produkt/")
def spara_produkt(produkt: Produkt):
    """Spara eller uppdatera en produkt (anropas av scanner.py)."""
    databas[produkt.id] = produkt.dict()
    sätt_databas(databas)
    return {"message": f"Sparad: {produkt.visningsnamn}", "id": produkt.id}



@app.post("/skanna-video/")
async def skanna_video(
    frames:     List[UploadFile] = File(...),
    positioner: str              = Form(...)
):
    skanning_id  = f"skanning_{int(time.time())}"
    skanning_dir = f"/tmp/{skanning_id}"
    os.makedirs(skanning_dir, exist_ok=True)

    # Spara alla frames
    for frame in frames:
        frame_path = f"{skanning_dir}/{frame.filename}"
        with open(frame_path, "wb") as f:
            shutil.copyfileobj(frame.file, f)

    # Spara positioner
    pos_data = json.loads(positioner)
    with open(f"{skanning_dir}/positioner.json", "w") as f:
        json.dump(pos_data, f)

    print(f"📥 Skanning mottagen: {skanning_id}")
    print(f"   {len(frames)} frames, {len(pos_data)} positioner")

    import asyncio
    asyncio.create_task(analysera_skanning(skanning_dir, pos_data))

    return {"message": "Mottagen", "id": skanning_id}

async def analysera_skanning(skanning_dir: str, positioner: list):
    """Körs i bakgrunden — analyserar varje frame med Qwen."""
    print(f"🔍 Startar analys av {skanning_dir}")
    
    import cv2
    
    frames = sorted([
        f for f in os.listdir(skanning_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    ])

    print(f"   {len(frames)} frames att analysera")

    for frame_fil in frames:
        frame_nr   = int(frame_fil.replace("frame_", "").replace(".jpg", ""))
        frame_path = f"{skanning_dir}/{frame_fil}"

        position = närmaste_position(frame_nr, positioner)

        # Läs bild
        img = cv2.imread(frame_path)
        if img is None:
            continue

        # Rotera om liggande
        h, w = img.shape[:2]
        if w > h:
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

        # CLAHE — förbättrar lokal kontrast
        lab     = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe   = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l       = clahe.apply(l)
        img     = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)

        # Unsharp mask — skärper text
        gaussian = cv2.GaussianBlur(img, (0, 0), sigmaX=2.0)
        img      = cv2.addWeighted(img, 1.6, gaussian, -0.6, 0)

        # Bilateral filter — tar bort brus, bevarar kanter
        img = cv2.bilateralFilter(img, d=5, sigmaColor=55, sigmaSpace=55)

        # Skicka till Qwen
        svar = fråga_qwen_vllm(img, frame_nr)
        if not svar or "OKÄND" in svar.upper():
            continue

        # Matcha mot produkter.csv
        from produktdb import slå_upp_produkt
        produkt_info = slå_upp_produkt(svar)

        if produkt_info and produkt_info.get("score", 0) >= 75:
            kanoniskt = produkt_info["visningsnamn"]
            varumarke = produkt_info.get("varumarke", "")
            taggar    = produkt_info.get("taggar", [])
        else:
            kanoniskt = svar.strip().split("\n")[0]
            varumarke = ""
            taggar    = []
            print(f"   🆕 Ny produkt (ej i CSV): {kanoniskt}")

        prod_id = slug(kanoniskt)

        if prod_id in databas:
            if svar not in databas[prod_id].get("ocr_alias", []):
                databas[prod_id]["ocr_alias"].append(svar)
            print(f"   ⏭️  Redan känd: {kanoniskt}")
        else:
            payload = {
                "id":           prod_id,
                "visningsnamn": kanoniskt,
                "varumarke":    varumarke,
                "taggar":       taggar,
                "ocr_alias":    [svar],
                "x":            position["x"],
                "y":            position["y"],
                "z":            position["z"],
                "status":       "I lager"
            }
            databas[prod_id] = payload
            sätt_databas(databas)
            print(f"   ✅ {kanoniskt} → ({position['x']:.2f}, {position['y']:.2f})")

    print(f"✅ Analys klar — {len(databas)} produkter i databasen")
    

def närmaste_position(frame_nr: int, positioner: list) -> dict:
    """Hittar den position som tidsmässigt är närmast frame_nummret."""
    if not positioner:
        return {"x": 0.0, "y": 0.0, "z": 0.0}

    bästa = min(positioner,
                key=lambda p: abs(p.get("frame", 0) - frame_nr))
    return {
        "x": bästa.get("x", 0.0),
        "y": bästa.get("y", 0.0),
        "z": bästa.get("z", 0.0)
    }

@app.get("/produkt/{prod_id}")
def hämta_produkt(prod_id: str):
    """Hämta en specifik produkt på ID."""
    if prod_id not in databas:
        return {"fel": f"'{prod_id}' hittades inte"}
    return databas[prod_id]


@app.get("/produkter/")
def lista_produkter():
    """Lista alla produkter i databasen."""
    return {"antal": len(databas), "produkter": list(databas.values())}


@app.delete("/produkt/{prod_id}")
def ta_bort_produkt(prod_id: str):
    """Ta bort en produkt."""
    if prod_id not in databas:
        return {"fel": f"'{prod_id}' hittades inte"}
    namn = databas[prod_id].get("visningsnamn", prod_id)
    del databas[prod_id]
    sätt_databas(databas)
    return {"message": f"Borttagen: {namn}"}


@app.get("/ocr-match/")
def ocr_match(text: str):
    """
    Matchar OCR-text mot ocr_alias.
    Används när kund riktar kameran mot hyllan.
    """
    text_lower  = text.lower().strip()
    bästa_poäng = 0
    bästa_prod  = None

    for prod in databas.values():
        for alias in prod.get("ocr_alias", []):
            poäng = fuzz.token_set_ratio(text_lower, alias.lower())
            if poäng > bästa_poäng:
                bästa_poäng = poäng
                bästa_prod  = prod

    if bästa_prod and bästa_poäng >= 65:
        return {"träff": True, "produkt": bästa_prod, "poäng": bästa_poäng}
    return {"träff": False, "poäng": bästa_poäng}


@app.get("/status/")
def status():
    """Hälsokontroll."""
    return {
        "status":   "online",
        "version":  "3.2",
        "produkter": len(databas)
    }


# Bakåtkompatibilitet
@app.get("/sok/{query}")
def sök_gammal(query: str):
    """Gammal endpoint — använd hellre /sok?q=..."""
    return smart_sök(query)



# ─────────────────────────────────────────────────────────────────────────────
# START
# ─────────────────────────────────────────────────────────────────────────────

def hitta_ledig_port(startport: int = 8000) -> int:
    for port in range(startport, startport + 10):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return port
    return startport


if __name__ == "__main__":
    port = hitta_ledig_port(8000)
    print(f"🚀 Puls-AR Server v3.2 startar på port {port}")
    print(f"   Dokumentation: http://localhost:{port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=port)
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
import os
import shutil
import socket
import time
from typing import List
from fastapi import FastAPI, UploadFile, File, Form, Request
import re

import uvicorn
from pydantic import BaseModel
from rapidfuzz import fuzz

from core.loop_closure import korrigera_loop_closure
from core.positionering import korrigera_position, beräkna_hyllposition
from core.läs_usdz import extrahera_koordinater
from core.scanner import slug
from core.qwen import fråga_qwen_vllm
from core.sok     import sök_router, sätt_databas, smart_sök
from core.clip_sok import clip_matcha
from core.databas  import (spara_produkt as db_spara, hämta_produkt,
                            hämta_alla_produkter, ta_bort_produkt as db_ta_bort,
                            flagga_saknas, hämta_flaggor)

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
    gång:           str       = "okänd"
    status:         str       = "I lager"
    off_verifierad: bool      = False


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/produkt/")
def spara_produkt_endpoint(produkt: Produkt):
    db_spara(produkt.dict(), källa="personal")
    sätt_databas({p["id"]: p for p in hämta_alla_produkter()})
    return {"message": f"Sparad: {produkt.visningsnamn}"}

@app.post("/skanna-struktur/")
async def skanna_struktur(
    karta: UploadFile = File(...),
    objekt_data: str  = Form(None)
):
    innehåll = await karta.read()
    sökväg   = f"/tmp/butik_{int(time.time())}.usdz"
    with open(sökväg, "wb") as f:
        f.write(innehåll)

    # Spara JSON-data om den finns
    parsed_data = None
    if objekt_data:
        parsed_data = json.loads(objekt_data)
        json_sökväg = sökväg.replace(".usdz", ".json")
        with open(json_sökväg, "w") as f:
            json.dump(parsed_data, f, ensure_ascii=False, indent=2)
        print(f"✅ Objektdata sparad: {json_sökväg}")

    koordinater = extrahera_koordinater(sökväg)
    print(f"✅ Karta sparad: {sökväg} ({len(innehåll)/1024:.0f}KB)")
    print(f"   {len(koordinater['väggar'])} väggar")
    print(f"   {len(koordinater['objekt'])} objekt")

    return {
        "message":     "Karta sparad",
        "fil":         sökväg,
        "koordinater": koordinater,
        "objekt_data": parsed_data
    }

@app.delete("/gång/{gång_namn}/reset")
async def reset_gång(gång_namn: str):
    """Tar bort alla produkter för en gång och rensar gång-indexet."""
    # Ta bort produkter för denna gång
    alla = hämta_alla_produkter()
    borttagna = 0
    for prod in alla:
        if prod.get("gång") == gång_namn:
            db_ta_bort(prod["id"])
            borttagna += 1

    # Rensa gång-index
    gång_index_fil = "/tmp/gång_index.json"
    if os.path.exists(gång_index_fil):
        with open(gång_index_fil) as f:
            gång_index = json.load(f)
        if gång_namn in gång_index:
            del gång_index[gång_namn]
        with open(gång_index_fil, "w") as f:
            json.dump(gång_index, f)

    print(f"🗑️ Reset {gång_namn}: {borttagna} produkter borttagna")
    return {"message": f"Reset klar — {borttagna} produkter borttagna"}
    
@app.post("/ankarpunkter/")
async def spara_ankarpunkter(request: Request):
    """Tar emot ankarpunkter från iOS-kartläggning."""
    data     = await request.json()
    fil_path = "/tmp/ankarpunkter.json"

    with open(fil_path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(data)} ankarpunkter sparade")
    for punkt in data:
        print(f"   📍 {punkt['namn']}: ({punkt['x']:.2f}, {punkt['z']:.2f})")

    return {"message": f"{len(data)} ankarpunkter sparade"}


@app.get("/gång/positioner")
async def hämta_gång_positioner(namn: str):
    print(f"🔍 Söker positioner för: '{namn}'")
    gång_index_fil = "/tmp/gång_index.json"
    if not os.path.exists(gång_index_fil):
        print("❌ gång_index.json finns inte")
        return {"positioner": []}
    
    with open(gång_index_fil) as f:
        gång_index = json.load(f)
    
    print(f"📋 Index innehåller: {list(gång_index.keys())}")
    
    skanning_dir = gång_index.get(namn)
    if not skanning_dir:
        print(f"❌ '{namn}' hittades inte i index")
        return {"positioner": []}
    
    pos_fil = f"{skanning_dir}/positioner.json"
    if not os.path.exists(pos_fil):
        return {"positioner": []}
    
    with open(pos_fil) as f:
        return {"positioner": json.load(f)}

@app.get("/ankarpunkter/")
async def hämta_ankarpunkter():
    """Returnerar sparade ankarpunkter."""
    fil_path = "/tmp/ankarpunkter.json"
    if not os.path.exists(fil_path):
        return {"ankarpunkter": []}
    with open(fil_path) as f:
        return {"ankarpunkter": json.load(f)}

@app.post("/skanna-video/")
async def skanna_video(
    frames:     List[UploadFile] = File(...),
    positioner: str              = Form(...)
):
    skanning_id  = f"skanning_{int(time.time())}"
    skanning_dir = f"/tmp/{skanning_id}"
    os.makedirs(skanning_dir, exist_ok=True)

    for frame in frames:
        frame_path = f"{skanning_dir}/{frame.filename}"
        with open(frame_path, "wb") as f:
            shutil.copyfileobj(frame.file, f)

    pos_data = json.loads(positioner)
    korrigerade_pos, closure_info = korrigera_loop_closure(pos_data)
    if not closure_info["korrigerad"]:
        korrigerade_pos = pos_data

    with open(f"{skanning_dir}/positioner.json", "w") as f:
        json.dump(korrigerade_pos, f)

    # Spara mappning gångnamn → skanningmapp
    # Varför: Så att vi kan hitta positionerna för en specifik gång senare
    gång_namn = pos_data[0].get("gång", "okänd") if pos_data else "okänd"
    gång_index_fil = "/tmp/gång_index.json"
    if os.path.exists(gång_index_fil):
        with open(gång_index_fil) as f:
            gång_index = json.load(f)
    else:
        gång_index = {}
    gång_index[gång_namn] = skanning_dir
    with open(gång_index_fil, "w") as f:
        json.dump(gång_index, f)

    print(f"📥 Skanning mottagen: {skanning_id} ({gång_namn})")
    print(f"   {len(frames)} frames, {len(pos_data)} positioner")

    import asyncio
    asyncio.create_task(analysera_skanning(skanning_dir, korrigerade_pos))

    return {"message": "Mottagen", "id": skanning_id}



def rensa_qwen_svar(text: str) -> str:
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'^\d+\.\s*', '', text.strip())
    text = re.sub(r'\(.*?\)', '', text)
    # Konvertera till title case om allt är versaler
    if text.isupper():
        text = text.title()
    text = ' '.join(text.split())
    return text.strip()


async def analysera_skanning(skanning_dir: str, positioner: list):
    """Körs i bakgrunden — analyserar varje frame med Qwen + CLIP."""
    print(f"🔍 Startar analys av {skanning_dir}")

    import cv2
    from core.produktdb import slå_upp_produkt

    frames = sorted([
        f for f in os.listdir(skanning_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    ])

    print(f"   {len(frames)} frames att analysera")

    for frame_fil in frames:
        frame_nr   = int(frame_fil.replace("frame_", "").replace(".jpg", ""))
        frame_path = f"{skanning_dir}/{frame_fil}"

        # Korrigera position med LiDAR
        position = korrigera_position(positioner, frame_nr)
        position = beräkna_hyllposition(position)

        if position.get("korrigerad"):
            print(f"   🎯 Frame {frame_nr}: LiDAR-korrigerad [{position.get('precision')}]")

        img = cv2.imread(frame_path)
        if img is None:
            continue

        h, w = img.shape[:2]
        if w > h:
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)

        lab     = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe   = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l       = clahe.apply(l)
        img     = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
        gaussian = cv2.GaussianBlur(img, (0, 0), sigmaX=2.0)
        img      = cv2.addWeighted(img, 1.6, gaussian, -0.6, 0)
        img      = cv2.bilateralFilter(img, d=5, sigmaColor=55, sigmaSpace=55)

        # ── QWEN ──────────────────────────────────────────
        qwen_svar = fråga_qwen_vllm(img, frame_nr)
        qwen_namn = None
        if qwen_svar and "OKÄND" not in qwen_svar.upper():
            qwen_namn = rensa_qwen_svar(qwen_svar.strip().split("\n")[0])

        if qwen_namn:
            kanoniskt = qwen_namn
            säkerhet  = position.get("precision", "låg")
        else:
            print(f"   ⚪ Frame {frame_nr}: ingen produkt")
            continue

        # ── VERIFIERA MOT ICA-DATABASEN ──────────────────
        match = slå_upp_produkt(kanoniskt)
        if not match or match.get("score", 0) < 65:
            print(f"   ⚪ Frame {frame_nr}: '{kanoniskt}' ej i ICA-sortiment")
            continue

        kanoniskt = match["kanoniskt_namn"]
        varumarke = match.get("varumarke", "")
        kategori  = match.get("kategori", "")

        print(f"   ✅ {kanoniskt} [{säkerhet}] Qwen:{qwen_namn} "
              f"{'🎯' if position.get('korrigerad') else ''}")

        prod_id = slug(kanoniskt)

        if prod_id in databas:
            if qwen_namn and qwen_namn not in databas[prod_id].get("ocr_alias", []):
                databas[prod_id]["ocr_alias"].append(qwen_namn)
            print(f"   ⏭️  Redan känd: {kanoniskt}")
        else:
            payload = {
                "id":           prod_id,
                "visningsnamn": kanoniskt,
                "varumarke":    varumarke,
                "kategori":     kategori,
                "taggar":       [],
                "ocr_alias":    [qwen_namn] if qwen_namn else [],
                "x":            position["x"],
                "y":            position.get("y", 0),
                "z":            position.get("z", 0),
                "djup":         position.get("djup_fram", 0),
                "gång":         position.get("gång", "okänd"),
                "status":       "I lager",
                "säkerhet":     säkerhet,
                "precision":    position.get("precision", "låg"),
            }
            databas[prod_id] = payload
            sätt_databas(databas)
            print(f"   💾 Sparad: {kanoniskt} → "
                  f"({position['x']:.2f}, {position.get('z', 0):.2f}) "
                  f"[{position.get('precision', 'låg')}]")

    print(f"✅ Analys klar — {len(databas)} produkter i databasen")

@app.post("/flagga/{prod_id}")
def flagga_produkt(prod_id: str):
    """Kund rapporterar att produkt saknas på angiven position."""
    flagga_saknas(prod_id)
    return {"message": "Tack för rapporten"}

@app.get("/flaggor/")
def lista_flaggor():
    """Personal ser alla flaggor."""
    return hämta_flaggor()

@app.get("/gångar/")
async def lista_gångar():
    produkter = hämta_alla_produkter()
    gångar = {}
    
    # Lägg till gångar från produktdatabasen
    for prod in produkter:
        gång = prod.get("gång", "okänd")
        if gång not in gångar:
            gångar[gång] = {
                "namn":      gång,
                "produkter": [],
                "offset_x":  0,
                "offset_z":  0,
            }
        gångar[gång]["produkter"].append(prod)

    # Lägg också till gångar från gång_index som inte har produkter än
    # Varför: En gång kan vara skannad men utan produkter (t.ex. hemma)
    gång_index_fil = "/tmp/gång_index.json"
    if os.path.exists(gång_index_fil):
        with open(gång_index_fil) as f:
            gång_index = json.load(f)
        for gång_namn in gång_index:
            if gång_namn not in gångar:
                gångar[gång_namn] = {
                    "namn":      gång_namn,
                    "produkter": [],
                    "offset_x":  0,
                    "offset_z":  0,
                }

    # Ladda sparade offsets
    offset_fil = "/tmp/gång_positioner.json"
    if os.path.exists(offset_fil):
        with open(offset_fil) as f:
            offsets = json.load(f)
        for gång_namn, offset in offsets.items():
            if gång_namn in gångar:
                gångar[gång_namn]["offset_x"] = offset.get("offset_x", 0)
                gångar[gång_namn]["offset_z"] = offset.get("offset_z", 0)

    return {"gångar": list(gångar.values())}

@app.put("/gång/{gång_namn}/position")
async def uppdatera_gång_position(gång_namn: str, data: dict):
    """Personal justerar gångens position i butikkartan."""
    # Spara gångoffset i en JSON-fil
    offset_fil = "/tmp/gång_positioner.json"
    if os.path.exists(offset_fil):
        with open(offset_fil) as f:
            offsets = json.load(f)
    else:
        offsets = {}
    
    offsets[gång_namn] = {
        "offset_x": data.get("offset_x", 0),
        "offset_z": data.get("offset_z", 0),
    }
    with open(offset_fil, "w") as f:
        json.dump(offsets, f)
    
    return {"message": f"Position sparad för {gång_namn}"}

@app.get("/gång/{gång_namn}/positioner")
async def hämta_gång_positioner(gång_namn: str):
    print(f"🔍 Söker positioner för: '{gång_namn}'")
    gång_index_fil = "/tmp/gång_index.json"
    if not os.path.exists(gång_index_fil):
        print("❌ gång_index.json finns inte")
        return {"positioner": []}
    
    with open(gång_index_fil) as f:
        gång_index = json.load(f)
    
    print(f"📋 Index innehåller: {list(gång_index.keys())}")
    
    skanning_dir = gång_index.get(gång_namn)
    if not skanning_dir:
        print(f"❌ '{gång_namn}' hittades inte i index")
        return {"positioner": []}
    
    pos_fil = f"{skanning_dir}/positioner.json"
    if not os.path.exists(pos_fil):
        print(f"❌ Positionsfil finns inte: {pos_fil}")
        return {"positioner": []}
    
    with open(pos_fil) as f:
        return {"positioner": json.load(f)}

@app.get("/produkt/{prod_id}")
def hämta_produkt_endpoint(prod_id: str):
    prod = hämta_produkt(prod_id)
    if not prod:
        return {"fel": f"'{prod_id}' hittades inte"}
    return prod

@app.get("/produkter/")
def lista_produkter():
    alla = hämta_alla_produkter()
    return {"antal": len(alla), "produkter": alla}

@app.delete("/produkt/{prod_id}")
def ta_bort_produkt_endpoint(prod_id: str):
    prod = hämta_produkt(prod_id)
    if not prod:
        return {"fel": f"'{prod_id}' hittades inte"}
    db_ta_bort(prod_id)
    return {"message": f"Borttagen: {prod['visningsnamn']}"}


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


from fastapi.responses import HTMLResponse

@app.get("/admin", response_class=HTMLResponse)
async def admin():
    with open("admin.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get("/admin/data")
async def admin_data():
    usdz_filer = sorted(
        [f for f in os.listdir("/tmp") if f.endswith(".usdz")],
        key=lambda f: os.path.getmtime(f"/tmp/{f}"),
        reverse=True
    )
    karta       = None
    objekt_data = None

    if usdz_filer:
        usdz_path  = f"/tmp/{usdz_filer[0]}"
        karta      = extrahera_koordinater(usdz_path)
        json_path  = usdz_path.replace(".usdz", ".json")
        if os.path.exists(json_path):
            with open(json_path) as f:
                objekt_data = json.load(f)

    produkter = hämta_alla_produkter()
    return {
        "karta":       karta,
        "objekt_data": objekt_data,
        "produkter":   produkter
    }

@app.put("/admin/produkt/{prod_id}")
async def uppdatera_produkt(prod_id: str, data: dict):
    """Personal uppdaterar position eller status manuellt."""
    prod = hämta_produkt(prod_id)
    if not prod:
        return {"fel": "Produkt hittades inte"}
    prod.update(data)
    db_spara(prod, källa="personal")
    return {"message": "Uppdaterad"}

@app.delete("/admin/produkt/{prod_id}")
async def radera_produkt(prod_id: str):
    """Personal tar bort en produkt."""
    db_ta_bort(prod_id)
    return {"message": "Borttagen"}



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
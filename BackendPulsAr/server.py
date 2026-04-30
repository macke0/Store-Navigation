"""
server.py  –  Puls-AR Backend v3.2
─────────────────────────────────────────────────────────────────────────────
Nytt mot v3.1:
  - Smart sökning via sok.py
  - GET /sok?q=... hanterar fuzzy + Claude-sökning
  - Gammal GET /sok/{query} finns kvar för bakåtkompatibilitet
─────────────────────────────────────────────────────────────────────────────
"""

# VIKTIGT: Sätt max storlek FÖRE allt annat
from starlette.formparsers import MultiPartParser
MultiPartParser.max_part_size = 1024 * 1024 * 500  # 500MB per form field


import asyncio
from vps_endpoints import setup_vps_routes
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

from core.feature_karta import bygg_karta
from core.lokalisering  import lokalisera_kund
from core.loop_closure import korrigera_loop_closure
from core.positionering import korrigera_position, beräkna_hyllposition
#from core.läs_usdz import extrahera_koordinater
from core.scanner import slug
from core.qwen import fråga_qwen_vllm
from core.sok     import sök_router, sätt_databas, smart_sök
# from core.clip_sok import clip_matcha
from core.databas  import (spara_produkt as db_spara, hämta_produkt,
                            hämta_alla_produkter, ta_bort_produkt as db_ta_bort,
                            flagga_saknas, hämta_flaggor)
from vps_3d_endpoints import router as vps_3d_router
from sok_endpoint import setup_sok_routes
from core.produkt_lista import router as produkt_lista_router
from core.scan_viewer import router as viewer_router
from core.viewer_3d import router as viewer_3d_router
from core.butik_endpoints import router as butik_router
from core.produkt_edit_endpoints import router as edit_router

from core.butik_kalibrering import (
    spara_kalibrering,
    ladda_kalibrering,
    vps_till_pixel,
    pixel_till_vps,
    spara_kartbild,
    hämta_kartbild_path,
    butik_status,
    lista_butiker,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional

from core.multi_session import (
    preflight,
    lägg_till_session,
    lista_kartor as lista_alla_kartor,
)


class Referenspunkt(BaseModel):
    vps: List[float]
    pixel: List[float]
    beskrivning: Optional[str] = None


class KalibreraRequest(BaseModel):
    referenspunkter: List[Referenspunkt]


class VpsKoordinat(BaseModel):
    x: float
    z: float


class PixelKoordinat(BaseModel):
    pixel_x: float
    pixel_y: float

# ─────────────────────────────────────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="Puls-AR API", version="3.2")

setup_sok_routes(app)
app.include_router(vps_3d_router)
setup_vps_routes(app)
app.include_router(sök_router)
app.include_router(produkt_lista_router)
app.include_router(viewer_router)
app.include_router(viewer_3d_router)
app.include_router(butik_router)
app.include_router(edit_router)



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

@app.delete("/gång/reset")
async def reset_gång(namn: str):
    alla = hämta_alla_produkter()
    borttagna = 0
    for prod in alla:
        if prod.get("gång") == namn:
            db_ta_bort(prod["id"])
            borttagna += 1

    gång_index_fil = "/tmp/gång_index.json"
    if os.path.exists(gång_index_fil):
        with open(gång_index_fil) as f:
            gång_index = json.load(f)
        if namn in gång_index:
            del gång_index[namn]
        with open(gång_index_fil, "w") as f:
            json.dump(gång_index, f)

    print(f"🗑️ Reset {namn}: {borttagna} produkter borttagna")
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

@app.get("/gang/{gang_namn}/positioner")
async def hämta_gang_positioner_ascii(gang_namn: str):
    """ASCII-version av gång-endpoint för webbläsarkompatibilitet."""
    gang_namn = gang_namn.replace("_", " ").replace("Gang", "Gång")
    
    print(f"🔍 Söker positioner för: '{gang_namn}'")
    gång_index_fil = "/tmp/gång_index.json"
    
    if not os.path.exists(gång_index_fil):
        return {"positioner": []}
    
    with open(gång_index_fil) as f:
        gång_index = json.load(f)
    
    skanning_dir = gång_index.get(gang_namn)
    if not skanning_dir:
        return {"positioner": []}
    
    pos_fil = f"{skanning_dir}/positioner.json"
    if not os.path.exists(pos_fil):
        return {"positioner": []}
    
    with open(pos_fil) as f:
        return {"positioner": json.load(f)}

@app.get("/gång/{gång_namn}/positioner")
async def hämta_gång_positioner(gång_namn: str):
    gång_namn = gång_namn.replace("_", " ")  # Hantera både "Gång_4" och "Gång 4"
    
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
        return {"positioner": []}  # ← RETURN SAKNADES!
    
    pos_fil = f"{skanning_dir}/positioner.json"
    if not os.path.exists(pos_fil):
        print(f"❌ Positionsfil finns inte: {pos_fil}")
        return {"positioner": []}
    
    with open(pos_fil) as f:
        return {"positioner": json.load(f)}

@app.post("/lokalisera/")
async def lokalisera(
    bild:      UploadFile = File(...),
    gång_namn: str        = Form(None)
):
    """Lokaliserar kund baserat på kamerabild via VPS."""
    import os
    with open("/tmp/vps_debug_test.txt", "w") as _f:
        _f.write("endpoint nådd")
    print("🔴 LOKALISERA ENDPOINT NÅDD")
    bild_bytes = await bild.read()
    # DEBUG: spara bilden som iOS skickar
    with open("/tmp/debug_vps_image.jpg", "wb") as f:
        f.write(bild_bytes)
    import cv2, numpy as np
    img_debug = cv2.imdecode(np.frombuffer(bild_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img_debug is not None:
        print(f"📷 Mottagen bild: {img_debug.shape[1]}x{img_debug.shape[0]}, {len(bild_bytes)//1024} KB")
    else:
        print(f"📷 Kunde inte läsa bilden! {len(bild_bytes)} bytes")
    resultat   = lokalisera_kund(bild_bytes, gång_namn)
    if resultat.get("success") or resultat.get("x") is not None:
        print(f"   📍 Position: x={resultat.get('x', 0):.2f}, y={resultat.get('y', 0):.2f}, z={resultat.get('z', 0):.2f}")
        print(f"   🧭 Yaw: {resultat.get('yaw', resultat.get('rotation', 0)):.1f}°")
        print(f"   🎯 Inliers: {resultat.get('inliers', '?')}")
    else:
        print(f"   ❌ Lokalisering misslyckades: {resultat}")
    return resultat

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
    request: Request,
    frames: List[UploadFile] = File(default=[]),
    positioner: str = Form(...),
    punkter_3d: str = Form("[]"),
    karta_id: str = Form(None),
):
    """Tar emot skanning och bygger eller mergar kartan."""
    from starlette.formparsers import MultiPartParser
    MultiPartParser.max_part_size = 1024 * 1024 * 500
    
    skanning_id = f"skanning_{int(time.time())}"
    skanning_dir = f"/tmp/{skanning_id}"
    os.makedirs(skanning_dir, exist_ok=True)
    
    for frame in frames:
        frame_path = f"{skanning_dir}/{frame.filename}"
        with open(frame_path, "wb") as f:
            shutil.copyfileobj(frame.file, f)
    
    pos_data = json.loads(positioner)
    punkter_data = json.loads(punkter_3d)
    
    korrigerade_pos, closure_info = korrigera_loop_closure(pos_data)
    if not closure_info["korrigerad"]:
        korrigerade_pos = pos_data
    
    with open(f"{skanning_dir}/positioner.json", "w") as f:
        json.dump(korrigerade_pos, f)
    with open(f"{skanning_dir}/punkter_3d.json", "w") as f:
        json.dump(punkter_data, f)
    
    print(f"📥 Skanning mottagen: {skanning_id}")
    print(f"   {len(frames)} frames, {len(pos_data)} positioner, {len(punkter_data)} 3D-punkter")
    print(f"   karta_id: {karta_id or 'NY KARTA'}")
    
    förväntat_karta = karta_id if karta_id else None
    
    resultat = lägg_till_session(
        session_dir=skanning_dir,
        punkter_3d=punkter_data,
        positioner=korrigerade_pos,
        session_id=skanning_id,
        förväntat_karta_id=förväntat_karta,
        verbose=True,
    )
    
    return resultat

async def bygg_3d_karta_async(skanning_dir, punkter_data, positioner, gång_namn):
    """Wrapper för att köra kartbygge async."""
    try:
        from core.vps_3d import bygg_3d_karta
        print(f"🔧 Bygger 3D-karta för {gång_namn}...")
        bygg_3d_karta(skanning_dir, punkter_data, positioner, gång_namn)
    except Exception as e:
        print(f"❌ Kartbygge misslyckades: {e}")

async def lägg_till_session_async(
    skanning_dir,
    punkter_data,
    positioner,
    session_id,
    karta_id
):
    """Wrapper för att köra multi-session pipeline async."""
    try:
        from core.multi_session import lägg_till_session
        print(f"🔧 Multi-session: bygger karta för {session_id}...")
        resultat = lägg_till_session(
            session_dir=skanning_dir,
            punkter_3d=punkter_data,
            positioner=positioner,
            session_id=session_id,
            förväntat_karta_id=karta_id,
            verbose=True,
        )
        print(f"   Resultat: {resultat}")
    except Exception as e:
        import traceback
        print(f"❌ Multi-session misslyckades: {e}")
        traceback.print_exc()

def rensa_qwen_svar(text: str) -> str:
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'^\d+\.\s*', '', text.strip())
    text = re.sub(r'\(.*?\)', '', text)
    # Konvertera till title case om allt är versaler
    if text.isupper():
        text = text.title()
    text = ' '.join(text.split())
    return text.strip()


def _förbehandla_frame(img):
    """Bildförbättring: CLAHE + skärpning + bilateral filter."""
    import cv2
    lab     = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe   = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l       = clahe.apply(l)
    img     = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)
    gaussian = cv2.GaussianBlur(img, (0, 0), sigmaX=2.0)
    img      = cv2.addWeighted(img, 1.6, gaussian, -0.6, 0)
    img      = cv2.bilateralFilter(img, d=5, sigmaColor=55, sigmaSpace=55)
    return img


def _dela_frame_i_rutor(img, rader: int = 4, kolumner: int = 4):
    """Delar en frame i rader×kolumner rutor med 10% överlapp."""
    h, w      = img.shape[:2]
    överlapp  = 0.10
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


def _analysera_ruta_worker(args):
    """Worker för att analysera en ruta med Qwen + produktdb-match.
    Körs i ThreadPoolExecutor."""
    import cv2
    from core.qwen import fråga_qwen_hylla
    from core.produktdb import slå_upp_produkt

    ruta_img, ruta_nr, position = args

    # Förbehandla rutan
    ruta_img = _förbehandla_frame(ruta_img)

    # Qwen identifierar alla produkter i rutan
    qwen_produkter = fråga_qwen_hylla(ruta_img, ruta_nr)

    resultat = []
    for qwen_namn in qwen_produkter:
        qwen_namn = rensa_qwen_svar(qwen_namn)
        if not qwen_namn:
            continue

        match = slå_upp_produkt(qwen_namn)
        if not match or match.get("score", 0) < 65:
            continue

        resultat.append({
            "qwen_namn":  qwen_namn,
            "kanoniskt":  match["kanoniskt_namn"],
            "varumarke":  match.get("varumarke", ""),
            "kategori":   match.get("kategori", ""),
            "match_score": match.get("score", 0),
            "position":   position,
        })

    return resultat


SKANNING_RUTNÄT_RADER    = 4   # 4×4 = 16 rutor per frame
SKANNING_RUTNÄT_KOLUMNER = 4
SKANNING_MAX_WORKERS     = 8   # parallella Qwen-anrop


async def analysera_skanning(skanning_dir: str, positioner: list):
    """Körs i bakgrunden — analyserar varje frame med grid-split + Qwen + CLIP.

    Förbättringar mot tidigare version:
      1. Delar varje frame i 4×4 rutor — varje ruta analyseras separat
      2. Qwen returnerar ALLA produkter per ruta (multi-product prompt)
      3. Parallell processing med ThreadPoolExecutor
      4. Deduplicering — samma produkt sparas bara en gång,
         men OCR-alias uppdateras
    """
    import cv2
    import concurrent.futures

    print(f"🔍 Startar analys av {skanning_dir}")
    print(f"   Rutnät: {SKANNING_RUTNÄT_RADER}×{SKANNING_RUTNÄT_KOLUMNER} "
          f"= {SKANNING_RUTNÄT_RADER * SKANNING_RUTNÄT_KOLUMNER} rutor/frame")

    frames = sorted([
        f for f in os.listdir(skanning_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    ])

    print(f"   {len(frames)} frames att analysera")

    alla_produkter = {}   # prod_id → payload  (deduplicering)
    totalt_identifierade = 0

    for frame_fil in frames:
        frame_nr   = int(frame_fil.replace("frame_", "").replace(".jpg", ""))
        frame_path = f"{skanning_dir}/{frame_fil}"

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

        # Dela framen i rutor
        boxar = _dela_frame_i_rutor(
            img, SKANNING_RUTNÄT_RADER, SKANNING_RUTNÄT_KOLUMNER
        )

        # Bygg worker-args: varje ruta som separat crop
        worker_args = []
        for i, (x1, y1, x2, y2) in enumerate(boxar):
            crop = img[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            ruta_nr = frame_nr * 100 + i  # unikt nummer per ruta
            worker_args.append((crop, ruta_nr, position))

        # Parallell analys av alla rutor i denna frame
        frame_resultat = []
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=SKANNING_MAX_WORKERS
        ) as executor:
            futures = {
                executor.submit(_analysera_ruta_worker, args): args[1]
                for args in worker_args
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    res_lista = future.result()
                    if res_lista:
                        frame_resultat.extend(res_lista)
                except Exception as e:
                    ruta_id = futures[future]
                    print(f"   ⚠️  Ruta {ruta_id}: {e}")

        # Deduplicera och spara
        for res in frame_resultat:
            kanoniskt = res["kanoniskt"]
            qwen_namn = res["qwen_namn"]
            prod_id   = slug(kanoniskt)
            säkerhet  = res["position"].get("precision", "låg")

            if prod_id in alla_produkter:
                # Uppdatera alias om nytt
                alias = alla_produkter[prod_id].get("ocr_alias", [])
                if qwen_namn and qwen_namn not in alias:
                    alias.append(qwen_namn)
                    alla_produkter[prod_id]["ocr_alias"] = alias
            else:
                alla_produkter[prod_id] = {
                    "id":           prod_id,
                    "visningsnamn": kanoniskt,
                    "varumarke":    res["varumarke"],
                    "kategori":     res["kategori"],
                    "taggar":       [],
                    "ocr_alias":    [qwen_namn] if qwen_namn else [],
                    "x":            res["position"]["x"],
                    "y":            res["position"].get("y", 0),
                    "z":            res["position"].get("z", 0),
                    "djup":         res["position"].get("djup_fram", 0),
                    "gång":         res["position"].get("gång", "okänd"),
                    "status":       "I lager",
                    "säkerhet":     säkerhet,
                    "precision":    res["position"].get("precision", "låg"),
                }
                totalt_identifierade += 1
                print(f"   ✅ {kanoniskt} [{säkerhet}] "
                      f"Qwen:'{qwen_namn}' score:{res['match_score']} "
                      f"{'🎯' if res['position'].get('korrigerad') else ''}")

        print(f"   📦 Frame {frame_nr}: "
              f"{len(frame_resultat)} produktträffar, "
              f"{totalt_identifierade} unika totalt")

    # Spara alla till databas
    for prod_id, payload in alla_produkter.items():
        if prod_id not in databas:
            databas[prod_id] = payload
            sätt_databas(databas)
        else:
            # Uppdatera alias
            existing_alias = databas[prod_id].get("ocr_alias", [])
            for alias in payload.get("ocr_alias", []):
                if alias not in existing_alias:
                    existing_alias.append(alias)
            databas[prod_id]["ocr_alias"] = existing_alias
            sätt_databas(databas)

    print(f"✅ Analys klar — {len(alla_produkter)} nya produkter, "
          f"{len(databas)} totalt i databasen")

    gång_namn = positioner[0].get("gång", "okänd") if positioner else "okänd"
    if gång_namn != "okänd":
        print(f"🗺️  Bygger VPS-karta för {gång_namn}...")
        karta_result = bygg_karta(skanning_dir, positioner, gång_namn)
        if karta_result:
            print(f"✅ VPS-karta klar: {karta_result}")
        else:
            print(f"⚠️  VPS-karta kunde inte byggas")

    print(f"🏁 Skanning {skanning_dir} helt klar!")

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
    from core.produkt_sok import get_produkt_sök
    sök = get_produkt_sök()
    resultat = sök.sök(query, limit=30)
    produkter = []
    for p in resultat:
        produkter.append({
            "id": p.get("id", ""),
            "visningsnamn": p.get("namn", ""),
            "varumarke": p.get("varumarke", ""),
            "kategori": p.get("kategori", ""),
            "bild_url": p.get("bild_url", ""),  
            "gång": p.get("gång"),
            "x": p.get("x"),
            "y": p.get("y"),
            "z": p.get("z"),
            "status": "I lager"
        })
    return {"query": query, "antal": len(produkter), "produkter": produkter}


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

@app.get("/vps/status")
async def vps_status():
    """Visa status för alla VPS-kartor."""
    kartor_dir = "/tmp/kartor"
    if not os.path.exists(kartor_dir):
        return {"kartor": [], "meddelande": "Inga kartor byggda"}
    
    kartor = []
    for gång_dir in os.listdir(kartor_dir):
        meta_fil = f"{kartor_dir}/{gång_dir}/metadata.json"
        if os.path.exists(meta_fil):
            with open(meta_fil) as f:
                meta = json.load(f)
            kartor.append(meta)
    
    return {"kartor": kartor, "antal": len(kartor)}


@app.post("/vps/testa")
async def testa_vps(bild: UploadFile = File(...)):
    """Testa VPS-lokalisering med en bild."""
    bild_bytes = await bild.read()
    resultat = lokalisera_kund(bild_bytes)
    return resultat

@app.get("/debug/skanning/{skanning_id}")
async def debug_skanning(skanning_id: str):
    """Visa alla frames och vad Qwen såg i dem."""
    import cv2
    from core.qwen import fråga_qwen_vllm
    
    skanning_dir = f"/tmp/{skanning_id}"
    if not os.path.exists(skanning_dir):
        return {"fel": f"Skanning {skanning_id} finns inte"}
    
    frames = sorted([
        f for f in os.listdir(skanning_dir)
        if f.startswith("frame_") and f.endswith(".jpg")
    ])[:10]  # Begränsa till 10 första
    
    resultat = []
    for frame_fil in frames:
        frame_path = f"{skanning_dir}/{frame_fil}"
        img = cv2.imread(frame_path)
        if img is None:
            continue
        
        qwen_svar = fråga_qwen_vllm(img, 0)
        resultat.append({
            "frame": frame_fil,
            "qwen_svar": qwen_svar or "OKÄND",
        })
    
    return {"skanning": skanning_id, "frames": resultat}


@app.get("/debug/vps")
async def debug_vps():
    """Visa status för alla VPS-kartor."""
    kartor_dir = "/tmp/kartor"
    if not os.path.exists(kartor_dir):
        return {"kartor": [], "meddelande": "Inga kartor byggda"}
    
    kartor = []
    for gång_dir in os.listdir(kartor_dir):
        meta_fil = f"{kartor_dir}/{gång_dir}/metadata.json"
        if os.path.exists(meta_fil):
            with open(meta_fil) as f:
                kartor.append(json.load(f))
    
    return {"kartor": kartor}


@app.post("/debug/lokalisera")
async def debug_lokalisera(bild: UploadFile = File(...)):
    """Testa VPS-lokalisering med detaljerad output."""
    from core.lokalisering import lokalisera_kund
    
    bild_bytes = await bild.read()
    resultat = lokalisera_kund(bild_bytes)
    return resultat

# ─────────────────────────────────────────────────────────────────────────────
# BATCH UPLOAD ENDPOINT
# ─────────────────────────────────────────────────────────────────────────────

# Temporär lagring för batches
batch_storage = {}

@app.post("/skanna-video-batch/")
async def skanna_video_batch(
    skanning_id:   str              = Form(...),
    batch_index:   int              = Form(...),
    total_batches: int              = Form(...),
    is_last:       str              = Form(...),
    frames:        List[UploadFile] = File(default=[]),
    positioner:    str              = Form("[]"),
    punkter_3d:    str              = Form("[]"),
    karta_id:      str              = Form(None),
    mesh:          List[UploadFile] = File(default=[]),
):
    """Ta emot en batch av frames och 3D-punkter."""
    
    print(f"📦 Batch {batch_index + 1}/{total_batches} för {skanning_id}")
    print(f"   {len(frames)} frames, is_last={is_last}")
    
    # Initiera storage för denna skanning
    if skanning_id not in batch_storage:
        batch_storage[skanning_id] = {
            "frames": [],
            "positioner": [],
            "punkter_3d": [],
            "received_batches": 0,
            "karta_id": None
        }
    
    # Spara karta_id om det skickas (kan komma i vilken batch som helst)
    if karta_id:
        batch_storage[skanning_id]["karta_id"] = karta_id
    
    storage = batch_storage[skanning_id]
    
    # Spara frames till disk
    skanning_dir = f"/tmp/{skanning_id}"
    os.makedirs(skanning_dir, exist_ok=True)
    
    frame_offset = len(storage["frames"])
    for i, frame in enumerate(frames):
        frame_path = f"{skanning_dir}/frame_{frame_offset + i:04d}.jpg"
        content = await frame.read()
        with open(frame_path, "wb") as f:
            f.write(content)
        storage["frames"].append(frame_path)
    
    # Spara mesh-filer (kommer i sista batchen)
    if mesh:
        mesh_dir = f"{skanning_dir}/mesh"
        os.makedirs(mesh_dir, exist_ok=True)
        
        for mesh_fil in mesh:
            mesh_path = f"{mesh_dir}/{mesh_fil.filename}"
            content = await mesh_fil.read()
            with open(mesh_path, "wb") as f:
                f.write(content)
        
        print(f"   📦 Sparade {len(mesh)} mesh-filer till {mesh_dir}")
    
    # Lägg till positioner
    try:
        pos_list = json.loads(positioner)
        storage["positioner"].extend(pos_list)
        print(f"   ✅ Parsade {len(pos_list)} positioner")
    except Exception as e:
        print(f"   ❌ Kunde inte parsa positioner: {e}")
        print(f"   Raw data (första 200 tecken): {positioner[:200] if positioner else 'TOM'}")
    
    # Lägg till 3D-punkter
    try:
        punkter_list = json.loads(punkter_3d)
        storage["punkter_3d"].extend(punkter_list)
        print(f"   ✅ Parsade {len(punkter_list)} 3D-punkter")
    except Exception as e:
        print(f"   ❌ Kunde inte parsa punkter_3d: {e}")
        print(f"   Raw data (första 200 tecken): {punkter_3d[:200] if punkter_3d else 'TOM'}")
    
    storage["received_batches"] += 1
    
    print(f"   Totalt nu: {len(storage['frames'])} frames, {len(storage['punkter_3d'])} punkter")
    
    # Om sista batch - bygg kartan
    if is_last.lower() == "true":
        print(f"✅ Alla batches mottagna för {skanning_id}")
        
        # Hämta gång från första positionen
        gång = "Gång 1"
        if storage["positioner"]:
            gång = storage["positioner"][0].get("gång", "Gång 1")
        
        total_frames = len(storage["frames"])
        total_punkter = len(storage["punkter_3d"])
        
        print(f"📥 Skanning komplett: {skanning_id} ({gång})")
        print(f"   {total_frames} frames, {total_punkter} 3D-punkter")
        
        # Spara positioner till disk
        with open(f"{skanning_dir}/positioner.json", "w") as f:
            json.dump(storage["positioner"], f)
        print(f"   Sparade {len(storage['positioner'])} positioner till {skanning_dir}")
        
        # Spara 3D-punkter till disk
        with open(f"{skanning_dir}/punkter_3d.json", "w") as f:
            json.dump(storage["punkter_3d"], f)
        print(f"   Sparade {len(storage['punkter_3d'])} 3D-punkter till {skanning_dir}")
        
        # Uppdatera gång_index
        index_path = "/tmp/gång_index.json"
        try:
            gång_index = json.load(open(index_path)) if os.path.exists(index_path) else {}
        except:
            gång_index = {}
        gång_index[gång] = skanning_dir
        with open(index_path, "w") as f:
            json.dump(gång_index, f)
        print(f"   Uppdaterade gång_index: {gång} -> {skanning_dir}")
        
        # Kör loop closure
        korrigera_loop_closure(storage["positioner"])
        
        # Multi-session: använd lägg_till_session för att antingen skapa ny karta eller merga
        använd_karta_id = storage.get("karta_id")
        print(f"   karta_id: {använd_karta_id or 'INGEN — första skanning'}")
        
        asyncio.create_task(lägg_till_session_async(
            skanning_dir,
            storage["punkter_3d"],
            storage["positioner"],
            skanning_id,
            använd_karta_id
        ))
        
        # Rensa batch storage
        del batch_storage[skanning_id]
        
        return {
            "status": "complete",
            "skanning_id": skanning_id,
            "gång": gång,
            "frames": total_frames,
            "punkter_3d": total_punkter
        }
    
    return {
        "status": "batch_received",
        "skanning_id": skanning_id,
        "batch": batch_index + 1,
        "total": total_batches
    }

# =============================================
# BUTIKSKARTA OCH KALIBRERING
# =============================================
 
@app.post("/butik/{butik_id}/kartbild")
async def ladda_upp_kartbild(butik_id: str, bild: UploadFile = File(...)):
    """
    Ladda upp butikskartan (PNG/JPG).
    Exempel: POST /butik/bromma_maxi/kartbild med filen.
    """
    bild_bytes = await bild.read()
    resultat = spara_kartbild(butik_id, bild_bytes, bild.filename or "karta.png")
    return resultat
 
 
@app.get("/butik/{butik_id}/kartbild")
async def hämta_kartbild(butik_id: str):
    """Hämta butikskartan som bild."""
    path = hämta_kartbild_path(butik_id)
    if path is None:
        return {"fel": "Kartbild saknas"}
    return FileResponse(str(path))
 
 
@app.post("/butik/{butik_id}/kalibrera")
async def kalibrera_butik(butik_id: str, request: KalibreraRequest):
    """
    Kalibrera översättning mellan VPS-koordinater och kartpixlar.
    Skicka minst 3 referenspunkter.
    """
    punkter = [p.dict() for p in request.referenspunkter]
    return spara_kalibrering(butik_id, punkter)
 
 
@app.post("/butik/{butik_id}/vps-till-pixel")
async def översätt_vps_till_pixel(butik_id: str, koord: VpsKoordinat):
    """
    Översätt VPS-koordinat (x, z i meter) till pixelposition på kartan.
    Används av iOS-klienten för att rita blå prick.
    """
    resultat = vps_till_pixel(butik_id, koord.x, koord.z)
    if resultat is None:
        return {"fel": "Butik ej kalibrerad"}
    return resultat
 
 
@app.post("/butik/{butik_id}/pixel-till-vps")
async def översätt_pixel_till_vps(butik_id: str, koord: PixelKoordinat):
    """
    Översätt pixelposition på kartan till VPS-koordinat.
    Används när personal trycker på kartan för att märka produktposition.
    """
    resultat = pixel_till_vps(butik_id, koord.pixel_x, koord.pixel_y)
    if resultat is None:
        return {"fel": "Butik ej kalibrerad"}
    return resultat
 
 
@app.get("/butik/{butik_id}")
async def hämta_butik_status(butik_id: str):
    """Status för en butik: har den kartbild och kalibrering?"""
    return butik_status(butik_id)
 
 
@app.get("/butiker")
async def hämta_alla_butiker():
    """Lista alla konfigurerade butiker."""
    return {"butiker": lista_butiker()}


@app.post("/preflight")
async def preflight_endpoint(bild: UploadFile = File(...)):
    """
    Identifiera vilken karta användaren är vid innan skanning.
    """
    bild_bytes = await bild.read()
    print(f"📍 Preflight: {len(bild_bytes)//1024} KB")
    
    resultat = preflight(bild_bytes)
    print(f"   Status: {resultat.get('status')}, karta: {resultat.get('karta_id')}, inliers: {resultat.get('inliers', '?')}")
    
    return resultat


@app.get("/kartor")
async def hämta_alla_kartor():
    """Lista alla befintliga kartor."""
    kartor = lista_alla_kartor()
    info = []
    for namn in kartor:
        karta_dir = Path(f"/home/hartman/ICA_ai/BackendPulsAr/data/kartor/{namn}")
        meta_path = karta_dir / "metadata.json"
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            info.append({
                "namn": namn,
                "antal_frames": len(meta.get("frames", [])),
                "antal_sessioner": len(meta.get("session_log", [])),
            })
    return {"kartor": info}
    
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
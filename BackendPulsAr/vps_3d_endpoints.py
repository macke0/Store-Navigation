"""
vps_3d_endpoints.py — FastAPI endpoints för VPS 3D
"""

from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks, Request
import json
import os
import time
import shutil
from pathlib import Path
from typing import Optional, List

router = APIRouter(tags=["VPS 3D"])

@router.post("/debug-upload/")
async def debug_upload(request: Request):
    """Se exakt vad som kommer in."""
    print(f"🔍 Content-Type: {request.headers.get('content-type')}")
    
    body = await request.body()
    print(f"🔍 Body size: {len(body)} bytes")
    print(f"🔍 Body start: {body[:500]}")
    
    return {"size": len(body), "content_type": request.headers.get('content-type')}

@router.post("/skanna-video-3d/")
async def skanna_video_3d(
    request: Request,
    background_tasks: BackgroundTasks,
    positioner: str = Form("[]"),
    punkter_3d: str = Form("[]"),
    frames: List[UploadFile] = File(default=[]),
):

    # Debug
    print(f"🔥 Headers: {dict(request.headers)}")
    print(f"🔥 Content-Type: {request.headers.get('content-type')}")
    
    """Ta emot skanning med 3D-punkter från LiDAR."""
    
    # Säkerställ att frames är en lista
    if frames is None:
        frames = []
    
    print(f"🔥 Mottog request!")
    print(f"   Frames: {len(frames)}")
    
    timestamp = int(time.time())
    pos_data = json.loads(positioner) if positioner else []
    
    gång_namn = pos_data[0].get("gång", f"skanning_{timestamp}") if pos_data else f"skanning_{timestamp}"
    säker_namn = gång_namn.replace(" ", "_").replace("/", "_")
    skanning_dir = f"/tmp/skanning_3d_{säker_namn}_{timestamp}"
    os.makedirs(skanning_dir, exist_ok=True)
    
    print(f"📥 Tar emot 3D-skanning: {gång_namn}")
    
    # Spara frames
    for frame in frames:
        frame_path = f"{skanning_dir}/{frame.filename}"
        content = await frame.read()
        with open(frame_path, "wb") as f:
            f.write(content)
    
    # Spara positioner
    with open(f"{skanning_dir}/positioner.json", "w") as f:
        json.dump(pos_data, f)
    
    # Spara 3D-punkter
    punkter_data = json.loads(punkter_3d) if punkter_3d else []
    with open(f"{skanning_dir}/punkter_3d.json", "w") as f:
        json.dump(punkter_data, f)
    
    print(f"   3D-punkter: {len(punkter_data)}")
    
    # Bygg karta i bakgrunden
    if frames:
        background_tasks.add_task(
            _bygg_karta_bakgrund,
            skanning_dir,
            gång_namn,
            pos_data,
            punkter_data
        )
    
    return {
        "status": "ok",
        "meddelande": f"Skanning mottagen för {gång_namn}",
        "frames": len(frames),
        "punkter_3d": len(punkter_data),
        "bygger_karta": len(frames) > 0
    }


async def _bygg_karta_bakgrund(skanning_dir, gång_namn, positioner, punkter_3d):
    """Bygg 3D-karta i bakgrunden."""
    try:
        from core.vps_3d import bygg_3d_karta
        print(f"🔧 Startar kartbygge för {gång_namn}...")
        karta_path = bygg_3d_karta(
            skanning_dir=skanning_dir,
            punkter_3d=punkter_3d,
            positioner=positioner,
            gång_namn=gång_namn
        )
        if karta_path:
            print(f"✅ Karta klar: {karta_path}")
        else:
            print(f"⚠️  Karta kunde inte byggas")
    except Exception as e:
        print(f"❌ Fel vid kartbygge: {e}")
        import traceback
        traceback.print_exc()


@router.post("/lokalisera/")
async def lokalisera_endpoint(
    bild: UploadFile = File(...),
    gång: Optional[str] = Form(None),
    debug: bool = Form(False),
):
    """Lokalisera med VPS."""
    from core.vps_3d import lokalisera
    bild_bytes = await bild.read()
    # DEBUG: spara bilden
    with open("/tmp/debug_vps_image.jpg", "wb") as f:
        f.write(bild_bytes)
    import cv2, numpy as np
    img = cv2.imdecode(np.frombuffer(bild_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is not None:
        print(f"📷 VPS-bild: {img.shape[1]}x{img.shape[0]}, {len(bild_bytes)//1024} KB")
    else:
        print(f"📷 Kunde INTE läsa bilden! {len(bild_bytes)} bytes")
    return lokalisera(bild_bytes, gång=gång, debug=debug)


@router.get("/vps/kartor")
async def lista_kartor():
    """Lista alla VPS-kartor."""
    kartor = []
    kartor_dir = Path("/home/hartman/ICA_ai/BackendPulsAr/data/kartor")
    
    if kartor_dir.exists():
        for karta_path in kartor_dir.iterdir():
            if karta_path.is_dir() and (karta_path / "metadata.json").exists():
                with open(karta_path / "metadata.json") as f:
                    meta = json.load(f)
                kartor.append({
                    "namn": meta.get("gång", karta_path.name),
                    "frames": meta.get("antal_frames", 0),
                    "punkter_3d": meta.get("antal_3d_punkter", 0),
                    "version": meta.get("version", "1.0"),
                })
    
    return {"kartor": kartor, "antal": len(kartor)}


@router.delete("/vps/karta/{gång_namn}")
async def radera_karta(gång_namn: str):
    """Radera en VPS-karta."""
    from core.vps_3d import Karta3DCache
    
    säker_namn = gång_namn.replace(" ", "_").replace("/", "_")
    karta_dir = Path(f"/home/hartman/ICA_ai/BackendPulsAr/data/kartor/{säker_namn}")
    
    if karta_dir.exists():
        shutil.rmtree(karta_dir)
        Karta3DCache.rensa()
        return {"raderad": True}
    return {"raderad": False}


@router.get("/vps/status")
async def vps_status():
    """Status för VPS-systemet."""
    import json
    import os
    from core.vps_3d import Karta3DCache, extractor, matcher, device
    
    karta_namn = Karta3DCache.lista()
    kartor = []
    
    for namn in karta_namn:
        karta_dir = f"/home/hartman/ICA_ai/BackendPulsAr/data/kartor/{namn.replace(' ', '_')}"
        meta_path = f"{karta_dir}/metadata.json"
        
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            kartor.append({
                "gång": namn,
                "antal_frames": len(meta.get("frames", [])),
                "antal_desc": meta.get("antal_3d_punkter", 0),
                "loopar": meta.get("loopar", 0),
                "luckor": meta.get("luckor", 0),
                "merges": meta.get("merges", 0),
                "täckning": {"täckning": meta.get("täckning", 0)}
            })
        else:
            kartor.append({
                "gång": namn,
                "antal_frames": 0,
                "antal_desc": 0,
                "loopar": 0,
                "luckor": 0,
                "merges": 0,
                "täckning": {"täckning": 0}
            })
    
    return {
        "status": "ok",
        "device": str(device),
        "superpoint": extractor is not None,
        "lightglue": matcher is not None,
        "kartor": kartor,
        "version": "2.0-lightglue"
    }
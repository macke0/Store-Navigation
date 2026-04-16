"""
butik_endpoints.py — API-endpoints för butiksmodelle
───────────────────────────────────────────────────────
Hanterar scan-sessioner, batch-upload, och kartbygge.

Endpoints:
  POST /scan/start          — Starta ny session
  POST /scan/resume/{id}    — Fortsätt pausad session
  POST /scan/pause/{id}     — Pausa session
  POST /scan/stop/{id}      — Avsluta session
  POST /scan/upload         — Ladda upp batch (frames + data)
  POST /scan/bygg-karta     — Bygg global karta
  GET  /scan/status         — Status för allt
  DELETE /scan/session/{id} — Radera en session
"""

from fastapi import APIRouter, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import List, Optional
import json
import time

from core.butik_modell import get_butik

router = APIRouter(prefix="/scan", tags=["Scanning"])


@router.post("/start")
async def starta_session():
    """Starta en ny skanning-session."""
    butik = get_butik()
    session = butik.ny_session()
    
    return {
        "status": "ok",
        "session_id": session.session_id,
        "meddelande": f"Session startad. Ladda upp frames via /scan/upload"
    }


@router.post("/resume/{session_id}")
async def fortsätt_session(session_id: str):
    """Fortsätt en pausad session."""
    butik = get_butik()
    session = butik.fortsätt_session(session_id)
    
    if session:
        return {
            "status": "ok",
            "session_id": session.session_id,
            "befintliga_frames": session.antal_frames,
            "meddelande": "Session återupptagen"
        }
    
    return JSONResponse(
        status_code=404,
        content={"error": f"Session '{session_id}' hittades inte eller är inte pausad"}
    )


@router.post("/pause/{session_id}")
async def pausa_session(session_id: str):
    """Pausa en aktiv session. Kan fortsättas senare."""
    butik = get_butik()
    butik.pausa_session(session_id)
    
    session = butik.sessioner.get(session_id)
    return {
        "status": "ok",
        "session_id": session_id,
        "frames_sparade": session.antal_frames if session else 0,
        "meddelande": "Session pausad. Använd /scan/resume för att fortsätta."
    }


@router.post("/stop/{session_id}")
async def avsluta_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    auto_bygg: bool = True
):
    """
    Avsluta session. Om auto_bygg=true, bygg om global karta automatiskt.
    """
    butik = get_butik()
    butik.avsluta_session(session_id)
    
    session = butik.sessioner.get(session_id)
    
    # Kolla om nya data överlappar gamla sessioner
    if session:
        överlapp = butik.hitta_överlappande_sessioner(session)
        if överlapp:
            print(f"🔄 Session {session_id} överlappar med: {överlapp}")
    
    resultat = {
        "status": "ok",
        "session_id": session_id,
        "frames": session.antal_frames if session else 0,
        "punkter_3d": session.antal_punkter if session else 0,
    }
    
    # Bygg karta i bakgrunden
    if auto_bygg and butik.behöver_ombyggnad():
        background_tasks.add_task(_bygg_karta_bakgrund)
        resultat["bygger_karta"] = True
        resultat["meddelande"] = "Session klar. Kartan byggs i bakgrunden."
    else:
        resultat["bygger_karta"] = False
        resultat["meddelande"] = "Session klar."
    
    return resultat


@router.post("/upload")
async def ladda_upp_batch(
    session_id: str = Form(...),
    batch_index: int = Form(0),
    total_batches: int = Form(1),
    is_last: str = Form("false"),
    positioner: str = Form("[]"),
    punkter_3d: str = Form("[]"),
    frames: List[UploadFile] = File(default=[]),
):
    """
    Ladda upp en batch av frames + data till en session.
    Samma format som befintlig batch-upload.
    """
    butik = get_butik()
    session = butik.sessioner.get(session_id)
    
    if not session:
        # Skapa session automatiskt om den inte finns
        session = butik.ny_session()
        session.session_id = session_id  # Behåll klientens ID
        butik.sessioner[session_id] = session
    
    # Läs frames
    frame_data = []
    for frame in frames:
        content = await frame.read()
        frame_data.append((frame.filename, content))
    
    # Parsa JSON
    pos_data = json.loads(positioner) if positioner else []
    pkt_data = json.loads(punkter_3d) if punkter_3d else []
    
    # Lägg till i session
    butik.lägg_till_batch(
        session_id=session.session_id,
        frames=frame_data,
        positioner=pos_data,
        punkter_3d=pkt_data,
        batch_index=batch_index,
    )
    
    return {
        "status": "ok",
        "session_id": session.session_id,
        "batch": batch_index,
        "frames_i_batch": len(frame_data),
        "totalt_frames": session.antal_frames,
        "totalt_punkter": session.antal_punkter,
    }


@router.post("/bygg-karta")
async def bygg_karta(background_tasks: BackgroundTasks):
    """Bygg om global karta från alla sessioner."""
    butik = get_butik()
    
    if not butik.behöver_ombyggnad():
        return {
            "status": "ok",
            "meddelande": "Kartan är redan uppdaterad",
            "version": butik.global_karta_version
        }
    
    background_tasks.add_task(_bygg_karta_bakgrund)
    
    return {
        "status": "ok",
        "meddelande": "Kartbygge startat i bakgrunden",
        "nuvarande_version": butik.global_karta_version,
    }


@router.get("/status")
async def scan_status():
    """Status för butiksmodellen och alla sessioner."""
    butik = get_butik()
    return butik.status()


@router.delete("/session/{session_id}")
async def radera_session(session_id: str):
    """Radera en session och dess data."""
    butik = get_butik()
    
    if session_id not in butik.sessioner:
        return JSONResponse(
            status_code=404,
            content={"error": f"Session '{session_id}' hittades inte"}
        )
    
    butik.ta_bort_session(session_id)
    return {"status": "ok", "raderad": session_id}


@router.get("/sessioner")
async def lista_sessioner():
    """Lista alla sessioner med detaljer."""
    butik = get_butik()
    
    sessioner = []
    for sid, s in butik.sessioner.items():
        sessioner.append({
            **s.to_dict(),
            "varaktighet": (s.slut_tid or time.time()) - s.start_tid,
        })
    
    return {
        "antal": len(sessioner),
        "sessioner": sessioner
    }


@router.post("/rescan")
async def rescan_område(
    session_id: str = Form(...),
    background_tasks: BackgroundTasks = None,
):
    """
    Markera en session som re-scan.
    Gamla sessioner som överlappar tas bort automatiskt.
    """
    butik = get_butik()
    session = butik.sessioner.get(session_id)
    
    if not session:
        return JSONResponse(status_code=404, content={"error": "Session hittades inte"})
    
    # Hitta och ta bort överlappande
    överlapp = butik.hitta_överlappande_sessioner(session)
    for sid in överlapp:
        butik.ta_bort_session(sid)
    
    resultat = {
        "status": "ok",
        "ersatta_sessioner": överlapp,
        "antal_ersatta": len(överlapp),
    }
    
    # Bygg om karta
    if överlapp and background_tasks:
        background_tasks.add_task(_bygg_karta_bakgrund)
        resultat["bygger_karta"] = True
    
    return resultat


# ─────────────────────────────────────────────
# BAKGRUNDSUPPGIFTER
# ─────────────────────────────────────────────

async def _bygg_karta_bakgrund():
    """Bygg global karta i en separat tråd (blockerar inte servern)."""
    import asyncio
    def _bygg():
        try:
            butik = get_butik()
            butik.bygg_global_karta()
        except Exception as e:
            print(f"❌ Kartbygge misslyckades: {e}")
            import traceback
            traceback.print_exc()
    await asyncio.to_thread(_bygg)

@router.get("/täckning")
async def skannad_täckning():
    """Returnera alla skannade positioner för att visa på karta."""
    butik = get_butik()
    
    alla_positioner = []
    for sid, session in butik.sessioner.items():
        if session.status not in ("klar", "pausad"):
            continue
        pos_path = session.session_dir / "positioner.json"
        if pos_path.exists():
            import json
            with open(pos_path) as f:
                pos = json.load(f)
            for p in pos:
                alla_positioner.append({
                    "x": p.get("x", 0),
                    "z": p.get("z", 0),
                    "session": sid
                })
    
    return {
        "antal_punkter": len(alla_positioner),
        "positioner": alla_positioner
    }


# Kartbygge-progress (global variabel)
_bygg_progress = {"status": "idle", "steg": "", "procent": 0}

def uppdatera_progress(steg: str, procent: int):
    global _bygg_progress
    _bygg_progress = {"status": "bygger", "steg": steg, "procent": procent}

@router.get("/bygg-status")
async def bygg_status():
    """Kolla progress för kartbygge."""
    butik = get_butik()
    return {
        **_bygg_progress,
        "karta_version": butik.global_karta_version,
        "senast_byggd": butik.senast_byggd,
    }

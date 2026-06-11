"""
chat_endpoints.py - FastAPI endpoints för Puls-AR chat
─────────────────────────────────────────────────────────────────
Lägg till dessa endpoints i din server.py:

    from chat_endpoints import chat_router
    app.include_router(chat_router, prefix="/chat", tags=["Chat"])

Eller kopiera in koden direkt.
"""

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
import json
import uuid

from core.claude_assistant import get_session_manager
from core.produkt_sok import get_produkt_sök
from core.produkt_skanning import läs_konsoliderade
from core.matratter import foresla_matratter

chat_router = APIRouter()


# ─────────────────────────────────────────────
# REQUEST/RESPONSE MODELS
# ─────────────────────────────────────────────

class ChatRequest(BaseModel):
    meddelande: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    svar: str
    session_id: str


class SökRequest(BaseModel):
    query: str
    limit: Optional[int] = 5


class SökResponse(BaseModel):
    query: str
    antal: int
    resultat: list


class NySessionResponse(BaseModel):
    session_id: str
    meddelande: str


class KundAssistentRequest(BaseModel):
    meddelande: str
    session_id: Optional[str] = None
    karta: str = "hela_butiken"


class KundAssistentResponse(BaseModel):
    svar: str
    session_id: str
    produkter: list


class MaträttRequest(BaseModel):
    meddelande: str
    karta: str = "hela_butiken"


class MaträttResponse(BaseModel):
    matratter: list


def _extrahera_produkter_ur_historik(historik: list) -> list:
    """
    Plocka ut produkter ur senaste tool_result i sessionshistoriken så att
    klienten kan visa en "Hitta i butiken"-knapp per produkt.

    Letar efter arrayerna produkter / alternativ / nyttigare_alternativ som
    _kör_tool returnerar, och tar den senaste.
    """
    senaste: list = []
    for meddelande in historik:
        innehåll = meddelande.get("content")
        if not isinstance(innehåll, list):
            continue
        for block in innehåll:
            if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                continue
            try:
                data = json.loads(block.get("content", ""))
            except (json.JSONDecodeError, TypeError):
                continue
            for nyckel in ("produkter", "alternativ", "nyttigare_alternativ"):
                lista = data.get(nyckel)
                if isinstance(lista, list) and lista:
                    senaste = [
                        {"produkt_id": p.get("id"), "visningsnamn": p.get("namn")}
                        for p in lista
                        if isinstance(p, dict) and p.get("id")
                    ]
    return senaste


# ─────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────

@chat_router.post("/", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Unified chat med Claude-assistenten.
    
    Skicka vad som helst:
    - "ica soja" → söker produkter
    - "berätta mer om den första" → produktinfo
    - "finns något nyttigare?" → nyttigare alternativ
    - "var finns den?" → position i butiken
    
    Session hålls automatiskt om session_id skickas.
    """
    try:
        session_manager = get_session_manager()
        
        # Skapa ny session om ingen angiven
        session_id = request.session_id
        if not session_id:
            session_id = str(uuid.uuid4())
        
        # Kör chat
        resultat = session_manager.chat(session_id, request.meddelande)
        
        return ChatResponse(
            svar=resultat["svar"],
            session_id=session_id
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.post("/kund/assistent", response_model=KundAssistentResponse)
async def kund_assistent(request: KundAssistentRequest):
    """
    Kund-flöde: chatta med assistenten och få tillbaka en lista produkter som
    klienten kan slå upp med POST /kund/hitta-produkt.

    Matar in konsoliderade produktpositioner i assistentens produkt_db så att
    verktyget hämta_produktposition kan returnera riktiga kartkoordinater.
    """
    try:
        session_manager = get_session_manager()

        # Mata in riktiga positioner från kartan i assistentens produkt_db
        produkt_db = {
            p["id"]: {
                "visningsnamn": p.get("visningsnamn"),
                "x": p.get("x"),
                "y": p.get("y", 0),
                "z": p.get("z"),
            }
            for p in läs_konsoliderade(request.karta)
            if p.get("id")
        }
        session_manager.uppdatera_produkt_db(produkt_db)

        session_id = request.session_id or str(uuid.uuid4())
        resultat = session_manager.chat(session_id, request.meddelande)

        produkter = _extrahera_produkter_ur_historik(
            session_manager.sessioner.get(session_id, [])
        )

        # Berika med kartposition så att klienten kan navigera direkt
        # utan att slå upp positionen separat.
        for p in produkter:
            pos = produkt_db.get(p.get("produkt_id"))
            if pos:
                p["x"] = pos.get("x")
                p["y"] = pos.get("y")
                p["z"] = pos.get("z")

        return KundAssistentResponse(
            svar=resultat["svar"],
            session_id=session_id,
            produkter=produkter,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.post("/kund/matratter", response_model=MaträttResponse)
async def kund_matratter(request: MaträttRequest):
    """
    Kund-flöde: föreslå maträtter utifrån kundens önskemål. Claude komponerar
    rätterna; varje ingrediens berikas med riktigt pris, kampanj, bild och
    kartposition från butikens sortiment, plus total kostnad och besparing.

    Klienten visar maträtterna som bläddringsbara kort med bild, och vid klick
    ingredienslista som kan läggas i inköpslista.
    """
    try:
        return MaträttResponse(**foresla_matratter(request.meddelande, request.karta))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@chat_router.get("/ny-session", response_model=NySessionResponse)
async def ny_session():
    """Skapa en ny chat-session."""
    session_manager = get_session_manager()
    session_id = session_manager.ny_session()
    
    return NySessionResponse(
        session_id=session_id,
        meddelande="Ny session skapad. Skicka denna session_id med dina meddelanden."
    )


@chat_router.delete("/session/{session_id}")
async def rensa_session(session_id: str):
    """Rensa en chat-session (radera historik)."""
    session_manager = get_session_manager()
    session_manager.rensa_session(session_id)
    return {"status": "ok", "meddelande": f"Session {session_id} rensad"}


@chat_router.post("/sök", response_model=SökResponse)
async def sök_endpoint(request: SökRequest):
    """
    Enkel produktsökning utan Claude.
    Snabbare och billigare för enkel sökning.
    
    Fuzzy matching - exakt stavning krävs inte:
    - "ica soja" hittar "ICA Sojadryck Naturell"
    - "cola zero" hittar "Coca-Cola Zero"
    """
    sök = get_produkt_sök()
    resultat = sök.sök(request.query, request.limit)
    
    return SökResponse(
        query=request.query,
        antal=len(resultat),
        resultat=resultat
    )


@chat_router.get("/produkt/{produkt_id}")
async def hämta_produkt(produkt_id: str):
    """Hämta en specifik produkt via ID."""
    sök = get_produkt_sök()
    produkt = sök.hämta(produkt_id)
    
    if not produkt:
        raise HTTPException(status_code=404, detail="Produkt hittades inte")
    
    return produkt


@chat_router.get("/produkt/{produkt_id}/liknande")
async def liknande_produkter(produkt_id: str, limit: int = 5):
    """Hämta liknande produkter (för om produkten är slut)."""
    sök = get_produkt_sök()
    resultat = sök.hitta_liknande(produkt_id, limit)
    
    if not resultat:
        raise HTTPException(status_code=404, detail="Inga liknande produkter hittades")
    
    return {"produkt_id": produkt_id, "liknande": resultat}


@chat_router.get("/produkt/{produkt_id}/nyttigare")
async def nyttigare_alternativ(produkt_id: str, limit: int = 5):
    """Hämta nyttigare alternativ till en produkt."""
    sök = get_produkt_sök()
    resultat = sök.hitta_nyttigare(produkt_id, limit)
    
    if not resultat:
        raise HTTPException(status_code=404, detail="Inga nyttigare alternativ hittades")
    
    return {"produkt_id": produkt_id, "nyttigare_alternativ": resultat}


# ─────────────────────────────────────────────
# STANDALONE SERVER (för testning)
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    from fastapi import FastAPI
    
    app = FastAPI(
        title="Puls-AR Chat API",
        description="Claude-powered butiksassistent för ICA Maxi"
    )
    
    app.include_router(chat_router, prefix="/chat", tags=["Chat"])
    
    @app.get("/")
    async def root():
        return {
            "meddelande": "Puls-AR Chat API",
            "endpoints": {
                "POST /chat/": "Skicka meddelande till assistenten",
                "GET /chat/ny-session": "Skapa ny session",
                "POST /chat/sök": "Enkel produktsökning",
                "GET /chat/produkt/{id}": "Hämta produkt",
                "GET /chat/produkt/{id}/liknande": "Liknande produkter",
                "GET /chat/produkt/{id}/nyttigare": "Nyttigare alternativ"
            }
        }
    
    print("🚀 Startar Puls-AR Chat API på http://0.0.0.0:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)
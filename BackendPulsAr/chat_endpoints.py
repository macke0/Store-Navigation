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
import uuid

from core.claude_assistant import get_session_manager
from core.produkt_sok import get_produkt_sök

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
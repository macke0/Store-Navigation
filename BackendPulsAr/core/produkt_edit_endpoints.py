"""
produkt_edit_endpoints.py — API för manuell produktredigering
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from core.produkt_voting import get_voting

router = APIRouter(prefix="/produkter", tags=["Produktredigering"])


class KorrigeringRequest(BaseModel):
    position_id: str
    namn: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None


class NyProduktRequest(BaseModel):
    namn: str
    x: float
    y: float = 1.5
    z: float


@router.get("/identifierade")
async def lista_identifierade():
    """Lista alla identifierade produkter med konfidens."""
    voting = get_voting()
    produkter = voting.hämta_produkter()
    
    return {
        "antal": len(produkter),
        "produkter": produkter,
        "manuella_korrigeringar": len(voting.manuella)
    }


@router.post("/korrigera")
async def korrigera_produkt(req: KorrigeringRequest):
    """Korrigera namn eller position på en identifierad produkt."""
    voting = get_voting()
    
    resultat = voting.korrigera(
        position_id=req.position_id,
        namn=req.namn,
        x=req.x,
        y=req.y,
        z=req.z
    )
    
    return resultat


@router.delete("/korrigera/{position_id}")
async def ta_bort_korrigering(position_id: str):
    """Ta bort en manuell korrigering."""
    voting = get_voting()
    return voting.korrigera(position_id=position_id, ta_bort=True)


@router.post("/lägg-till")
async def lägg_till_produkt(req: NyProduktRequest):
    """Lägg till en ny produkt manuellt."""
    voting = get_voting()
    return voting.lägg_till_manuell(
        namn=req.namn,
        x=req.x,
        y=req.y,
        z=req.z
    )


@router.get("/korrigeringar")
async def lista_korrigeringar():
    """Lista alla manuella korrigeringar."""
    voting = get_voting()
    return {
        "antal": len(voting.manuella),
        "korrigeringar": voting.manuella
    }
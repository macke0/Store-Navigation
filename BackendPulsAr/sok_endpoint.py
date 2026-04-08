"""
Smart produktsökning endpoint för Puls-AR.

Haiku ser produkter och väljer de relevanta.
Resultat cachas permanent → nästa sökning instant.

Importera i server.py:
    from sok_endpoint import setup_sok_routes
    setup_sok_routes(app)
"""
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
import sys
import os

# Lägg till core i path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.smart_sok import SmartSök

# Global sökning-instans (laddas en gång)
_smart_sök = None


def get_smart_sök():
    """Hämta eller skapa SmartSök-instans."""
    global _smart_sök
    if _smart_sök is None:
        _smart_sök = SmartSök(
            'data/ica_produkter.json',
            'data/sok_cache.json'
        )
    return _smart_sök


def setup_sok_routes(app: FastAPI):
    """
    Registrera sök-endpoints.
    
    Endpoints:
        GET /sok?q=...  - Sök produkter (intent-baserad, <50ms för kända sökningar)
        GET /produkt/{id} - Hämta specifik produkt
    """
    
    @app.get("/sok")
    async def sök_produkter(q: str = Query(..., description="Sökterm")):
        """
        Sök efter produkter med smart intent-matching.
        
        Snabbhet:
        - Känd sökning: <50ms (intent-match)
        - Ny sökning: ~2s första gången (Claude), sedan instant
        
        Returnerar:
        {
            "query": "mjölk",
            "antal": 22,
            "ai_powered": true,
            "produkter": [...]
        }
        """
        if not q or len(q.strip()) < 1:
            return JSONResponse({"query": q, "antal": 0, "produkter": [], "ai_powered": True})
        
        sök = get_smart_sök()
        resultat = await sök.sök(q.strip(), limit=30)
        
        # Formatera för iOS-appen
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
        
        return {
            "query": q.strip(),
            "antal": len(produkter),
            "ai_powered": True,
            "produkter": produkter
        }
    
    @app.get("/produkt/{produkt_id}")
    async def hämta_produkt(produkt_id: str):
        """
        Hämta en specifik produkt.
        """
        sök = get_smart_sök()
        
        if produkt_id in sök.id_to_produkt:
            p = sök.id_to_produkt[produkt_id]
            return {
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
            }
        
        return JSONResponse(
            status_code=404,
            content={"error": f"Produkt '{produkt_id}' hittades inte"}
        )
    
    @app.get("/cache")
    async def lista_cache():
        """
        Lista alla cachade sökningar.
        """
        sök = get_smart_sök()
        return {
            "antal_cachade": len(sök.cache),
            "sökningar": list(sök.cache.keys())[:50]
        }
    
    @app.delete("/cache")
    async def rensa_cache(q: str = None):
        """
        Rensa cache för en sökning eller alla.
        """
        sök = get_smart_sök()
        sök.rensa_cache(q)
        return {"status": "ok", "rensat": q or "allt"}
    
    @app.get("/")
    async def root():
        """API-information."""
        return {
            "namn": "Puls-AR Smart Sök API",
            "version": "3.0",
            "endpoints": {
                "/sok?q=...": "Sök produkter (Haiku AI)",
                "/produkt/{id}": "Hämta produkt",
                "/cache": "Lista cachade sökningar",
                "DELETE /cache?q=...": "Rensa cache"
            }
        }
    
    print("✅ Smart sök-routes registrerade")
    print("   🔍 GET /sok?q=...  — Haiku AI-sökning")
    print("   📦 GET /produkt/{id} — Hämta produkt")
    print("   💾 GET /cache — Visa cachade sökningar")
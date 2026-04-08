"""
vps_endpoints.py — VPS Admin & Debug endpoints v2
───────────────────────────────────────────────────
Nya funktioner:
  - Radera karta
  - Merge/slå ihop skanningar
  - Täckningsanalys
  - Loop-detection
"""

import os
import json
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional


def setup_vps_routes(app: FastAPI):
    """Registrerar alla VPS och debug endpoints."""
    
    # ─────────────────────────────────────────────
    # VPS STATUS & ADMIN
    # ─────────────────────────────────────────────
    
    @app.get("/vps/admin")
    async def vps_admin_sida():
        """Serverar VPS admin-sidan."""
        html_path = os.path.join(os.path.dirname(__file__), "vps_admin.html")
        if os.path.exists(html_path):
            with open(html_path, encoding="utf-8") as f:
                return HTMLResponse(content=f.read())
        return HTMLResponse(content="<h1>vps_admin.html saknas</h1>", status_code=404)
    
    
    @app.get("/vps/status")
    async def vps_status():
        """Returnerar status för alla VPS-kartor."""
        kartor_dir = "/tmp/kartor"
        if not os.path.exists(kartor_dir):
            return {"kartor": [], "antal": 0, "totalt_descriptors": 0, "totalt_frames": 0}
        
        kartor = []
        totalt_desc = 0
        totalt_frames = 0
        
        for gång_dir in os.listdir(kartor_dir):
            meta_path = f"{kartor_dir}/{gång_dir}/metadata.json"
            if os.path.exists(meta_path):
                with open(meta_path) as f:
                    meta = json.load(f)
                kartor.append({
                    "gång": meta.get("gång", gång_dir),
                    "antal_frames": meta.get("antal_frames", 0),
                    "antal_desc": meta.get("antal_desc", 0),
                    "loopar": meta.get("loopar", 0),
                    "luckor": meta.get("luckor", 0),
                    "täckning": meta.get("täckning", {}),
                    "merges": meta.get("merges", 0),
                    "skapad": meta.get("skapad", ""),
                    "senast_uppdaterad": meta.get("senast_uppdaterad", ""),
                })
                totalt_desc += meta.get("antal_desc", 0)
                totalt_frames += meta.get("antal_frames", 0)
        
        return {
            "kartor": kartor,
            "antal": len(kartor),
            "totalt_descriptors": totalt_desc,
            "totalt_frames": totalt_frames,
        }
    
    
    @app.get("/vps/karta/{gång_namn}")
    async def vps_karta_detaljer(gång_namn: str):
        """Returnerar detaljer för en specifik karta."""
        säker_namn = gång_namn.replace(" ", "_").replace("/", "_")
        karta_dir = f"/tmp/kartor/{säker_namn}"
        
        if not os.path.exists(karta_dir):
            raise HTTPException(status_code=404, detail="Karta finns inte")
        
        meta_path = f"{karta_dir}/metadata.json"
        pos_path = f"{karta_dir}/positioner.json"
        
        meta = {}
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
        
        positioner = []
        if os.path.exists(pos_path):
            with open(pos_path) as f:
                positioner = json.load(f)
        
        return {
            "gång": gång_namn,
            "metadata": meta,
            "antal_positioner": len(positioner),
        }
    
    
    @app.delete("/vps/karta/{gång_namn}")
    async def vps_radera_karta(gång_namn: str):
        """Raderar en VPS-karta."""
        from core.feature_karta import radera_karta
        
        # Normalisera namnet
        gång_namn = gång_namn.replace("_", " ")
        
        if radera_karta(gång_namn):
            return {"raderad": True, "gång": gång_namn}
        else:
            raise HTTPException(status_code=404, detail="Karta finns inte")
    
    
    @app.post("/vps/rebuild/{gång_namn}")
    async def vps_bygg_om_karta(gång_namn: str):
        """Bygger om en karta från befintlig skanning."""
        from core.feature_karta import bygg_karta, radera_karta
        
        # Normalisera namnet
        gång_namn = gång_namn.replace("_", " ")
        
        # Hitta skanning
        gång_index_fil = "/tmp/gång_index.json"
        if not os.path.exists(gång_index_fil):
            raise HTTPException(status_code=404, detail="Ingen skanning finns")
        
        with open(gång_index_fil) as f:
            gång_index = json.load(f)
        
        skanning_dir = gång_index.get(gång_namn)
        if not skanning_dir:
            raise HTTPException(status_code=404, detail=f"Skanning för {gång_namn} finns inte")
        
        pos_fil = f"{skanning_dir}/positioner.json"
        if not os.path.exists(pos_fil):
            raise HTTPException(status_code=404, detail="Positionsfil saknas")
        
        with open(pos_fil) as f:
            positioner = json.load(f)
        
        # Radera gammal karta
        radera_karta(gång_namn)
        
        # Bygg om
        resultat = bygg_karta(skanning_dir, positioner, gång_namn)
        
        if resultat:
            return {"ombyggd": True, "gång": gång_namn, "karta_dir": resultat}
        else:
            raise HTTPException(status_code=500, detail="Kunde inte bygga karta")
    
    
    # ─────────────────────────────────────────────
    # MERGE SKANNINGAR
    # ─────────────────────────────────────────────
    
    @app.post("/vps/merge/{gång_namn}")
    async def vps_merge_skanning(gång_namn: str, skanning_id: Optional[str] = None):
        """
        Slår ihop en ny skanning med befintlig karta.
        Om skanning_id inte anges, används den senaste skanningen för gången.
        """
        from core.feature_karta import slå_ihop_skanningar
        
        # Normalisera namnet
        gång_namn = gång_namn.replace("_", " ")
        
        # Hitta skanning
        gång_index_fil = "/tmp/gång_index.json"
        if not os.path.exists(gång_index_fil):
            raise HTTPException(status_code=404, detail="Ingen skanning finns")
        
        with open(gång_index_fil) as f:
            gång_index = json.load(f)
        
        skanning_dir = gång_index.get(gång_namn)
        if not skanning_dir:
            raise HTTPException(status_code=404, detail=f"Skanning för {gång_namn} finns inte")
        
        pos_fil = f"{skanning_dir}/positioner.json"
        if not os.path.exists(pos_fil):
            raise HTTPException(status_code=404, detail="Positionsfil saknas")
        
        with open(pos_fil) as f:
            positioner = json.load(f)
        
        # Merge
        resultat = slå_ihop_skanningar(gång_namn, skanning_dir, positioner)
        
        return resultat
    
    
    @app.get("/vps/tackning/{gång_namn}")
    async def vps_täckning(gång_namn: str):
        """Analyserar täckningen för en karta."""
        from core.feature_karta import beräkna_täckning, detektera_loopar, hitta_luckor
        
        # Normalisera namnet
        gång_namn = gång_namn.replace("_", " ")
        säker_namn = gång_namn.replace(" ", "_")
        karta_dir = f"/tmp/kartor/{säker_namn}"
        
        pos_path = f"{karta_dir}/positioner.json"
        if not os.path.exists(pos_path):
            raise HTTPException(status_code=404, detail="Karta finns inte")
        
        with open(pos_path) as f:
            positioner = json.load(f)
        
        # Analysera
        täckning = beräkna_täckning(positioner)
        loopar = detektera_loopar(positioner)
        luckor = hitta_luckor(positioner)
        
        return {
            "gång": gång_namn,
            "täckning": täckning,
            "loopar": len(loopar),
            "loop_detaljer": loopar[:10],  # Max 10 visas
            "luckor": len(luckor),
            "lucka_detaljer": luckor[:10],
        }
    
    
    # ─────────────────────────────────────────────
    # DEBUG ENDPOINTS
    # ─────────────────────────────────────────────
    
    @app.post("/debug/lokalisera")
    async def debug_lokalisera(bild: UploadFile = File(...), gång: Optional[str] = None):
        """Testa VPS-lokalisering med en bild."""
        from core.lokalisering import lokalisera_kund
        
        bild_bytes = await bild.read()
        resultat = lokalisera_kund(bild_bytes, debug=True)
        
        return resultat
    
    
    @app.post("/debug/qwen")
    async def debug_qwen(bild: UploadFile = File(...), mode: str = "debug"):
        """Testa Qwen på en bild."""
        from core.qwen import fråga_qwen_vllm, är_vllm_igång
        
        if not är_vllm_igång():
            return {"error": "vLLM är inte igång", "status": "offline"}
        
        bild_bytes = await bild.read()
        resultat = fråga_qwen_vllm(bild_bytes, mode=mode)
        
        return {"mode": mode, "resultat": resultat}
    
    
    @app.get("/debug/skanning/{skanning_id}")
    async def debug_skanning(skanning_id: str):
        """Se detaljer om en skanning."""
        skanning_dir = f"/tmp/skanning_{skanning_id}"
        
        if not os.path.exists(skanning_dir):
            # Prova hitta i gång_index
            gång_index_fil = "/tmp/gång_index.json"
            if os.path.exists(gång_index_fil):
                with open(gång_index_fil) as f:
                    gång_index = json.load(f)
                for gång, path in gång_index.items():
                    if skanning_id in path:
                        skanning_dir = path
                        break
        
        if not os.path.exists(skanning_dir):
            raise HTTPException(status_code=404, detail="Skanning finns inte")
        
        # Räkna frames
        frames = [f for f in os.listdir(skanning_dir) if f.startswith("frame_")]
        
        # Ladda positioner
        pos_fil = f"{skanning_dir}/positioner.json"
        positioner = []
        if os.path.exists(pos_fil):
            with open(pos_fil) as f:
                positioner = json.load(f)
        
        return {
            "skanning_dir": skanning_dir,
            "antal_frames": len(frames),
            "antal_positioner": len(positioner),
            "frames": frames[:20],  # Max 20 visas
        }
    
    
    @app.get("/debug/cache")
    async def debug_cache():
        """Visa VPS-cache status."""
        try:
            from core.lokalisering import cache_status
            return cache_status()
        except ImportError:
            return {"error": "lokalisering.py saknar cache_status()"}
    
    
    @app.post("/debug/rensa-cache")
    async def debug_rensa_cache():
        """Rensa VPS-cachen."""
        try:
            from core.lokalisering import rensa_cache
            rensa_cache()
            return {"rensat": True}
        except ImportError:
            return {"error": "lokalisering.py saknar rensa_cache()"}
    
    
    # ─────────────────────────────────────────────
    # LISTA SKANNINGAR
    # ─────────────────────────────────────────────
    
    @app.get("/vps/skanningar")
    async def lista_skanningar():
        """Listar alla skanningar (även de utan karta)."""
        gång_index_fil = "/tmp/gång_index.json"
        if not os.path.exists(gång_index_fil):
            return {"skanningar": []}
        
        with open(gång_index_fil) as f:
            gång_index = json.load(f)
        
        skanningar = []
        for gång, skanning_dir in gång_index.items():
            säker_namn = gång.replace(" ", "_")
            karta_finns = os.path.exists(f"/tmp/kartor/{säker_namn}/faiss.index")
            
            # Räkna frames
            frames = 0
            if os.path.exists(skanning_dir):
                frames = len([f for f in os.listdir(skanning_dir) if f.startswith("frame_")])
            
            skanningar.append({
                "gång": gång,
                "skanning_dir": skanning_dir,
                "antal_frames": frames,
                "karta_byggd": karta_finns,
            })
        
        return {"skanningar": skanningar}
    
    
    print("✅ VPS och Debug endpoints registrerade")
    print("   📍 /vps/admin    — Admin-gränssnitt")
    print("   📊 /vps/status   — Karta-status")
    print("   🗑️  /vps/karta/{gång} DELETE — Radera karta")
    print("   🔄 /vps/merge/{gång} POST — Slå ihop skanningar")
    print("   📈 /vps/tackning/{gång} — Täckningsanalys")
    print("   🔍 /debug/qwen   — Testa Qwen")
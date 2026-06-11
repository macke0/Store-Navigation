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
import time
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional


# ─── Live-lokalisering (i RAM, per gång) ─────────────────────
# Senaste rapporterade kameraposition från en testande klient (telefon/web).
# 3D-vyn pollar detta för att rita en blå "min position"-dot live.
_senaste_lokalisering: dict = {}


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
    
    
    @app.get("/vps/karta/{gang_namn}")
    async def vps_karta_detaljer(gang_namn: str):
        """Returnerar detaljer för en specifik karta."""
        säker_namn = gang_namn.replace(" ", "_").replace("/", "_")
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
            "gång": gang_namn,
            "metadata": meta,
            "antal_positioner": len(positioner),
        }
    
    
    @app.delete("/vps/karta/{gang_namn}")
    async def vps_radera_karta(gang_namn: str):
        """Raderar en VPS-karta."""
        from core.feature_karta import radera_karta
        
        # Normalisera namnet
        gang_namn = gang_namn.replace("_", " ")
        
        if radera_karta(gang_namn):
            return {"raderad": True, "gång": gang_namn}
        else:
            raise HTTPException(status_code=404, detail="Karta finns inte")
    
    
    @app.post("/vps/rebuild/{gang_namn}")
    async def vps_bygg_om_karta(gang_namn: str):
        """Bygger om en karta från befintlig skanning."""
        from core.feature_karta import bygg_karta, radera_karta
        
        # Normalisera namnet
        gang_namn = gang_namn.replace("_", " ")
        
        # Hitta skanning
        gång_index_fil = "/tmp/gång_index.json"
        if not os.path.exists(gång_index_fil):
            raise HTTPException(status_code=404, detail="Ingen skanning finns")
        
        with open(gång_index_fil) as f:
            gång_index = json.load(f)
        
        skanning_dir = gång_index.get(gang_namn)
        if not skanning_dir:
            raise HTTPException(status_code=404, detail=f"Skanning för {gang_namn} finns inte")
        
        pos_fil = f"{skanning_dir}/positioner.json"
        if not os.path.exists(pos_fil):
            raise HTTPException(status_code=404, detail="Positionsfil saknas")
        
        with open(pos_fil) as f:
            positioner = json.load(f)
        
        # Radera gammal karta
        radera_karta(gang_namn)
        
        # Bygg om
        resultat = bygg_karta(skanning_dir, positioner, gang_namn)
        
        if resultat:
            return {"ombyggd": True, "gång": gang_namn, "karta_dir": resultat}
        else:
            raise HTTPException(status_code=500, detail="Kunde inte bygga karta")
    
    
    # ─────────────────────────────────────────────
    # MERGE SKANNINGAR
    # ─────────────────────────────────────────────
    
    @app.post("/vps/merge/{gang_namn}")
    async def vps_merge_skanning(gang_namn: str, skanning_id: Optional[str] = None):
        """
        Slår ihop en ny skanning med befintlig karta.
        Om skanning_id inte anges, används den senaste skanningen för gången.
        """
        from core.feature_karta import slå_ihop_skanningar
        
        # Normalisera namnet
        gang_namn = gang_namn.replace("_", " ")
        
        # Hitta skanning
        gång_index_fil = "/tmp/gång_index.json"
        if not os.path.exists(gång_index_fil):
            raise HTTPException(status_code=404, detail="Ingen skanning finns")
        
        with open(gång_index_fil) as f:
            gång_index = json.load(f)
        
        skanning_dir = gång_index.get(gang_namn)
        if not skanning_dir:
            raise HTTPException(status_code=404, detail=f"Skanning för {gang_namn} finns inte")
        
        pos_fil = f"{skanning_dir}/positioner.json"
        if not os.path.exists(pos_fil):
            raise HTTPException(status_code=404, detail="Positionsfil saknas")
        
        with open(pos_fil) as f:
            positioner = json.load(f)
        
        # Merge
        resultat = slå_ihop_skanningar(gang_namn, skanning_dir, positioner)
        
        return resultat
    
    
    @app.get("/vps/tackning/{gang_namn}")
    async def vps_täckning(gang_namn: str):
        """Analyserar täckningen för en karta."""
        from core.feature_karta import beräkna_täckning, detektera_loopar, hitta_luckor
        
        # Normalisera namnet
        gang_namn = gang_namn.replace("_", " ")
        säker_namn = gang_namn.replace(" ", "_")
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
            "gång": gang_namn,
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
    
    @app.post("/produkter/extrahera/")
    async def extrahera_produkter_endpoint(
        bild: UploadFile = File(...),
        gång: str = Form(...),
        frame_lidar: str = Form("[]"),   # JSON-array av {u,v,x,y,z}
    ):
        from core.produkt_extraktion import extrahera_produkter_frame, spara_produkter
        bytes_ = await bild.read()
        lidar = json.loads(frame_lidar)
        nya = extrahera_produkter_frame(bytes_, lidar, gång)
        info = spara_produkter(gång, nya)
        return {"hittad": len(nya) > 0, "produkter": nya, **info}


    @app.get("/vps/karta/{gang_namn}/produkter")
    async def lista_produkter(gang_namn: str):
        from core.produkt_extraktion import läs_produkter
        return {"produkter": läs_produkter(gang_namn)}


    # ─────────────────────────────────────────────
    # LÄGE 2 — PRODUKTSKANNING (A1 per frame)
    # ─────────────────────────────────────────────
    #
    # iOS-flödet (ProduktSkanningView):
    #   1. Lokalisera mot kartan via /debug/lokalisera → (x_karta, yaw_karta)
    #   2. Räkna ut T_arkit→karta lokalt och håll konstant under skanningen
    #   3. Var 0.5s: ta frame, samla LiDAR-punkter (ARKit-world),
    #      skicka bild + transform + intrinsics + image_dims +
    #      T_arkit→karta + frame_punkter → här
    #
    # Backend kör A1 (Qwen-bbox + projektion av LiDAR-punkter), back-projekterar
    # bbox-centrum till ARKit-world och multiplicerar med T_arkit→karta så att
    # produkter sparas i kartans frame.

    @app.post("/produkter/skanna_frame/")
    async def skanna_frame_endpoint(
        bild: UploadFile = File(...),
        karta: str = Form(...),
        transform: str = Form(...),               # JSON-array, 16 floats column-major
        intrinsics: str = Form(...),              # JSON {fx,fy,cx,cy} portrait
        image_dims: str = Form(...),              # JSON {image_width, image_height}
        frame_punkter: str = Form("[]"),          # JSON-array [{x,y,z}, ...] ARKit-world
        T_arkit_till_karta: str = Form("null"),   # JSON-array 16 floats eller "null"
        frame_id: int = Form(0),
    ):
        from core.produkt_skanning import extrahera_produkter_a1, append_produkter

        try:
            bytes_ = await bild.read()
            t = json.loads(transform)
            intr = json.loads(intrinsics)
            dims = json.loads(image_dims)
            punkter = json.loads(frame_punkter)
            t_ak_raw = json.loads(T_arkit_till_karta)
            t_ak = t_ak_raw if isinstance(t_ak_raw, list) and len(t_ak_raw) == 16 else None
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"Ogiltig JSON: {e}")

        nya = extrahera_produkter_a1(
            bild_bytes=bytes_,
            frame_punkter=punkter,
            transform=t,
            intrinsics=intr,
            image_dims=dims,
            T_arkit_till_karta=t_ak,
            frame_id=int(frame_id),
        )
        info = append_produkter(karta, nya)

        # Uppdatera live-position så 3D-viewerns Live-prick följer kameran
        # under hela skanningen (inte bara vid lokalisering).
        if t_ak is not None and isinstance(t, list) and len(t) == 16:
            try:
                import numpy as _np
                T_ak_mat = _np.array(t_ak, dtype=_np.float64).reshape(4, 4).T
                T_arkit_cam = _np.array(t, dtype=_np.float64).reshape(4, 4).T
                cam_arkit = T_arkit_cam[:3, 3]
                cam_karta_h = T_ak_mat @ _np.array([cam_arkit[0], cam_arkit[1], cam_arkit[2], 1.0])
                # Yaw från ARKit-kamerans Z-axel transformerad genom T_ak
                arkit_z = T_arkit_cam[:3, 2]
                karta_z = T_ak_mat[:3, :3] @ arkit_z
                yaw = float(_np.arctan2(-karta_z[0], -karta_z[2]))
                _senaste_lokalisering[karta] = {
                    "x": float(cam_karta_h[0]),
                    "y": float(cam_karta_h[1]),
                    "z": float(cam_karta_h[2]),
                    "yaw": yaw,
                    "konfidens": "skanning",
                    "t": time.time(),
                }
            except Exception:
                pass

        return {
            "hittad": len(nya) > 0,
            "produkter": nya,
            "antal_nya": len(nya),
            "totalt": info.get("totalt", 0),
        }


    @app.post("/produkter/live_pos/")
    async def live_pos_endpoint(
        karta: str = Form(...),
        transform: str = Form(...),               # JSON-array, 16 floats column-major
        T_arkit_till_karta: str = Form(...),      # JSON-array, 16 floats column-major
    ):
        """
        Lättviktig live-positionsuppdatering. Tar bara ARKit-kameratransform +
        T_arkit→karta, räknar ut kartpositionen och lagrar den i
        _senaste_lokalisering. Ingen bild, LiDAR eller Qwen → kan kallas ofta
        (flera Hz) så 3D-viewerns Live-prick följer kameran mjukt under skanning.
        """
        try:
            t = json.loads(transform)
            t_ak = json.loads(T_arkit_till_karta)
            if not (isinstance(t, list) and len(t) == 16
                    and isinstance(t_ak, list) and len(t_ak) == 16):
                raise HTTPException(status_code=400, detail="transform/T_ak måste vara 16 floats")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"Ogiltig JSON: {e}")

        import numpy as _np
        T_ak_mat = _np.array(t_ak, dtype=_np.float64).reshape(4, 4).T
        T_arkit_cam = _np.array(t, dtype=_np.float64).reshape(4, 4).T
        cam_arkit = T_arkit_cam[:3, 3]
        cam_karta_h = T_ak_mat @ _np.array([cam_arkit[0], cam_arkit[1], cam_arkit[2], 1.0])
        arkit_z = T_arkit_cam[:3, 2]
        karta_z = T_ak_mat[:3, :3] @ arkit_z
        yaw = float(_np.arctan2(-karta_z[0], -karta_z[2]))
        _senaste_lokalisering[karta] = {
            "x": float(cam_karta_h[0]),
            "y": float(cam_karta_h[1]),
            "z": float(cam_karta_h[2]),
            "yaw": yaw,
            "konfidens": "live",
            "t": time.time(),
        }
        return {"x": float(cam_karta_h[0]), "y": float(cam_karta_h[1]),
                "z": float(cam_karta_h[2]), "yaw": yaw}


    @app.get("/produkter/lista/{karta}")
    async def lista_skannade_produkter(karta: str):
        """Listar alla produkter som skannats in via Läge 2."""
        from core.produkt_skanning import läs_produkter
        return {"karta": karta, "produkter": läs_produkter(karta)}


    @app.post("/produkter/konsolidera/{karta}")
    async def konsolidera_produkter_endpoint(
        karta: str,
        avstånd: float = 1.5,
    ):
        """
        Slår ihop rådata-observationer i identifierade_produkter.json till en
        konsoliderad lista (en rad per fysisk produkt-instans) i
        produkter_konsoliderade.json. Kör efter en skanningssession.

        Query-param:
          avstånd (float, default 1.5): meter inom vilka samma produkt-id
                                       räknas som samma fysiska instans.
        """
        from core.produkt_skanning import konsolidera_produkter
        info = konsolidera_produkter(karta, distance_threshold=avstånd)
        return {"karta": karta, **info}


    @app.get("/produkter/konsoliderade/{karta}")
    async def lista_konsoliderade_produkter(karta: str):
        """Listar konsoliderade produkter (en rad per fysisk instans)."""
        from core.produkt_skanning import läs_konsoliderade
        return {"karta": karta, "produkter": läs_konsoliderade(karta)}


    # ─────────────────────────────────────────────
    # NAVIGATION — Steg 2: Occupancy grid + A*
    # ─────────────────────────────────────────────

    @app.post("/navigation/grid/{karta}")
    async def bygg_grid_endpoint(
        karta: str,
        cell_storlek: float = 0.10,
        höjd_min: float = 0.30,
        höjd_max: float = 2.00,
        dilation: float = 0.35,
        marginal: float = 1.0,
    ):
        """
        Bygg/uppdatera occupancy_grid.npy för kartan från all_points_3d.npy.
        Query-params styr cell-storlek, höjdfilter över golvet och
        obstacle-dilation (= person-radius + safety).
        """
        from core.navigation import bygg_occupancy_grid
        return bygg_occupancy_grid(
            karta_namn=karta,
            cell_storlek=cell_storlek,
            höjd_över_golv_min=höjd_min,
            höjd_över_golv_max=höjd_max,
            dilation_meter=dilation,
            marginal=marginal,
        )


    @app.get("/navigation/grid_meta/{karta}")
    async def grid_meta_endpoint(karta: str):
        """Returnerar occupancy_meta.json (grid-bounds, cell-storlek, m.m.)."""
        from core.navigation import läs_grid_meta
        meta = läs_grid_meta(karta)
        if meta is None:
            raise HTTPException(
                status_code=404,
                detail="occupancy_grid saknas — POST /navigation/grid/{karta} först",
            )
        return meta


    @app.post("/navigation/väg")
    async def navigation_väg_endpoint(payload: dict):
        """
        A*-pathfinding i kartans koordinatsystem.

        Body (JSON):
          {
            "karta": str,
            "start": [x, z],
            "mål":   [x, z]   (eller "mal" om JSON-klienten klagar på å)
          }

        Returnerar:
          { ok, waypoints: [[x,z], ...], längd_meter, antal_waypoints, ... }
        """
        from core.navigation import astar_väg

        karta = payload.get("karta")
        if not karta:
            raise HTTPException(status_code=400, detail="karta saknas")

        start = payload.get("start")
        mål = payload.get("mål") or payload.get("mal") or payload.get("mål_xz")
        if not (isinstance(start, list) and len(start) == 2):
            raise HTTPException(status_code=400, detail="start måste vara [x, z]")
        if not (isinstance(mål, list) and len(mål) == 2):
            raise HTTPException(status_code=400, detail="mål måste vara [x, z]")

        try:
            start_xz = (float(start[0]), float(start[1]))
            mål_xz = (float(mål[0]), float(mål[1]))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Ogiltiga koordinater")

        return astar_väg(start_xz, mål_xz, karta)


    @app.post("/kund/hitta-produkt")
    async def kund_hitta_produkt(payload: dict):
        """
        Kund-flöde: hitta en produkt i kartan och beräkna väg dit.

        Body (JSON):
          {
            "karta": str,
            "produkt_id": str,            # valfri
            "produktnamn": str,           # valfri (används om produkt_id saknas)
            "nuvarande_position": [x, z]  # kundens nuvarande kartposition
          }
        Minst en av produkt_id / produktnamn krävs.

        Returnerar:
          { hittad, produkt: {...}, väg_ok, waypoints, längd_meter, antal_waypoints }
        """
        from core.navigation import astar_väg, läs_grid
        from core.produkt_skanning import läs_konsoliderade
        from core.produkt_sok import get_produkt_sök

        karta = payload.get("karta")
        if not karta:
            raise HTTPException(status_code=400, detail="karta saknas")

        produkt_id = payload.get("produkt_id")
        produktnamn = payload.get("produktnamn")
        if not produkt_id and not produktnamn:
            raise HTTPException(
                status_code=400,
                detail="minst en av produkt_id / produktnamn krävs",
            )

        pos = payload.get("nuvarande_position")
        if not (isinstance(pos, list) and len(pos) == 2):
            raise HTTPException(
                status_code=400, detail="nuvarande_position måste vara [x, z]"
            )
        try:
            start_xz = (float(pos[0]), float(pos[1]))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Ogiltig nuvarande_position")

        produkter = läs_konsoliderade(karta)

        # Hitta målprodukten i kartan
        produkt = None
        if produkt_id:
            produkt = next((p for p in produkter if p.get("id") == produkt_id), None)
        else:
            namn_l = produktnamn.lower()
            produkt = next(
                (p for p in produkter
                 if namn_l in str(p.get("visningsnamn", "")).lower()),
                None,
            )
            # Fallback: katalogsök → matcha id mot konsoliderade
            if produkt is None:
                träffar = get_produkt_sök().sök(produktnamn, 1)
                if träffar:
                    katalog_id = träffar[0].get("id")
                    produkt = next(
                        (p for p in produkter if p.get("id") == katalog_id), None
                    )

        if produkt is None:
            return {"hittad": False, "fel": "Produkt ej hittad i kartan"}

        produkt_ut = {
            "id": produkt.get("id"),
            "visningsnamn": produkt.get("visningsnamn"),
            "varumarke": produkt.get("varumarke"),
            "kategori": produkt.get("kategori"),
            "bild_url": produkt.get("bild_url"),
            "x": produkt.get("x"),
            "z": produkt.get("z"),
        }

        # Vägberäkning — kräver byggd occupancy_grid
        if läs_grid(karta) is None:
            return {
                "hittad": True,
                "produkt": produkt_ut,
                "väg_ok": False,
                "fel": f"occupancy_grid saknas — kör POST /navigation/grid/{karta}",
            }

        mål_xz = (float(produkt["x"]), float(produkt["z"]))
        väg = astar_väg(start_xz, mål_xz, karta)

        return {
            "hittad": True,
            "produkt": produkt_ut,
            "väg_ok": bool(väg.get("ok")),
            "waypoints": väg.get("waypoints", []),
            "längd_meter": väg.get("längd_meter"),
            "antal_waypoints": väg.get("antal_waypoints"),
            "fel": väg.get("fel"),
        }


    @app.post("/produkter/lokalisera_för_skanning/")
    async def lokalisera_för_skanning(
        bild: UploadFile = File(...),
        karta: str = Form(...),
        arkit_transform: str = Form(...),   # JSON 16-floats column-major (ARKit world_from_camera)
    ):
        """
        Kör VPS-lokalisering OCH returnerar T_arkit→karta så iOS slipper räkna
        rotationsmatte själv. iOS kan sedan skicka samma transform med varje
        produktskanningsframe.

        Returns:
          { hittad, pose, T_arkit_till_karta: [16], konfidens, inliers, ... }
        """
        import numpy as _np
        from core.vps_3d import lokalisera as _lokalisera

        try:
            t_arkit_flat = json.loads(arkit_transform)
            if not (isinstance(t_arkit_flat, list) and len(t_arkit_flat) == 16):
                raise ValueError("arkit_transform måste vara 16 floats")
        except (json.JSONDecodeError, ValueError) as e:
            raise HTTPException(status_code=400, detail=f"Ogiltig arkit_transform: {e}")

        bytes_ = await bild.read()
        resultat = _lokalisera(bytes_, gång=karta)

        if not resultat.get("hittad"):
            return {"hittad": False, **resultat}

        # Bygg T_karta_camera (4x4) direkt från råa rotationsmatrisen.
        # Tidigare rekonstruerades R från Euler-vinklar med Rz för yaw, vilket
        # antar Z-up world. Men ARKit/karta är Y-up → fel rotationsaxel →
        # transformerade koordinater fick både rotation och felaktig skala.
        x = float(resultat["x"]); y = float(resultat["y"]); z = float(resultat["z"])
        R_kc_raw = resultat.get("R_world_from_camera")
        if R_kc_raw is None:
            raise HTTPException(status_code=500,
                detail="lokalisera() returnerade ingen R_world_from_camera")
        R_kc = _np.array(R_kc_raw, dtype=_np.float64)

        # R_world_from_camera kommer från cv2.solvePnP → OpenCV-kamerabas
        # (+X höger, +Y NED, +Z FRAMÅT). iOS T_arkit_camera är i ARKit-bas
        # (+X höger, +Y UPP, +Z BAKÅT). Baserna skiljer sig med diag(1,-1,-1)
        # (flip Y och Z). Utan denna konvertering får T_ak ett 180°-fel runt
        # X-axeln: position stämmer (translation oberoende av kamerabas) men
        # all rörelse och kompass-riktning blir speglad. Konvertera CV→ARKit:
        #   R_world←ARKitCam = R_world←CVCam @ diag(1,-1,-1)
        cv_till_arkit = _np.diag([1.0, -1.0, -1.0])
        R_kc = R_kc @ cv_till_arkit

        T_karta_camera = _np.eye(4)
        T_karta_camera[:3, :3] = R_kc
        T_karta_camera[:3, 3] = [x, y, z]

        # ARKit-transform (column-major flat → 4x4 row-major numpy)
        T_arkit_camera = _np.array(t_arkit_flat, dtype=_np.float64).reshape(4, 4).T

        try:
            T_arkit_till_karta = T_karta_camera @ _np.linalg.inv(T_arkit_camera)
        except _np.linalg.LinAlgError:
            raise HTTPException(status_code=400, detail="Singulär ARKit-transform")

        # Returnera column-major flat (samma format som iOS använder)
        flat = T_arkit_till_karta.T.reshape(-1).tolist()

        # Spara även som live-position så 3D-viewerns Live-knapp kan visa
        # var iOS just lokaliserade sig (för felsökning av PnP-pose).
        _senaste_lokalisering[karta] = {
            "x": x, "y": y, "z": z,
            "yaw": float(resultat.get("yaw", 0)),
            "konfidens": resultat.get("konfidens", "okänd"),
            "t": time.time(),
        }

        return {
            "hittad": True,
            "pose": {
                "x": x, "y": y, "z": z,
                "roll": float(resultat.get("roll", 0)),
                "pitch": float(resultat.get("pitch", 0)),
                "yaw": float(resultat.get("yaw", 0)),
            },
            "konfidens": resultat.get("konfidens", "okänd"),
            "inliers": resultat.get("inliers", 0),
            "T_arkit_till_karta": flat,
            "metod": resultat.get("metod", ""),
        }


    # ─────────────────────────────────────────────
    # LIVE-LOKALISERING (för 3D-viewerns "min position"-dot)
    # ─────────────────────────────────────────────

    @app.post("/vps/lokalisering/senaste")
    async def rapportera_lokalisering(payload: dict):
        """
        Klient (iOS-app eller web) rapporterar sin lokaliserade position.
        Body: {gång, x, y, z, yaw, konfidens?}
        Lagras i RAM, läses av 3D-viewern.
        """
        gång = payload.get("gång")
        if not gång:
            return JSONResponse(status_code=400, content={"error": "gång saknas"})
        _senaste_lokalisering[gång] = {
            "x": float(payload.get("x", 0)),
            "y": float(payload.get("y", 1.5)),
            "z": float(payload.get("z", 0)),
            "yaw": float(payload.get("yaw", 0)),
            "konfidens": payload.get("konfidens", "okänd"),
            "t": time.time(),
        }
        return {"ok": True, "gång": gång}


    @app.get("/vps/karta/{gang_namn}/lokalisering-senaste")
    async def hämta_senaste_lokalisering(gang_namn: str):
        """
        3D-viewern pollar denna varje sekund.
        Returnerar 404 om ingen position eller om den är äldre än 8 sek.
        """
        info = _senaste_lokalisering.get(gang_namn)
        if not info:
            return JSONResponse(status_code=404, content={"error": "ingen position"})
        if time.time() - info["t"] > 8.0:
            return JSONResponse(status_code=404, content={"error": "för gammal"})
        return info


    print("✅ VPS och Debug endpoints registrerade")
    print("   📍 /vps/admin    — Admin-gränssnitt")
    print("   📊 /vps/status   — Karta-status")
    print("   🗑️  /vps/karta/{gång} DELETE — Radera karta")
    print("   🔄 /vps/merge/{gång} POST — Slå ihop skanningar")
    print("   📈 /vps/tackning/{gång} — Täckningsanalys")
    print("   🔍 /debug/qwen   — Testa Qwen")
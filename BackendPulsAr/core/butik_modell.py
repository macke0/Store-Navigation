"""
butik_modell.py — Global butiksmodell för Puls-AR
───────────────────────────────────────────────────
En butik = en global karta byggd av alla skanningar.

Principer:
  - Varje skanning är en "session" som läggs till modellen
  - COLMAP körs på ALLA sessioner tillsammans → global precision
  - Re-scan: nya frames i samma område ersätter automatiskt
  - Pause/resume: varje session har eget ID, kan fortsättas
  
Struktur på disk:
  /tmp/butik_modell/
  ├── sessioner/
  │   ├── session_1713000000/
  │   │   ├── frames/          (frame_0.jpg, frame_1.jpg, ...)
  │   │   ├── positioner.json  (ARKit-positioner per frame)
  │   │   ├── punkter_3d.json  (LiDAR-punkter)
  │   │   └── metadata.json    (start/slut-tid, antal frames)
  │   ├── session_1713001200/
  │   │   └── ...
  │   └── ...
  ├── global_karta/
  │   ├── metadata.json
  │   ├── frame_descriptors.npy
  │   ├── frame_index.faiss
  │   └── ... (COLMAP-optimerade punkter)
  └── butik_metadata.json      (namn, senast uppdaterad, etc)
"""

import json
import os
import shutil
import time
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict
from dataclasses import dataclass, field


BUTIK_DIR = Path("/tmp/butik_modell")


@dataclass
class SkanningsSession:
    """En skanning-session."""
    session_id: str
    start_tid: float
    slut_tid: Optional[float] = None
    antal_frames: int = 0
    antal_punkter: int = 0
    status: str = "aktiv"  # aktiv, pausad, klar, bearbetar
    start_position: Optional[Dict] = None
    slut_position: Optional[Dict] = None
    
    @property
    def session_dir(self) -> Path:
        return BUTIK_DIR / "sessioner" / self.session_id
    
    @property
    def frames_dir(self) -> Path:
        return self.session_dir / "frames"
    
    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "start_tid": self.start_tid,
            "slut_tid": self.slut_tid,
            "antal_frames": self.antal_frames,
            "antal_punkter": self.antal_punkter,
            "status": self.status,
            "start_position": self.start_position,
            "slut_position": self.slut_position,
        }


class ButikModell:
    """
    Global butiksmodell som ackumulerar skanningar.
    
    Användning:
        modell = ButikModell.ladda_eller_skapa("ICA Maxi Bromma")
        session = modell.ny_session()
        modell.lägg_till_frames(session.session_id, frames, positioner, punkter)
        modell.avsluta_session(session.session_id)
        modell.bygg_global_karta()  # COLMAP på allt
    """
    
    def __init__(self, namn: str):
        self.namn = namn
        self.sessioner: Dict[str, SkanningsSession] = {}
        self.senast_byggd: Optional[float] = None
        self.global_karta_version: int = 0
        
        # Skapa mappar
        BUTIK_DIR.mkdir(parents=True, exist_ok=True)
        (BUTIK_DIR / "sessioner").mkdir(exist_ok=True)
        (BUTIK_DIR / "global_karta").mkdir(exist_ok=True)
    
    @classmethod
    def ladda_eller_skapa(cls, namn: str) -> 'ButikModell':
        """Ladda befintlig modell eller skapa ny."""
        meta_path = BUTIK_DIR / "butik_metadata.json"
        
        modell = cls(namn)
        
        if meta_path.exists():
            with open(meta_path) as f:
                meta = json.load(f)
            modell.namn = meta.get("namn", namn)
            modell.senast_byggd = meta.get("senast_byggd")
            modell.global_karta_version = meta.get("version", 0)
            
            # Ladda sessioner
            for sid, sdata in meta.get("sessioner", {}).items():
                modell.sessioner[sid] = SkanningsSession(
                    session_id=sid,
                    start_tid=sdata.get("start_tid", 0),
                    slut_tid=sdata.get("slut_tid"),
                    antal_frames=sdata.get("antal_frames", 0),
                    antal_punkter=sdata.get("antal_punkter", 0),
                    status=sdata.get("status", "klar"),
                    start_position=sdata.get("start_position"),
                    slut_position=sdata.get("slut_position"),
                )
            
            print(f"📦 Laddade butiksmodell: {namn} ({len(modell.sessioner)} sessioner)")
        else:
            modell._spara_metadata()
            print(f"🆕 Skapade ny butiksmodell: {namn}")
        
        return modell
    
    def _spara_metadata(self):
        """Spara metadata till disk."""
        meta = {
            "namn": self.namn,
            "senast_byggd": self.senast_byggd,
            "version": self.global_karta_version,
            "sessioner": {
                sid: s.to_dict() for sid, s in self.sessioner.items()
            }
        }
        with open(BUTIK_DIR / "butik_metadata.json", "w") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    
    # ─────────────────────────────────────────────
    # SESSION-HANTERING
    # ─────────────────────────────────────────────
    
    def ny_session(self) -> SkanningsSession:
        """Skapa en ny skanning-session."""
        session_id = f"session_{int(time.time())}"
        session = SkanningsSession(
            session_id=session_id,
            start_tid=time.time(),
            status="aktiv"
        )
        
        # Skapa mappar
        session.frames_dir.mkdir(parents=True, exist_ok=True)
        
        self.sessioner[session_id] = session
        self._spara_metadata()
        
        print(f"🎬 Ny session: {session_id}")
        return session
    
    def fortsätt_session(self, session_id: str) -> Optional[SkanningsSession]:
        """Fortsätt en pausad session."""
        session = self.sessioner.get(session_id)
        if session and session.status == "pausad":
            session.status = "aktiv"
            self._spara_metadata()
            print(f"▶️  Fortsätter session: {session_id} (har {session.antal_frames} frames)")
            return session
        return None
    
    def pausa_session(self, session_id: str):
        """Pausa en aktiv session."""
        session = self.sessioner.get(session_id)
        if session:
            session.status = "pausad"
            self._spara_metadata()
            print(f"⏸️  Pausade session: {session_id} ({session.antal_frames} frames)")
    
    def avsluta_session(self, session_id: str):
        """Markera session som klar."""
        session = self.sessioner.get(session_id)
        if session:
            session.status = "klar"
            session.slut_tid = time.time()
            self._spara_metadata()
            print(f"✅ Session klar: {session_id} ({session.antal_frames} frames, {session.antal_punkter} 3D-punkter)")
    
    # ─────────────────────────────────────────────
    # FRAME-HANTERING
    # ─────────────────────────────────────────────
    
    def lägg_till_batch(
        self,
        session_id: str,
        frames: List[tuple],  # [(filename, bytes), ...]
        positioner: List[dict],
        punkter_3d: List[dict],
        batch_index: int = 0,
    ):
        """
        Lägg till en batch av frames till en session.
        Kallas från batch-upload endpoint.
        """
        session = self.sessioner.get(session_id)
        if not session:
            print(f"⚠️ Session {session_id} finns inte")
            return
        
        # Spara frames
        for filename, data in frames:
            frame_path = session.frames_dir / filename
            with open(frame_path, "wb") as f:
                f.write(data)
        
        # Spara/uppdatera positioner
        pos_path = session.session_dir / "positioner.json"
        befintliga_pos = []
        if pos_path.exists():
            with open(pos_path) as f:
                befintliga_pos = json.load(f)
        befintliga_pos.extend(positioner)
        with open(pos_path, "w") as f:
            json.dump(befintliga_pos, f)
        
        # Spara/uppdatera 3D-punkter
        pkt_path = session.session_dir / "punkter_3d.json"
        befintliga_pkt = []
        if pkt_path.exists():
            with open(pkt_path) as f:
                befintliga_pkt = json.load(f)
        befintliga_pkt.extend(punkter_3d)
        with open(pkt_path, "w") as f:
            json.dump(befintliga_pkt, f)
        
        # Uppdatera session
        session.antal_frames = len(list(session.frames_dir.glob("*.jpg")))
        session.antal_punkter = len(befintliga_pkt)
        
        # Spara start/slut-position
        if positioner:
            if not session.start_position:
                session.start_position = {
                    "x": positioner[0].get("x", 0),
                    "z": positioner[0].get("z", 0)
                }
            session.slut_position = {
                "x": positioner[-1].get("x", 0),
                "z": positioner[-1].get("z", 0)
            }
        
        self._spara_metadata()
        print(f"   📥 Batch {batch_index}: +{len(frames)} frames, +{len(punkter_3d)} punkter")
    
    # ─────────────────────────────────────────────
    # GLOBAL KARTA
    # ─────────────────────────────────────────────
    
    def samla_alla_frames(self) -> tuple:
        """
        Samla alla frames, positioner och 3D-punkter från alla klara sessioner.
        Returnerar (frames_dir, alla_positioner, alla_punkter).
        """
        # Skapa temporär mapp med alla frames
        alla_frames_dir = BUTIK_DIR / "alla_frames"
        if alla_frames_dir.exists():
            shutil.rmtree(alla_frames_dir)
        alla_frames_dir.mkdir()
        
        alla_positioner = []
        alla_punkter = []
        frame_offset = 0
        
        for sid, session in sorted(self.sessioner.items()):
            if session.status not in ("klar", "pausad"):
                continue
            
            # Ladda positioner
            pos_path = session.session_dir / "positioner.json"
            if pos_path.exists():
                with open(pos_path) as f:
                    pos = json.load(f)
                
                # Justera frame-nummer med offset
                for p in pos:
                    p["frame"] = p.get("frame", 0) + frame_offset
                    p["session"] = sid
                alla_positioner.extend(pos)
            
            # Ladda 3D-punkter
            pkt_path = session.session_dir / "punkter_3d.json"
            if pkt_path.exists():
                with open(pkt_path) as f:
                    pkt = json.load(f)
                for p in pkt:
                    p["frame"] = p.get("frame", 0) + frame_offset
                alla_punkter.extend(pkt)
            
            # Kopiera frames med nytt index
            frame_files = sorted(session.frames_dir.glob("*.jpg"))
            for ff in frame_files:
                fid = int(ff.stem.replace("frame_", ""))
                ny_path = alla_frames_dir / f"frame_{fid + frame_offset}.jpg"
                shutil.copy2(ff, ny_path)
            
            # Beräkna offset från faktiskt högsta frame-ID
            if frame_files:
                max_fid = max(int(ff.stem.replace("frame_", "")) for ff in frame_files)
                frame_offset += max_fid + 10
            else:
                frame_offset += 10
        
        total_frames = len(list(alla_frames_dir.glob("*.jpg")))
        
        # Sampla om för många frames (SuperPoint tar lång tid)
        MAX_TOTAL_FRAMES = 2000
        if total_frames > MAX_TOTAL_FRAMES:
            import random
            alla_jpgs = sorted(alla_frames_dir.glob("*.jpg"))
            steg = max(1, len(alla_jpgs) // MAX_TOTAL_FRAMES)
            behåll = set(alla_jpgs[::steg][:MAX_TOTAL_FRAMES])
            # Behåll alltid första och sista (för loop closure)
            behåll.add(alla_jpgs[0])
            behåll.add(alla_jpgs[-1])
            borttagna = 0
            for f in alla_jpgs:
                if f not in behåll:
                    f.unlink()
                    borttagna += 1
            # Filtrera positioner och punkter
            behåll_ids = set()
            for f in behåll:
                behåll_ids.add(int(f.stem.replace("frame_", "")))
            alla_positioner = [p for p in alla_positioner if p.get("frame", 0) in behåll_ids]
            alla_punkter = [p for p in alla_punkter if p.get("frame", 0) in behåll_ids]
            print(f"   ⚡ Samplade {MAX_TOTAL_FRAMES}/{total_frames} frames (tog bort {borttagna})")
            total_frames = MAX_TOTAL_FRAMES
        
        print(f"📊 Samlade {total_frames} frames, {len(alla_positioner)} positioner, {len(alla_punkter)} 3D-punkter")
        
        return str(alla_frames_dir), alla_positioner, alla_punkter
    
    def bygg_global_karta(self) -> bool:
        from core.butik_endpoints import uppdatera_progress
        print(f"\n🗺️  Bygger global karta för {self.namn}...")
        uppdatera_progress("Samlar frames", 10)
        
        frames_dir, positioner, punkter_3d = self.samla_alla_frames()

        if not positioner:
            print("⚠️ Inga frames att bygga karta av")
            return False

        # Loop closure på alla positioner
        from core.loop_closure import korrigera_loop_closure
        positioner, lc_info = korrigera_loop_closure(positioner)
        if lc_info.get("korrigerad"):
            print(f"🔄 Loop closure: {lc_info['total_drift']:.2f}m drift korrigerad")
        else:
            print(f"⚠️ Ingen loop closure — start och slut för långt ifrån varandra")

        try:
            from core.vps_3d import bygg_3d_karta
            
            karta_path = bygg_3d_karta(
                skanning_dir=frames_dir,
                punkter_3d=punkter_3d,
                positioner=positioner,
                gång_namn="hela_butiken"
            )
            
            if karta_path:
                self.senast_byggd = time.time()
                self.global_karta_version += 1
                self._spara_metadata()
                print(f"✅ Global karta byggd (version {self.global_karta_version})")
                
                # Identifiera produkter
                uppdatera_progress("Identifierar produkter", 70)
                print(f"\n🔍 Startar produktidentifiering...")
                # Använd ALLA frames från sessioner (inte samplade)
                from core.produkt_pipeline import kör_pipeline
                alla_pos = []
                alla_pkt = []
                original_frames = BUTIK_DIR / "alla_original_frames"
                if original_frames.exists():
                    shutil.rmtree(original_frames)
                original_frames.mkdir()
                for sid, session in sorted(self.sessioner.items()):
                    if session.status not in ("klar", "pausad"):
                        continue
                    pp = session.session_dir / "positioner.json"
                    if pp.exists():
                        with open(pp) as f:
                            alla_pos.extend(json.load(f))
                    pk = session.session_dir / "punkter_3d.json"
                    if pk.exists():
                        with open(pk) as f:
                            alla_pkt.extend(json.load(f))
                    fd = session.frames_dir
                    if fd.exists():
                        for ff in fd.glob("*.jpg"):
                            shutil.copy2(ff, original_frames / ff.name)
                produkter = kör_pipeline(str(original_frames), alla_pos, alla_pkt)
                if original_frames.exists():
                    shutil.rmtree(original_frames)
                print(f"✅ {len(produkter)} produkter identifierade och sparade")
                
                # Rensa temporära filer
                alla_frames_dir = BUTIK_DIR / "alla_frames"
                if alla_frames_dir.exists():
                    shutil.rmtree(alla_frames_dir)
                    print(f"🧹 Rensade temporära filer")
                
                uppdatera_progress("Klar", 100)
                
                return True
            
        except Exception as e:
            uppdatera_progress(f"Fel: {e}", 0)
            print(f"❌ Kartbygge misslyckades: {e}")
            import traceback
            traceback.print_exc()
        
        return False
    
    def behöver_ombyggnad(self) -> bool:
        """Kolla om det finns nya sessioner som inte inkluderats i kartan."""
        if not self.senast_byggd:
            return len(self.sessioner) > 0
        
        for session in self.sessioner.values():
            if session.status == "klar" and session.slut_tid and session.slut_tid > self.senast_byggd:
                return True
        return False
    
    # ─────────────────────────────────────────────
    # RE-SCAN
    # ─────────────────────────────────────────────
    
    def hitta_överlappande_sessioner(self, ny_session: SkanningsSession) -> List[str]:
        """
        Hitta sessioner som överlappar geografiskt med en ny session.
        Används för att detektera re-scans.
        """
        if not ny_session.start_position or not ny_session.slut_position:
            return []
        
        ny_min_x = min(ny_session.start_position["x"], ny_session.slut_position["x"])
        ny_max_x = max(ny_session.start_position["x"], ny_session.slut_position["x"])
        ny_min_z = min(ny_session.start_position["z"], ny_session.slut_position["z"])
        ny_max_z = max(ny_session.start_position["z"], ny_session.slut_position["z"])
        
        överlapp_tröskel = 2.0  # meter
        överlappande = []
        
        for sid, session in self.sessioner.items():
            if sid == ny_session.session_id:
                continue
            if not session.start_position or not session.slut_position:
                continue
            
            s_min_x = min(session.start_position["x"], session.slut_position["x"])
            s_max_x = max(session.start_position["x"], session.slut_position["x"])
            s_min_z = min(session.start_position["z"], session.slut_position["z"])
            s_max_z = max(session.start_position["z"], session.slut_position["z"])
            
            # Kolla överlapp med marginal
            if (ny_min_x - överlapp_tröskel < s_max_x and
                ny_max_x + överlapp_tröskel > s_min_x and
                ny_min_z - överlapp_tröskel < s_max_z and
                ny_max_z + överlapp_tröskel > s_min_z):
                överlappande.append(sid)
        
        return överlappande
    
    def ersätt_överlappande(self, ny_session_id: str):
        """
        Om en ny session överlappar gamla, ta bort de gamla.
        COLMAP bygger om med ny + resterande data.
        """
        ny_session = self.sessioner.get(ny_session_id)
        if not ny_session:
            return
        
        överlappande = self.hitta_överlappande_sessioner(ny_session)
        
        for sid in överlappande:
            print(f"🔄 Ersätter gammal session {sid} (överlapp med {ny_session_id})")
            self.ta_bort_session(sid)
    
    def ta_bort_session(self, session_id: str):
        """Ta bort en session och dess data."""
        session = self.sessioner.pop(session_id, None)
        if session and session.session_dir.exists():
            shutil.rmtree(session.session_dir)
        self._spara_metadata()
    
    # ─────────────────────────────────────────────
    # STATUS
    # ─────────────────────────────────────────────
    
    def status(self) -> dict:
        """Returnera status för butiksmodellen."""
        totalt_frames = sum(s.antal_frames for s in self.sessioner.values())
        totalt_punkter = sum(s.antal_punkter for s in self.sessioner.values())
        
        return {
            "namn": self.namn,
            "antal_sessioner": len(self.sessioner),
            "totalt_frames": totalt_frames,
            "totalt_3d_punkter": totalt_punkter,
            "senast_byggd": self.senast_byggd,
            "karta_version": self.global_karta_version,
            "behöver_ombyggnad": self.behöver_ombyggnad(),
            "sessioner": [s.to_dict() for s in self.sessioner.values()]
        }


# ─────────────────────────────────────────────
# SINGLETON
# ─────────────────────────────────────────────

_butik: Optional[ButikModell] = None

def get_butik() -> ButikModell:
    """Hämta eller skapa butiksmodellen."""
    global _butik
    if _butik is None:
        _butik = ButikModell.ladda_eller_skapa("ICA Maxi Bromma")
    return _butik
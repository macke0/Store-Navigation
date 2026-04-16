"""
produkt_pipeline.py — Produktidentifiering efter kartbygge
──────────────────────────────────────────────────────────
Körs efter att COLMAP byggt kartan. Identifierar produkter
i varje frame och beräknar deras 3D-position.

Pipeline:
  1. Ladda alla frames + kamerapositioner
  2. Kör Qwen (OpenRouter) på varje frame → produktnamn
  3. Fuzzy-match mot ICA-katalogen → kanoniskt namn
  4. Beräkna produktens 3D-position från kamera + djup
  5. Majoritetsvoting → slutliga produkter
  6. Spara till identifierade_produkter.json
"""

import json
import math
import os
import time
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed


class ProduktPipeline:
    def __init__(self, frames_dir: str, positioner: List[dict], 
                 punkter_3d: List[dict], ica_produkter_path: str = "data/ica_produkter.json"):
        self.frames_dir = Path(frames_dir)
        self.positioner = {p.get("frame", i): p for i, p in enumerate(positioner)}
        self.punkter_3d = punkter_3d
        
        # Ladda ICA-katalog för fuzzy match
        with open(ica_produkter_path, 'r', encoding='utf-8') as f:
            self.ica_produkter = json.load(f)
        self.ica_namn = {p['id']: p for p in self.ica_produkter}
        
        # Bygg sökindex — bara produktnamn, inte kategori
        self.sök_index = []
        for p in self.ica_produkter:
            sökbar = p.get('namn', '').lower()
            self.sök_index.append((sökbar, p))
        
        # 3D-punkter per frame
        self.punkter_per_frame: Dict[int, List[dict]] = {}
        for p in punkter_3d:
            fid = p.get("frame", 0)
            if fid not in self.punkter_per_frame:
                self.punkter_per_frame[fid] = []
            self.punkter_per_frame[fid].append(p)
        
        print(f"📦 Pipeline: {len(list(self.frames_dir.glob('*.jpg')))} frames, "
              f"{len(self.ica_produkter)} ICA-produkter, "
              f"{len(punkter_3d)} 3D-punkter")
    
    # ─────────────────────────────────────────────
    # STEG 1: IDENTIFIERA PRODUKTER I FRAMES
    # ─────────────────────────────────────────────
    
    def identifiera_alla(self, max_workers: int = 1, 
                          varannan_frame: int = 10) -> List[dict]:
        """
        Kör Qwen på frames och identifiera produkter.
        
        varannan_frame: hoppa över frames för snabbhet (3 = var tredje frame)
        max_workers: parallella Qwen-anrop
        """
        frame_filer = sorted(self.frames_dir.glob("frame_*.jpg"))
        
        # Hoppa över frames för snabbhet
        valda_frames = frame_filer[::varannan_frame]
        print(f"🔍 Identifierar produkter i {len(valda_frames)}/{len(frame_filer)} frames...")
        
        alla_identifieringar = []
        
        # Kör i batches för att inte överbelasta OpenRouter
        batch_size = max_workers
        total = len(valda_frames)
        
        for batch_start in range(0, total, batch_size):
            batch = valda_frames[batch_start:batch_start + batch_size]
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {}
                for frame_path in batch:
                    fid = int(frame_path.stem.replace("frame_", ""))
                    futures[executor.submit(self._identifiera_frame, frame_path, fid)] = fid
                
                for future in as_completed(futures):
                    fid = futures[future]
                    try:
                        resultat = future.result()
                        if resultat:
                            alla_identifieringar.extend(resultat)
                            for r in resultat:
                                print(f"   [{fid:4d}] {r['visningsnamn']}")
                    except Exception as e:
                        print(f"   [{fid:4d}] ⚠️ Fel: {e}")
            
            # Progress
            done = min(batch_start + batch_size, total)
            print(f"   📊 {done}/{total} frames ({len(alla_identifieringar)} produkter hittade)")
            
            # Kort paus mellan batches
            if batch_start + batch_size < total:
                time.sleep(0.5)
        
        print(f"\n✅ Totalt {len(alla_identifieringar)} identifieringar från {len(valda_frames)} frames")
        return alla_identifieringar
    
    def _identifiera_frame(self, frame_path: Path, frame_id: int) -> List[dict]:
        """Identifiera alla produkter i en frame."""
        img = cv2.imread(str(frame_path))
        if img is None:
            return []
        
        # Kör Qwen hylla-mode (identifierar ALLA produkter)
        produktnamn = self._qwen_hylla(img)
        if not produktnamn:
            return []
        
        # Hämta kameraposition
        pos = self.positioner.get(frame_id, {})
        cam_x = float(pos.get("x", 0))
        cam_y = float(pos.get("y", 0))
        cam_z = float(pos.get("z", 0))
        rot_y = float(pos.get("rot_y", 0))
        
        # Mediandjup från LiDAR
        frame_punkter = self.punkter_per_frame.get(frame_id, [])
        if frame_punkter:
            giltiga = [p.get("z", 1.0) for p in frame_punkter if 0.3 < p.get("z", 0) < 5.0]
            djup = float(np.median(giltiga)) if giltiga else 1.5
        else:
            djup = 1.5
        
        # Säkerhetskoll
        if np.isnan(djup) or djup <= 0:
            djup = 1.5  # Default om ingen LiDAR
        
        produktnamn = list(dict.fromkeys(produktnamn))
        
        resultat = []
        for i, namn in enumerate(produktnamn):
            # Fuzzy match mot ICA-katalogen
            match = self._fuzzy_match(namn)
            if not match:
                continue
            
            # Beräkna produktens 3D-position
            # Produkten är framför kameran på avstånd = djup
            prod_x = cam_x + float(djup) * math.sin(rot_y)
            prod_z = cam_z + float(djup) * math.cos(rot_y)
            
            # Skippa om position är nan
            if math.isnan(prod_x) or math.isnan(prod_z):
                continue
            
            # Sprida produkter lite vertikalt (hyllhöjd)
            # Uppskatta baserat på position i bildlistan
            prod_y = 0.5 + (i / max(len(produktnamn), 1)) * 2.0
            
            resultat.append({
                "visningsnamn": match["kanoniskt_namn"],
                "varumarke": match.get("varumarke", ""),
                "kategori": match.get("kategori", ""),
                "id": match.get("id", ""),
                "bild_url": match.get("bild_url", ""),
                "x": prod_x,
                "y": prod_y,
                "z": prod_z,
                "frame": frame_id,
                "säkerhet": "medium" if match.get("score", 0) > 80 else "låg",
                "qwen_svar": namn,
                "match_score": match.get("score", 0),
            })
        
        return resultat
    
    # ─────────────────────────────────────────────
    # QWEN VIA OPENROUTER
    # ─────────────────────────────────────────────
    
    def _qwen_hylla(self, img: np.ndarray) -> List[str]:
        """Skicka bild till Qwen och få lista av produktnamn."""
        import base64
        import requests
        
        # Skala ned
        h, w = img.shape[:2]
        max_dim = 1920
        if max(h, w) > max_dim:
            skala = max_dim / max(h, w)
            img = cv2.resize(img, (int(w * skala), int(h * skala)),
                           interpolation=cv2.INTER_LANCZOS4)
        
        _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64 = base64.b64encode(buf).decode("utf-8")
        
        openrouter_key = os.environ.get("OPENROUTER_KEY", "")
        
        payload = {
            "model": "qwen/qwen2.5-vl-72b-instruct",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": (
                        "There are price tags on shelves in this image. "
                        "Read the PRODUCT NAME and BRAND from each tag. Ignore the price number. "
                        "Return format: Brand Productname Weight. One per line. "
                        "Example: Findus Lättmajonnäs 200g "
                        "If no tags visible: OKÄND"
                    )}
                ]
            }],
            "max_tokens": 300,
            "temperature": 0.0,
        }
        
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json"
        }
        
        try: 
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload, headers=headers, timeout=60
            )
            resp.raise_for_status()
            svar = resp.json()["choices"][0]["message"]["content"].strip()
            svar = svar.replace("*", "").replace("#", "").strip()
            if svar and "OKÄND" not in svar.upper():
                print(f"      🔤 Qwen raw: {svar[:80]}")
            
            if not svar or "OKÄND" in svar.upper():
                return []
            
            # Slå ihop rader till produktbeskrivningar
            # Qwen kan svara med namn på en rad, vikt/märke på nästa
            rader = [r.strip().lstrip("0123456789.-) ") for r in svar.split("\n") if r.strip()]
            rader = [r for r in rader if r and "OKÄND" not in r.upper()]
            
            if not rader:
                return []
            
            # Filtrera bort OKÄND
            rader = [r for r in rader if "OKÄND" not in r.upper()]
            if not rader:
                return []
            
            # Heuristik: om en rad bara är siffror/pris, slå ihop med föregående
            produkter = []
            current = ""
            for rad in rader:
                # Skippa priser, jmf-pris, "per kilogram" etc
                rad_lower = rad.lower()
                if any(skip in rad_lower for skip in ["per kilo", "per kg", "jmf", "dmf", "/förp", "/förd", "förp", "klubb", "the price", "the product", "the tag", "reads:", "visible", "image"]):
                    continue
                # Skippa rena prisrader (bara siffror och mellanslag)
                stripped = rad.replace(" ", "").replace(".", "").replace(",", "").replace(":", "").replace("-", "")
                if stripped.isdigit():
                    continue
                
                # Om raden ser ut som vikt+märke (200g, FINDUS) → slå ihop
                if current and (rad.endswith("g") or rad.endswith("l") or "," in rad):
                    current = current + " " + rad
                elif current:
                    produkter.append(current)
                    current = rad
                else:
                    current = rad
            
            if current:
                produkter.append(current)
            
            return produkter
            
        except Exception as e:
            print(f"   ⚠️ Qwen-fel: {e}")
            return []
    
    # ─────────────────────────────────────────────
    # FUZZY MATCH MOT ICA-KATALOG
    # ─────────────────────────────────────────────
    
    def _fuzzy_match(self, qwen_namn: str, min_score: int = 70) -> Optional[dict]:
        """Matcha Qwen-svar mot ICA-produkter."""
        from rapidfuzz import fuzz, process
        
        q = qwen_namn.lower().strip()
        
        # Exakt match först
        for sökbar, prod in self.sök_index:
            if q in sökbar:
                return {
                    "kanoniskt_namn": prod.get("namn", ""),
                    "varumarke": prod.get("varumarke", ""),
                    "kategori": prod.get("kategori", ""),
                    "id": prod.get("id", ""),
                    "bild_url": prod.get("bild_url", ""),
                    "score": 100,
                }
        
        # Fuzzy match — partial_ratio funkar bättre för förkortningar (LÄTTMAJO → Lättmajonnäs)
        sökbara = [s for s, _ in self.sök_index]
        match = process.extractOne(q, sökbara, scorer=fuzz.WRatio)
        
        if match and match[1] >= min_score:
            idx = sökbara.index(match[0])
            prod = self.sök_index[idx][1]
            return {
                "kanoniskt_namn": prod.get("namn", ""),
                "varumarke": prod.get("varumarke", ""),
                "kategori": prod.get("kategori", ""),
                "id": prod.get("id", ""),
                "bild_url": prod.get("bild_url", ""),
                "score": match[1],
            }
        
        return None
    
    # ─────────────────────────────────────────────
    # STEG 2: VOTING + SPARA
    # ─────────────────────────────────────────────
    
    def processa_och_spara(self, max_workers: int = 4, 
                            varannan_frame: int = 10) -> List[dict]:
        """
        Kör hela pipelinen:
          1. Identifiera produkter i alla frames
          2. Majoritetsvoting
          3. Spara resultat
        """
        # Steg 1: Identifiera
        identifieringar = self.identifiera_alla(
            max_workers=max_workers,
            varannan_frame=varannan_frame
        )
        
        if not identifieringar:
            print("⚠️ Inga produkter identifierade")
            return []
        
        # Steg 2: Voting
        from core.produkt_voting import get_voting
        voting = get_voting()
        produkter = voting.processa(identifieringar)
        
        # Steg 3: Koppla till ICA-katalogen (lägg till bild_url etc)
        for p in produkter:
            if p.get("id") and p["id"] in self.ica_namn:
                ica = self.ica_namn[p["id"]]
                p["bild_url"] = ica.get("bild_url", "")
                if not p.get("kategori"):
                    p["kategori"] = ica.get("kategori", "")
        
        print(f"\n🏪 Pipeline klar: {len(produkter)} unika produkter identifierade")
        return produkter


def kör_pipeline(frames_dir: str, positioner: List[dict], 
                  punkter_3d: List[dict]) -> List[dict]:
    """
    Enkel wrapper för att köra hela pipelinen.
    Kallas efter kartbygge.
    """
    pipeline = ProduktPipeline(
        frames_dir=frames_dir,
        positioner=positioner,
        punkter_3d=punkter_3d,
    )
    return pipeline.processa_och_spara()
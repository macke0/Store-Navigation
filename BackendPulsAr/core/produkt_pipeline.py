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
        """Identifiera alla produkter i en frame och projicera dem till world-koord.

        Strategi (väg A1):
          1. Qwen returnerar {namn, bbox} per produkt i framen.
          2. Vi projicerar frame-ens 3D-punkter till portrait-pixel via cameraTransform.
          3. För varje bbox: median-djup av träffande punkter → back-projektera
             bbox-center till world-koord. Då får varje produkt sin egen (x,y,z).
          4. Fallback (om bbox saknas eller inga punkter träffar): gamla median-djup
             framåt-från-kameran-metoden, så voting fortfarande får data.
        """
        img = cv2.imread(str(frame_path))
        if img is None:
            return []

        # Kör Qwen hylla-mode → lista av {namn, bbox-or-None}
        kandidater = self._qwen_hylla(img)
        if not kandidater:
            return []

        # Hämta kameraposition + intrinsics + transform
        pos = self.positioner.get(frame_id, {})
        cam_x = float(pos.get("x", 0))
        cam_y = float(pos.get("y", 0))
        cam_z = float(pos.get("z", 0))
        rot_y = float(pos.get("rot_y", 0))
        transform_arr = pos.get("transform")
        fx_P = float(pos.get("fx", 0) or 0)
        fy_P = float(pos.get("fy", 0) or 0)
        cx_P = float(pos.get("cx", 0) or 0)
        cy_P = float(pos.get("cy", 0) or 0)
        # iOS sparade image_width = imageH_L (höjden i landscape)
        H_L = float(pos.get("image_width", 0) or 0)

        # Median-djup som fallback (samma beteende som tidigare)
        frame_punkter = self.punkter_per_frame.get(frame_id, [])
        giltiga_z = [p.get("z", 1.0) for p in frame_punkter if 0.3 < p.get("z", 0) < 5.0]
        median_djup = float(np.median(giltiga_z)) if giltiga_z else 1.5
        if np.isnan(median_djup) or median_djup <= 0:
            median_djup = 1.5

        # Förbered projektion: world → portrait pixel
        kan_projicera = (
            isinstance(transform_arr, list)
            and len(transform_arr) == 16
            and fx_P > 0 and fy_P > 0 and H_L > 0
        )

        T = T_inv = None
        fx_L = fy_L = cx_L = cy_L = 0.0
        if kan_projicera:
            # ARKit sparar transform kolumn-major flat: [c0.x..c0.w, c1.x..c1.w, ...]
            # numpy reshape(4,4) tar row-major → vi måste transponera
            try:
                T = np.array(transform_arr, dtype=np.float64).reshape(4, 4).T
                T_inv = np.linalg.inv(T)
            except (ValueError, np.linalg.LinAlgError):
                kan_projicera = False
            # Återskapa landscape-intrinsics (invertering av iOS portrait-konvertering)
            #   iOS: fx_P=fy_L, fy_P=fx_L, cx_P=H_L-cy_L, cy_P=cx_L
            #   ⇒  fx_L=fy_P, fy_L=fx_P, cx_L=cy_P, cy_L=H_L-cx_P
            fx_L = fy_P
            fy_L = fx_P
            cx_L = cy_P
            cy_L = H_L - cx_P

        # Projicera alla frame-punkter en gång, behåll (u_P, v_P, zc)
        projicerade: List[tuple] = []
        if kan_projicera and frame_punkter:
            for p in frame_punkter:
                try:
                    X = float(p.get("x", 0))
                    Y = float(p.get("y", 0))
                    Z = float(p.get("z", 0))
                except (TypeError, ValueError):
                    continue
                cam = T_inv @ np.array([X, Y, Z, 1.0])
                zc = float(cam[2])
                if zc <= 0.1:
                    continue  # bakom kameran
                xc = float(cam[0]); yc = float(cam[1])
                u_L = fx_L * xc / zc + cx_L
                v_L = fy_L * yc / zc + cy_L
                u_P = H_L - v_L
                v_P = u_L
                projicerade.append((u_P, v_P, zc))

        # Dedupa kandidater på namn (behåll första bbox vi sett)
        seen: set = set()
        unika: List[dict] = []
        for k in kandidater:
            n = k.get("namn", "")
            if n and n not in seen:
                seen.add(n)
                unika.append(k)

        resultat: List[dict] = []
        for kand in unika:
            namn = kand["namn"]
            bbox = kand.get("bbox")

            match = self._fuzzy_match(namn)
            if not match:
                continue

            prod_x = prod_y = prod_z = None
            position_metod = "fallback_median"
            antal_träffar = 0

            # Försök bbox-baserad position
            if kan_projicera and isinstance(bbox, list) and len(bbox) == 4:
                x1, y1, x2, y2 = bbox
                if x2 > x1 and y2 > y1 and projicerade:
                    träffar = [
                        zc for (u_P, v_P, zc) in projicerade
                        if x1 <= u_P <= x2 and y1 <= v_P <= y2
                    ]
                    antal_träffar = len(träffar)
                    if antal_träffar >= 3:
                        djup = float(np.median(träffar))
                        if 0.2 < djup < 10.0 and not np.isnan(djup):
                            # Back-projektera bbox-center → world
                            u_P_c = (x1 + x2) / 2.0
                            v_P_c = (y1 + y2) / 2.0
                            # Invertera portrait-rotation: u_L = v_P, v_L = H_L - u_P
                            u_L_c = v_P_c
                            v_L_c = H_L - u_P_c
                            xc_c = (u_L_c - cx_L) * djup / fx_L
                            yc_c = (v_L_c - cy_L) * djup / fy_L
                            world = T @ np.array([xc_c, yc_c, djup, 1.0])
                            prod_x = float(world[0])
                            prod_y = float(world[1])
                            prod_z = float(world[2])
                            position_metod = f"bbox_{antal_träffar}p"

            # Fallback: gamla median-djup framåt-från-kameran
            if prod_x is None:
                prod_x = cam_x + median_djup * math.sin(rot_y)
                prod_z = cam_z + median_djup * math.cos(rot_y)
                prod_y = cam_y - 0.3  # uppskattad hyllhöjd

            if math.isnan(prod_x) or math.isnan(prod_z) or math.isnan(prod_y):
                continue

            # Säkerhetsbedömning
            score = match.get("score", 0)
            if position_metod.startswith("bbox") and score > 80:
                säkerhet = "hög"
            elif score > 80:
                säkerhet = "medium"
            else:
                säkerhet = "låg"

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
                "säkerhet": säkerhet,
                "qwen_svar": namn,
                "match_score": score,
                "position_metod": position_metod,
                "bbox": bbox,
            })

        return resultat
    
    # ─────────────────────────────────────────────
    # QWEN VIA OPENROUTER
    # ─────────────────────────────────────────────
    
    def _qwen_hylla(self, img: np.ndarray) -> List[dict]:
        """Skicka bild till Qwen, få lista av {namn, bbox} i originalbildens koord.
        bbox kan vara None om Qwen inte gav giltig bbox-JSON för raden."""
        import base64
        import requests

        # Skala ned (Qwen ser den skalade versionen, så bboxar kommer i den koord-rymden)
        h_orig, w_orig = img.shape[:2]
        max_dim = 1920
        if max(h_orig, w_orig) > max_dim:
            skala = max_dim / max(h_orig, w_orig)
            img_q = cv2.resize(img, (int(w_orig * skala), int(h_orig * skala)),
                               interpolation=cv2.INTER_LANCZOS4)
        else:
            skala = 1.0
            img_q = img
        h_q, w_q = img_q.shape[:2]

        _, buf = cv2.imencode(".jpg", img_q, [cv2.IMWRITE_JPEG_QUALITY, 80])
        b64 = base64.b64encode(buf).decode("utf-8")

        openrouter_key = os.environ.get("OPENROUTER_KEY", "")

        prompt_text = (
            f"There are price tags on shelves in this image (size: {w_q} x {h_q} pixels, top-left origin). "
            f"For EACH visible price tag/product, output ONE JSON object on its own line:\n"
            f'{{"namn": "Brand Productname Weight", "bbox": [x1, y1, x2, y2]}}\n'
            f"bbox is the pixel rectangle of the product/tag (top-left x1,y1 to bottom-right x2,y2) in this image. "
            f"Read the PRODUCT NAME and BRAND from the tag. IGNORE the price number, jmf-pris, 'per kg', etc. "
            f'Example: {{"namn": "Findus Lättmajonnäs 200g", "bbox": [120, 340, 410, 580]}}\n'
            f"One JSON object per line. No prose, no markdown fences. If no tags visible: OKÄND"
        )

        payload = {
            "model": "qwen/qwen2.5-vl-72b-instruct",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    {"type": "text", "text": prompt_text}
                ]
            }],
            "max_tokens": 600,
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
            # Rensa ev. markdown-fence
            svar = svar.replace("```json", "").replace("```", "").strip()

            if svar and "OKÄND" not in svar.upper():
                print(f"      🔤 Qwen raw: {svar[:120]}")

            if not svar or "OKÄND" in svar.upper():
                return []

            kandidater: List[dict] = []
            for rad in svar.split("\n"):
                rad = rad.strip().rstrip(",")
                if not rad or "OKÄND" in rad.upper():
                    continue

                namn: Optional[str] = None
                bbox_q: Optional[list] = None

                # Försök JSON-parse först
                try:
                    obj = json.loads(rad)
                    if isinstance(obj, dict):
                        namn = (obj.get("namn") or obj.get("name") or "").strip()
                        b = obj.get("bbox") or obj.get("box")
                        if isinstance(b, list) and len(b) == 4:
                            bbox_q = [float(v) for v in b]
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass

                # Fallback: behandla som ren namn-rad (gammalt format)
                if not namn:
                    rensad = rad.lstrip("0123456789.-) ").strip()
                    rensad = rensad.replace("*", "").replace("#", "").strip()
                    if not rensad or "OKÄND" in rensad.upper():
                        continue
                    rad_lower = rensad.lower()
                    if any(s in rad_lower for s in ["per kilo", "per kg", "jmf", "dmf",
                                                     "/förp", "/förd", "förp", "klubb",
                                                     "the price", "the product", "the tag",
                                                     "reads:", "visible", "image"]):
                        continue
                    stripped = rensad.replace(" ", "").replace(".", "").replace(",", "")\
                                     .replace(":", "").replace("-", "")
                    if stripped.isdigit():
                        continue
                    namn = rensad

                if not namn:
                    continue

                # Skala bbox tillbaka till originalbildens koord
                bbox_orig: Optional[list] = None
                if bbox_q is not None:
                    bbox_orig = [v / skala for v in bbox_q]
                    # Sortera så x1<x2, y1<y2
                    x1, y1, x2, y2 = bbox_orig
                    if x2 < x1: x1, x2 = x2, x1
                    if y2 < y1: y1, y2 = y2, y1
                    bbox_orig = [x1, y1, x2, y2]

                kandidater.append({"namn": namn, "bbox": bbox_orig})

            return kandidater

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
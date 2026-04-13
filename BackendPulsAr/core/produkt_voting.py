"""
produkt_voting.py — Majoritetsvoting för produktidentifiering
─────────────────────────────────────────────────────────────
Flera frames ser samma hyllposition → rösta på rätt produkt.
Plus manuell override för korrigeringar.

Används efter skanning:
  1. Alla frames processas → identifieringar med position
  2. Gruppera identifieringar nära varandra (samma hyllposition)  
  3. Rösta — produkten som flest frames ser vinner
  4. Manuella korrigeringar har högst prioritet
"""

import json
import math
from pathlib import Path
from collections import Counter
from typing import List, Dict, Optional

MANUELLA_PATH = Path("/tmp/butik_modell/manuella_korrigeringar.json")
PRODUKTER_PATH = Path("/tmp/butik_modell/identifierade_produkter.json")

# Avstånd i meter för att räknas som "samma position"
POSITION_TRÖSKEL = 0.5  


class ProduktVoting:
    def __init__(self):
        self.identifieringar: List[dict] = []
        self.slutprodukter: List[dict] = []
        self.manuella: Dict[str, dict] = {}
        
        self._ladda_manuella()
    
    def _ladda_manuella(self):
        """Ladda manuella korrigeringar."""
        if MANUELLA_PATH.exists():
            with open(MANUELLA_PATH) as f:
                self.manuella = json.load(f)
            print(f"📝 Laddade {len(self.manuella)} manuella korrigeringar")
    
    def _spara_manuella(self):
        """Spara manuella korrigeringar."""
        MANUELLA_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(MANUELLA_PATH, "w") as f:
            json.dump(self.manuella, f, ensure_ascii=False, indent=2)
    
    def _spara_produkter(self):
        """Spara slutliga produkter."""
        PRODUKTER_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(PRODUKTER_PATH, "w") as f:
            json.dump(self.slutprodukter, f, ensure_ascii=False, indent=2)
    
    # ─────────────────────────────────────────────
    # GRUPPERING
    # ─────────────────────────────────────────────
    
    @staticmethod
    def _avstånd(a: dict, b: dict) -> float:
        """Euklidiskt avstånd mellan två positioner."""
        dx = float(a.get("x", 0)) - float(b.get("x", 0))
        dz = float(a.get("z", 0)) - float(b.get("z", 0))
        return math.sqrt(dx * dx + dz * dz)
    
    def gruppera(self, identifieringar: List[dict]) -> List[List[dict]]:
        """
        Gruppera identifieringar som är nära varandra.
        Enkel greedy clustering — snabb och tillräcklig.
        """
        grupper: List[List[dict]] = []
        använda = set()
        
        for i, ident in enumerate(identifieringar):
            if i in använda:
                continue
            
            grupp = [ident]
            använda.add(i)
            
            for j, annan in enumerate(identifieringar):
                if j in använda:
                    continue
                if self._avstånd(ident, annan) < POSITION_TRÖSKEL:
                    grupp.append(annan)
                    använda.add(j)
            
            grupper.append(grupp)
        
        return grupper
    
    # ─────────────────────────────────────────────
    # VOTING
    # ─────────────────────────────────────────────
    
    def rösta(self, grupp: List[dict]) -> dict:
        """
        Rösta på rätt produkt för en grupp identifieringar.
        
        Vikter:
          - hög säkerhet: 3 röster
          - medium: 2 röster
          - låg: 1 röst
        """
        vikter = {"hög": 3, "medium": 2, "låg": 1}
        
        röster = Counter()
        detaljer = {}
        
        for ident in grupp:
            namn = ident.get("visningsnamn", "")
            if not namn:
                continue
            
            vikt = vikter.get(ident.get("säkerhet", "låg"), 1)
            röster[namn] += vikt
            
            # Spara bästa detalj per produkt
            if namn not in detaljer or vikt > vikter.get(detaljer[namn].get("säkerhet", "låg"), 1):
                detaljer[namn] = ident
        
        if not röster:
            return {}
        
        # Vinnare
        bästa_namn, poäng = röster.most_common(1)[0]
        resultat = dict(detaljer[bästa_namn])
        
        # Beräkna medelposition
        xs = [float(i.get("x", 0)) for i in grupp]
        zs = [float(i.get("z", 0)) for i in grupp]
        ys = [float(i.get("y", 0)) for i in grupp]
        
        resultat["x"] = sum(xs) / len(xs)
        resultat["y"] = sum(ys) / len(ys)
        resultat["z"] = sum(zs) / len(zs)
        resultat["röster"] = poäng
        resultat["totalt_sett"] = len(grupp)
        resultat["konfidens"] = poäng / sum(röster.values()) if röster else 0
        resultat["alla_kandidater"] = dict(röster)
        
        # Generera unikt ID baserat på position
        resultat["position_id"] = f"pos_{resultat['x']:.2f}_{resultat['z']:.2f}"
        
        return resultat
    
    # ─────────────────────────────────────────────
    # HUVUDFUNKTION
    # ─────────────────────────────────────────────
    
    def processa(self, identifieringar: List[dict]) -> List[dict]:
        """
        Kör hela pipeline:
          1. Gruppera nära identifieringar
          2. Rösta per grupp
          3. Applicera manuella korrigeringar
          4. Spara resultat
        """
        self.identifieringar = identifieringar
        
        if not identifieringar:
            return []
        
        # 1. Gruppera
        grupper = self.gruppera(identifieringar)
        print(f"📊 {len(identifieringar)} identifieringar → {len(grupper)} grupper")
        
        # 2. Rösta
        produkter = []
        for grupp in grupper:
            resultat = self.rösta(grupp)
            if resultat:
                produkter.append(resultat)
        
        # 3. Applicera manuella korrigeringar
        for produkt in produkter:
            pid = produkt.get("position_id", "")
            if pid in self.manuella:
                korrigering = self.manuella[pid]
                print(f"📝 Manuell korrigering: {produkt.get('visningsnamn')} → {korrigering.get('visningsnamn')}")
                
                # Manuellt namn och position har högst prioritet
                if korrigering.get("visningsnamn"):
                    produkt["visningsnamn"] = korrigering["visningsnamn"]
                if korrigering.get("x") is not None:
                    produkt["x"] = korrigering["x"]
                if korrigering.get("z") is not None:
                    produkt["z"] = korrigering["z"]
                if korrigering.get("y") is not None:
                    produkt["y"] = korrigering["y"]
                    
                produkt["manuellt_korrigerad"] = True
                produkt["säkerhet"] = "hög"
        
        # Sortera på konfidens
        produkter.sort(key=lambda p: p.get("konfidens", 0), reverse=True)
        
        self.slutprodukter = produkter
        self._spara_produkter()
        
        hög = sum(1 for p in produkter if p.get("konfidens", 0) > 0.7)
        medium = sum(1 for p in produkter if 0.4 < p.get("konfidens", 0) <= 0.7)
        låg = sum(1 for p in produkter if p.get("konfidens", 0) <= 0.4)
        
        print(f"✅ {len(produkter)} produkter identifierade")
        print(f"   🟢 {hög} hög konfidens")
        print(f"   🟡 {medium} medium konfidens")
        print(f"   🔴 {låg} låg konfidens")
        
        return produkter
    
    # ─────────────────────────────────────────────
    # MANUELL KORRIGERING
    # ─────────────────────────────────────────────
    
    def korrigera(self, position_id: str, namn: str = None, 
                  x: float = None, y: float = None, z: float = None,
                  ta_bort: bool = False) -> dict:
        """
        Manuell korrigering av en produkt.
        Sparas permanent och appliceras vid varje ny bearbetning.
        """
        if ta_bort:
            self.manuella.pop(position_id, None)
            self._spara_manuella()
            return {"status": "borttagen", "position_id": position_id}
        
        korrigering = self.manuella.get(position_id, {})
        
        if namn is not None:
            korrigering["visningsnamn"] = namn
        if x is not None:
            korrigering["x"] = x
        if y is not None:
            korrigering["y"] = y
        if z is not None:
            korrigering["z"] = z
        
        korrigering["position_id"] = position_id
        self.manuella[position_id] = korrigering
        self._spara_manuella()
        
        # Uppdatera i slutprodukter om de finns
        for p in self.slutprodukter:
            if p.get("position_id") == position_id:
                if namn:
                    p["visningsnamn"] = namn
                if x is not None:
                    p["x"] = x
                if z is not None:
                    p["z"] = z
                p["manuellt_korrigerad"] = True
                break
        
        self._spara_produkter()
        
        return {"status": "ok", "korrigering": korrigering}
    
    def hämta_produkter(self) -> List[dict]:
        """Hämta alla identifierade produkter."""
        if not self.slutprodukter and PRODUKTER_PATH.exists():
            with open(PRODUKTER_PATH) as f:
                self.slutprodukter = json.load(f)
        return self.slutprodukter
    
    def lägg_till_manuell(self, namn: str, x: float, y: float, z: float) -> dict:
        """Lägg till en helt ny produkt manuellt."""
        position_id = f"manual_{x:.2f}_{z:.2f}"
        
        produkt = {
            "position_id": position_id,
            "visningsnamn": namn,
            "x": x,
            "y": y,
            "z": z,
            "säkerhet": "hög",
            "manuellt_korrigerad": True,
            "konfidens": 1.0,
            "röster": 0,
            "totalt_sett": 0,
        }
        
        self.manuella[position_id] = produkt
        self._spara_manuella()
        
        self.slutprodukter.append(produkt)
        self._spara_produkter()
        
        return produkt


# Singleton
_voting: Optional[ProduktVoting] = None

def get_voting() -> ProduktVoting:
    global _voting
    if _voting is None:
        _voting = ProduktVoting()
    return _voting
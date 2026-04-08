"""
Claude-powered produktsökning för Puls-AR.

Alltid Claude - $0.003 per sökning, mycket smartare.

Usage:
    from core.claude_sok import ClaudeSök
    
    sök = ClaudeSök('data/ica_produkter.json')
    resultat = sök.sök_sync("veganskt till fredagsmys")
"""

import json
import asyncio
from typing import Optional
import anthropic


class ClaudeSök:
    def __init__(self, produkter_path: str, api_key: Optional[str] = None):
        """
        Initialisera Claude-powered sökning.
        """
        with open(produkter_path, 'r', encoding='utf-8') as f:
            self.produkter = json.load(f)
        
        # Skapa index för snabb lookup
        self.id_to_produkt = {p['id']: p for p in self.produkter}
        
        # Förbereda kategori-grupper för smart filtrering
        self._bygg_kategori_index()
        
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        
        # Cache för snabbare upprepade sökningar
        self._cache = {}  # {query: (timestamp, resultat)}
        self._cache_max = 100
        self._cache_ttl = 3600  # 1 timme i sekunder
        
        print(f"✅ ClaudeSök laddade {len(self.produkter)} produkter")
        
        # Förladda vanliga sökningar i bakgrunden
        self._förladda_cache()
    
    def _förladda_cache(self):
        """Förladda cache med vanliga sökningar."""
        import threading
        import time
        
        def ladda():
            vanliga = ["mjölk", "bröd", "ägg", "ost", "kaffe", "frukt", "kött", "fisk", 
                       "pasta", "ris", "juice", "yoghurt", "smör", "korv", "kyckling"]
            print("🔄 Förladdar vanliga sökningar...")
            for term in vanliga:
                try:
                    self.sök_sync(term, limit=30)
                    time.sleep(3)  # Vänta 3 sekunder mellan varje
                except Exception as e:
                    print(f"   ⚠️ {term}: {e}")
                    time.sleep(5)  # Längre paus vid fel
            print(f"✅ Förladdat {len(self._cache)} sökningar i cache")
        
        thread = threading.Thread(target=ladda, daemon=True)
        thread.start()
        
    def _bygg_kategori_index(self):
        """Bygg index över produktkategorier för snabb filtrering."""
        self.kategori_keywords = {
            'mejeri': ['mjölk', 'ost', 'smör', 'grädde', 'yoghurt', 'fil', 'kvarg', 'ägg'],
            'kött': ['kött', 'fläsk', 'nöt', 'kyckling', 'korv', 'bacon', 'skinka', 'färs'],
            'fisk': ['fisk', 'lax', 'räk', 'tonfisk', 'sill', 'torsk'],
            'frukt_grönt': ['frukt', 'äpple', 'banan', 'tomat', 'gurka', 'sallad', 'grönsak', 'potatis'],
            'snacks': ['chips', 'godis', 'choklad', 'nötter', 'popcorn', 'snacks', 'dip'],
            'dryck': ['läsk', 'juice', 'vatten', 'öl', 'vin', 'kaffe', 'te', 'dryck'],
            'fryst': ['fryst', 'glass', 'pizza', 'pommes'],
            'bröd': ['bröd', 'knäcke', 'kaka', 'bulle'],
            'skafferi': ['pasta', 'ris', 'mjöl', 'socker', 'olja', 'sås', 'ketchup', 'senap'],
            'vego': ['vegan', 'vegetarisk', 'växtbaserad', 'tofu', 'soja', 'quorn'],
            'hälsa': ['protein', 'vitamin', 'eko', 'laktosfri', 'glutenfri'],
        }
        
        # Mappning: sökord → kategorier i databasen
        self.sökord_till_kategorier = {
            'mjölk': ['standardmjölk', 'mellanmjölk', 'lättmjölk', 'minimjölk', 'mjölkdryck'],
            'ägg': ['ägg'],
            'bröd': ['skivat bröd', 'lantbröd', 'frallor', 'baguette'],
            'ost': ['hårdost', 'mjukost', 'färskost', 'dessertost'],
            'kaffe': ['bryggkaffe', 'snabbkaffe', 'espresso'],
            'juice': ['apelsinjuice', 'äppeljuice', 'smoothie'],
            'yoghurt': ['naturell yoghurt', 'fruktyoghurt', 'turkisk yoghurt'],
            'fil': ['filmjölk', 'långfil'],
            'korv': ['falukorv', 'grillkorv', 'varmkorv', 'prinskorv'],
            'chips': ['potatischips', 'majschips', 'grönsakschips'],
        }
        
        # Korta ord som måste matcha som HELA ord (inte substring)
        self.hela_ord_match = {'ägg', 'ost', 'te', 'ris', 'öl', 'vin', 'rom', 'sås'}
    
    def _filtrera_kandidater(self, query: str, max_kandidater: int = 150) -> list[dict]:
        """Filtrera produkter baserat på sökfrågan. Prioriterar produkter som matchar fler sökord."""
        import re
        
        query_lower = query.lower()
        query_words = [w for w in query_lower.split() if len(w) >= 2]
        
        # Skapa ordstammar för bättre matchning
        def get_stam(word):
            for suffix in ['skt', 'ska', 'sk', 'en', 'et', 'erna', 'na', 'ar', 'or', 'er', 'a', 't']:
                if word.endswith(suffix) and len(word) > len(suffix) + 2:
                    return word[:-len(suffix)]
            return word
        
        query_stammar = [get_stam(w) for w in query_words]
        
        # Koncept-keywords för abstrakta sökningar
        koncept_keywords = {
            'fredagsmys': ['chips', 'dip', 'pizza', 'korv', 'godis', 'glass', 'popcorn', 'läsk', 'ost', 'nötter'],
            'frukost': ['müsli', 'flingor', 'yoghurt', 'mjölk', 'juice', 'bröd', 'ost', 'ägg', 'smör', 'fil'],
            'mellanmål': ['frukt', 'nötter', 'yoghurt', 'bar', 'kex', 'smoothie', 'kvarg'],
            'middag': ['kött', 'fisk', 'kyckling', 'pasta', 'ris', 'potatis', 'sås', 'färs'],
            'lunch': ['sallad', 'bröd', 'soppa', 'wrap', 'smörgås'],
        }
        
        extra_keywords = set()
        for koncept, kw_list in koncept_keywords.items():
            if koncept in query_lower:
                extra_keywords.update(kw_list)
        
        # Poängsätt alla produkter
        scored = []
        
        # Hitta relevanta kategorier baserat på sökorden
        relevanta_db_kategorier = set()
        for qw in query_words:
            if qw in self.sökord_till_kategorier:
                relevanta_db_kategorier.update(self.sökord_till_kategorier[qw])
        
        for p in self.produkter:
            namn = p.get('namn', '').lower()
            kategori = p.get('kategori', '').lower()
            sök_text = f"{namn} {kategori}"
            namn_ord = re.findall(r'\b\w+\b', sök_text)
            score = 0
            
            # BONUS: Om produkten är i en relevant kategori (t.ex. "standardmjölk")
            if any(rel_kat in kategori for rel_kat in relevanta_db_kategorier):
                score += 25  # Stor bonus!
            
            for qw, stam in zip(query_words, query_stammar):
                # För korta ord (ägg, ost, te) - matcha bara hela ord
                kräver_hel_match = qw in self.hela_ord_match or len(qw) <= 3
                
                # Exakt ordmatchning
                if qw in namn_ord:
                    score += 15
                    # Extra bonus om det är i produktnamnet (inte bara kategori)
                    if qw in namn.split():
                        score += 5
                # Stam-matchning (vegan → vegansk, veganskt) - INTE för korta ord
                elif not kräver_hel_match and any(ord.startswith(stam) and len(stam) >= 4 for ord in namn_ord):
                    score += 12
                # Prefix-matchning - INTE för korta ord
                elif not kräver_hel_match and any(ord.startswith(qw) and not ord.endswith('fri') for ord in namn_ord):
                    score += 10
                # Innehåller - INTE för korta ord
                elif not kräver_hel_match and stam in sök_text and f"{stam}fri" not in sök_text:
                    score += 5
            
            # Bonus för koncept-keywords
            if extra_keywords:
                for kw in extra_keywords:
                    if kw in namn:
                        score += 8
            
            if score > 0:
                scored.append((score, p))
        
        # Sortera efter score
        scored.sort(key=lambda x: -x[0])
        kandidater = [p for score, p in scored[:max_kandidater]]
        
        # Utöka med kategori-matchning om få resultat
        if len(kandidater) < 50:
            relevanta_keywords = set(extra_keywords)
            for qw in query_words:
                for kategori, keywords in self.kategori_keywords.items():
                    if qw in keywords or any(qw in kw or kw in qw for kw in keywords):
                        relevanta_keywords.update(keywords)
            
            for p in self.produkter:
                if p in kandidater:
                    continue
                namn = p.get('namn', '').lower()
                kategori = p.get('kategori', '').lower()
                if any(kw in namn or kw in kategori for kw in relevanta_keywords):
                    kandidater.append(p)
                    if len(kandidater) >= max_kandidater:
                        break
        
        return kandidater[:max_kandidater]
        
    def sök_sync(self, query: str, limit: int = 10) -> list[dict]:
        """Synkron sökning."""
        return asyncio.run(self.sök(query, limit))
    
    async def sök(self, query: str, limit: int = 10) -> list[dict]:
        """
        Sök produkter med Claude AI.
        """
        # Kolla cache först
        cache_key = f"{query.lower().strip()}:{limit}"
        if cache_key in self._cache:
            timestamp, cached_result = self._cache[cache_key]
            import time
            if time.time() - timestamp < self._cache_ttl:
                return cached_result
            else:
                del self._cache[cache_key]  # Utgången
        
        # Filtrera kandidater
        kandidater = self._filtrera_kandidater(query, max_kandidater=150)
        
        if not kandidater:
            # Fallback: skicka random subset
            kandidater = self.produkter[:150]
        
        # Formatera för Claude
        produkt_lista = "\n".join([
            f"{p['id']} | {p['namn']} | {p.get('kategori', '')}" 
            for p in kandidater
        ])
        
        prompt = f"""Du är en ICA-butiksassistent. Kunden söker: "{query}"

SVENSKA MJÖLKFÖRPACKNINGAR:
- RÖD = standardmjölk 3%
- GRÖN = mellanmjölk 1.5%
- BLÅ = lättmjölk 0.5%

STRIKTA REGLER:
1. Välj ENDAST produkter som kunden faktiskt vill ha
2. Om kunden söker "mjölk" - visa BARA mjölk, INTE choklad med mjölk, INTE mjölkfritt
3. Om kunden anger märke (ICA, Arla) - visa ENDAST det märket
4. Kvalitet över kvantitet - hellre 3 perfekta träffar än 30 halvdåliga
5. Om du är osäker - inkludera INTE produkten
6. Visa ALLA relevanta produkter, men max {limit} st

Produkter (id | namn | kategori):
{produkt_lista}

Svara ENDAST med produkt-ID för relevanta produkter, ett per rad. Ingen annan text.
Om bara 2 produkter är relevanta - svara med 2. Om 25 är relevanta - svara med 25 (max {limit})."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",  # Fungerar för dig
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parsa svar
            valda_ids = []
            for line in response.content[0].text.strip().split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    # Rensa bort eventuella nummer, punkter etc
                    clean = line.lstrip('0123456789.-) ').strip()
                    if clean:
                        valda_ids.append(clean)
            
            # Mappa till produkter
            resultat = []
            for pid in valda_ids[:limit]:
                if pid in self.id_to_produkt:
                    resultat.append(self.id_to_produkt[pid])
            
            # Spara i cache med timestamp
            import time
            if len(self._cache) >= self._cache_max:
                # Ta bort äldsta
                self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key] = (time.time(), resultat)
            
            return resultat
            
        except Exception as e:
            error_msg = str(e)
            print(f"⚠️ Claude API fel: {error_msg}")
            
            # Fallback: returnera top-kandidater baserat på score
            if "rate_limit" in error_msg.lower() or "429" in error_msg:
                print("   ↪ Använder fallback (top-kandidater)")
                return kandidater[:limit]
            
            return []


# Test
if __name__ == "__main__":
    sök = ClaudeSök('data/ica_produkter.json')
    
    queries = ["röd mjölk", "ica soja", "veganskt fredagsmys", "proteinrik frukost"]
    
    for q in queries:
        print(f'\n🔍 "{q}":')
        resultat = sök.sök_sync(q, limit=5)
        for p in resultat:
            print(f'   {p["namn"]} ({p.get("varumarke", "")})')
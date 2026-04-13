"""
Smart produktsökning med Haiku AI.

Haiku ser PRODUKTER (inte kategorier) och väljer de relevanta.
Resultat cachas permanent → nästa sökning instant.

Flöde:
1. Kolla cache (<1ms)
2. Förfiltrera kandidater lokalt (~200 produkter, <10ms)  
3. Haiku väljer de bästa produkterna (~1s)
4. Spara i cache → nästa gång instant

Kostnad: ~$0.001 per NY sökning (Haiku är billig)
"""

import json
import os
from typing import Optional
import anthropic


class SmartSök:
    def __init__(self, produkter_path: str, cache_path: str = None):
        """
        Initialisera smart sökning.
        """
        # Ladda produkter
        with open(produkter_path, 'r', encoding='utf-8') as f:
            self.produkter = json.load(f)
        
        self.id_to_produkt = {p['id']: p for p in self.produkter}
        
        # Cache-sökväg
        if cache_path is None:
            base_dir = os.path.dirname(produkter_path)
            cache_path = os.path.join(base_dir, 'sok_cache.json')
        
        self.cache_path = cache_path
        
        # Ladda eller skapa cache
        if os.path.exists(self.cache_path):
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                self.cache = json.load(f)
            self._cache_mtime = os.path.getmtime(self.cache_path)
        else:
            self.cache = {}
            self._cache_mtime = 0
            self._spara_cache()
        
        # Haiku-klient
        self.client = anthropic.Anthropic()
        
        print(f"✅ SmartSök laddade {len(self.produkter)} produkter, {len(self.cache)} cachade sökningar")
    
    def _spara_cache(self):
        """Spara cache till disk."""
        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)
        self._cache_mtime = os.path.getmtime(self.cache_path)
    
    def _tolka_okänd_sökning(self, query: str) -> list:
        """
        Använd Haiku för att tolka en abstrakt sökning till konkreta keywords.
        """
        prompt = f"""En kund i en matbutik söker: "{query}"

Vilka PRODUKTTYPER eller INGREDIENSER letar kunden troligen efter?

Svara med 5-10 relevanta sökord på svenska, ett per rad.
Tänk på vad som faktiskt finns i en matbutik.

Exempel:
- "nyttigt lördagsgodis" → nötter, mörk choklad, torkad frukt, müslibars, popcorn
- "festmat till många" → korv, bröd, sallad, chips, läsk, grillspett
- "snabb vardagsmiddag" → pasta, sås, färs, kyckling, wok, ris

Svara ENDAST med sökord, ett per rad:"""

        try:
            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )
            
            keywords = []
            for line in response.content[0].text.strip().split('\n'):
                word = line.strip().lstrip('•-* ').lower()
                if word and len(word) >= 2:
                    keywords.append(word)
            
            print(f"🧠 Haiku tolkade '{query}' → {keywords[:8]}")
            return keywords[:10]
            
        except Exception as e:
            print(f"⚠️ Kunde inte tolka sökning: {e}")
            return []
    
    def _förfiltrera(self, query: str, max_kandidater: int = 50) -> list:
        """
        Förfiltrera produkter baserat på sökorden.
        Returnerar produkter som matchar minst ett sökord.
        """
        query_lower = query.lower()
        query_ord = [w for w in query_lower.split() if len(w) >= 2]
        
        if not query_ord:
            return []
        
        # Koncept-expansion för abstrakta sökningar
        koncept_keywords = {
            'fredagsmys': ['chips', 'dip', 'pizza', 'korv', 'godis', 'glass', 'popcorn', 'läsk', 'ost', 'nötter'],
            'frukost': ['müsli', 'flingor', 'yoghurt', 'mjölk', 'juice', 'bröd', 'ost', 'ägg', 'smör', 'fil'],
            'mellanmål': ['frukt', 'nötter', 'yoghurt', 'bar', 'kex', 'smoothie', 'kvarg'],
            'middag': ['kött', 'fisk', 'kyckling', 'pasta', 'ris', 'potatis', 'sås', 'färs'],
            'grill': ['korv', 'kött', 'marinad', 'bröd', 'sås', 'sallad', 'öl', 'läsk'],
            'kalas': ['godis', 'chips', 'läsk', 'tårta', 'glass', 'korv', 'popcorn', 'ballong'],
            'hälsosam': ['frukt', 'grönsak', 'nötter', 'yoghurt', 'kvarg', 'protein', 'sallad'],
            'vegansk': ['vegan', 'växtbaserad', 'tofu', 'soja', 'havre', 'mjölkfri'],
            'vegetarisk': ['vegetarisk', 'vego', 'quorn', 'tofu', 'halloumi', 'bönor'],
            'fika': ['bulle', 'kaka', 'kaffe', 'te', 'choklad', 'kex', 'muffin', 'biscotti', 'wienerbröd'],
            'fikat': ['bulle', 'kaka', 'kaffe', 'te', 'choklad', 'kex', 'muffin', 'biscotti', 'wienerbröd'],
            'sött': ['choklad', 'godis', 'kaka', 'glass', 'sylt', 'kex', 'bulle', 'muffin'],
            'dessert': ['glass', 'choklad', 'mousse', 'pannacotta', 'tårta', 'frukt', 'grädde'],
            'barnmat': ['välling', 'gröt', 'barnmat', 'fruktpuré', 'smoothie barn'],
            'picknick': ['smörgås', 'frukt', 'juice', 'kex', 'ost', 'skinka', 'sallad'],
        }
        
        # Synonymer - sökord som betyder samma sak (inkl kategorier)
        synonymer = {
            'pasta': ['spaghetti', 'makaroner', 'penne', 'fusilli', 'tagliatelle', 'lasagne', 
                     'linguine', 'rigatoni', 'farfalle', 'gemelli', 'formpasta', 'fettuccine',
                     'papardelle', 'ravioli', 'tortellini'],
            'mjölk': ['standardmjölk', 'mellanmjölk', 'lättmjölk', 'mjölkdryck', 'minimjölk'],
            'bröd': ['limpa', 'fralla', 'baguette', 'knäcke', 'rostbröd', 'levain', 'ciabatta'],
            'ost': ['cheddar', 'mozzarella', 'parmesan', 'gouda', 'brie', 'halloumi', 'fetaost', 
                   'färskost', 'hårdost', 'mjukost'],
            'kött': ['nötkött', 'fläsk', 'lamm', 'vilt', 'köttfärs', 'entrecote', 'ryggbiff'],
            'fisk': ['lax', 'torsk', 'sill', 'räkor', 'tonfisk', 'makrill', 'rödspätta', 'sej'],
            'kyckling': ['kycklingfilé', 'kycklingben', 'kycklingklubba', 'kycklinglår', 'kycklingfärs'],
            'juice': ['apelsinjuice', 'äppeljuice', 'smoothie', 'tropisk juice'],
            'godis': ['choklad', 'lösgodis', 'lakrits', 'geléhallon', 'polkagris'],
            'chips': ['tortillachips', 'potatischips', 'grönsakschips'],
            'yoghurt': ['grekisk yoghurt', 'turkisk yoghurt', 'naturell yoghurt', 'smaksatt yoghurt',
                       'drickyoghurt', 'laktosfri yoghurt'],
        }
        
        # Lägg till koncept-keywords
        extra_ord = set()
        for koncept, keywords in koncept_keywords.items():
            if koncept in query_lower:
                extra_ord.update(keywords)
        
        # Lägg till synonymer
        for sökord in query_ord:
            if sökord in synonymer:
                extra_ord.update(synonymer[sökord])
        
        alla_sökord = set(query_ord) | extra_ord
        
        # Poängsätt produkter
        scored = []
        for p in self.produkter:
            namn = p.get('namn', '').lower()
            kategori = p.get('kategori', '').lower()
            varumärke = p.get('varumarke', '').lower()
            söktext = f"{namn} {kategori} {varumärke}"
            
            score = 0
            matched_original = set()  # Vilka ursprungliga sökord som matchade
            
            for qw in alla_sökord:
                is_original = qw in query_ord
                is_synonym = qw in extra_ord
                
                if qw in namn.split():
                    score += 15  # Exakt ordmatch i namn
                    if is_original:
                        matched_original.add(qw)
                elif qw in namn:
                    score += 8   # Delvis match i namn
                    if is_original:
                        matched_original.add(qw)
                
                # Match i kategori - viktigt för synonymer!
                if qw in kategori.lower().split() or qw in kategori.lower():
                    score += 10  # Högre poäng för kategorimatch
                    # Om synonym matchar kategori, räkna som om original matchade
                    if is_synonym:
                        for orig, syns in synonymer.items():
                            if qw in syns and orig in query_ord:
                                matched_original.add(orig)
                
                if qw in varumärke:
                    score += 3   # Match i varumärke
            
            # BONUS: Om ALLA ursprungliga sökord matchade (direkt eller via synonym)
            if len(matched_original) == len(query_ord) and len(query_ord) > 1:
                score += 50  # Stor bonus för full match
            
            if score > 0:
                scored.append((score, p))
        
        # Sortera och returnera top kandidater
        scored.sort(key=lambda x: -x[0])
        return [p for _, p in scored[:max_kandidater]]
    
    def _fråga_haiku(self, query: str, kandidater: list, limit: int) -> list:
        """
        Skicka produktlista till Haiku och låt den välja.
        """
        # Formatera produkter för Haiku
        produkt_lista = "\n".join([
            f"{p['id']} | {p['namn']} | {p.get('kategori', '')}"
            for p in kandidater
        ])

        prompt = f"""Kunden söker: "{query}"
Produkter (id | namn | kategori):
{produkt_lista}
Svara med relevanta produkt-ID:n, ett per rad. Max {limit}. Ingen annan text."""

        try:
            response = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=300,
                system="Du är en ICA-butiksassistent. Välj ALLA relevanta produkter. Exkludera irrelevant. Svara BARA med ID:n.",
                messages=[{"role": "user", "content": prompt}]
            )
        
            # Parsa svar
            valda_ids = []
            for line in response.content[0].text.strip().split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    # Rensa bort nummer, punkter etc
                    clean = line.lstrip('0123456789.-) ').strip()
                    if clean:
                        valda_ids.append(clean)
            
            # Mappa till produkter
            resultat = []
            for pid in valda_ids[:limit]:
                if pid in self.id_to_produkt:
                    resultat.append(self.id_to_produkt[pid])
            
            return resultat
            
        except Exception as e:
            print(f"⚠️ Haiku-fel: {e}")
            # Fallback: returnera top-kandidater
            return kandidater[:limit]
    
    def _ladda_cache_om_ändrad(self):
        """Ladda om cache från disk om en annan worker har uppdaterat den."""
        try:
            mtime = os.path.getmtime(self.cache_path)
            if mtime > self._cache_mtime:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    self.cache = json.load(f)
                self._cache_mtime = mtime
        except:
            pass
    
    async def sök(self, query: str, limit: int = 30) -> list:
        query_norm = query.lower().strip()
        cache_key = query_norm

        self._ladda_cache_om_ändrad()

        # 1. Kolla cache
        if cache_key in self.cache:
            ids = self.cache[cache_key]
            produkter = [self.id_to_produkt[pid] for pid in ids if pid in self.id_to_produkt]
            return produkter[:limit]

        # 2. Förfiltrera lokalt
        kandidater = self._förfiltrera(query, max_kandidater=50)

        if not kandidater:
            print(f"⚠️ Inga kandidater för '{query}'")
            return []

        print(f"🔍 '{query}': {len(kandidater)} kandidater → frågar Haiku...")

        # 3. Haiku väljer
        resultat = self._fråga_haiku(query, kandidater, 50)

        # 4. Spara i cache
        if resultat:
            self.cache[cache_key] = [p['id'] for p in resultat]
            self._spara_cache()
            print(f"✨ Cachade '{query}' ({len(resultat)} produkter)")

        return resultat[:limit]

    def sök_sync(self, query: str, limit: int = 30, use_claude_fallback: bool = True) -> list:
        """Synkron wrapper för sök."""
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.sök(query, limit))
    
    def rensa_cache(self, query: str = None):
        """Rensa cache för en specifik sökning eller alla."""
        if query:
            query_norm = query.lower().strip()
            keys_to_remove = [k for k in self.cache.keys() if k.startswith(query_norm)]
            for k in keys_to_remove:
                del self.cache[k]
            print(f"🗑️ Rensade cache för '{query}'")
        else:
            self.cache = {}
            print("🗑️ Rensade all cache")
        self._spara_cache()


# Test
if __name__ == "__main__":
    sök = SmartSök('data/ica_produkter.json')
    
    queries = [
        "ekologisk pasta",
        "röd mjölk",
        "något gott till fredagsmys",
        "vegansk ost",
        "proteinbar",
    ]
    
    for q in queries:
        print(f'\n🔍 "{q}":')
        resultat = sök.sök_sync(q, limit=10)
        print(f'   {len(resultat)} resultat')
        for p in resultat[:5]:
            print(f'   • {p["namn"][:45]}')
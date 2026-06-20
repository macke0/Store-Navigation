"""
produkt_sok.py - Fuzzy produktsökning för Puls-AR
─────────────────────────────────────────────────────────────────
Söker bland ICA-produkter med fuzzy matching.
Exakt stavning krävs inte - "ica soja" hittar "ICA Sojadryck Naturell".

Använder difflib (inbyggt) eller rapidfuzz (om installerat).
"""

import json
from pathlib import Path
from typing import Optional
from difflib import SequenceMatcher

# Försök använda rapidfuzz om det finns, annars fallback till difflib
try:
    from rapidfuzz import fuzz, process
    USE_RAPIDFUZZ = False
except ImportError:
    USE_RAPIDFUZZ = False


# Svenska böjnings-/plural-/bestämdhetsändelser. Om resten EFTER ett ord som
# börjar med sökordet är en sån ändelse → samma ord böjt (tomat→tomater,
# lök→lökar, ägg→äggen) → nästan exakt. Är resten NÅGOT annat bildar den ett
# ANNAT ord (mjöl→mjöl+k=mjölk, is→is+låda) → mycket svagare. Ren längd räcker
# inte: "k" är kort men gör mjöl→mjölk till en annan vara.
_BÖJNINGS_SUFFIX = frozenset({
    "", "s", "r", "n", "t", "a", "e",
    "er", "ar", "or", "en", "et", "na", "as", "rs", "ns", "ts",
    "ena", "erna", "arna", "orna",
})


def fuzzy_ratio(s1: str, s2: str) -> float:
    """
    Beräkna likhet mellan två strängar (0-100).
    Smart matchning som förstår produktkategorier.
    """
    if USE_RAPIDFUZZ:
        return fuzz.token_set_ratio(s1, s2)
    
    s1_lower = s1.lower()
    s2_lower = s2.lower()
    
    # Dela upp i ord
    query_words = [w for w in s1_lower.split() if len(w) > 1]
    target_words = s2_lower.split()
    
    if not query_words:
        return 0
    
    # Kända produktkategorier - dessa är "viktiga" ord
    produktkategorier = {
        "mjölk", "bröd", "ost", "smör", "ägg", "kaffe", "te", "juice", 
        "yoghurt", "fil", "grädde", "ketchup", "senap", "soja", "pasta",
        "ris", "nudlar", "flingor", "müsli", "sylt", "honung", "socker",
        "mjöl", "olja", "vinäger", "salt", "peppar", "kryddor", "örter",
        "kött", "fläsk", "nöt", "kyckling", "fisk", "lax", "räkor", "korv",
        "skinka", "bacon", "frukt", "äpple", "banan", "apelsin", "grönsaker",
        "tomat", "gurka", "lök", "potatis", "morötter", "sallad", "chips",
        "godis", "choklad", "glass", "kakor", "bullar", "dryck", "vatten",
        "läsk", "öl", "vin", "tvål", "schampo", "tandkräm", "toapapper"
    }
    
    # Attributord - färger, storlekar, egenskaper (bonus, inte krav)
    # "röd mjölk" → "mjölk" är viktigt, "röd" är bara bonus
    attributord = {
        "röd", "grön", "blå", "gul", "vit", "svart", "brun", "rosa", "lila", "orange",
        "stor", "liten", "mellan", "mini", "maxi", "familj",
        "eko", "ekologisk", "krav", "svensk", "laktosfri", "glutenfri", "vegan",
        "lätt", "mager", "fet", "stark", "mild", "kryddig"
    }
    
    # Kända varumärken - dessa är också "viktiga" ord (måste matcha om angivna)
    varumärken = {
        "ica", "arla", "valio", "oatly", "alpro", "felix", "heinz", "kikkoman",
        "pågen", "fazer", "findus", "scan", "hk", "gorby", "atria", "tulip",
        "coca", "cola", "pepsi", "fanta", "sprite", "ramlösa", "loka",
        "nescafe", "gevalia", "löfbergs", "zoégas", "lavazza",
        "marabou", "cloetta", "fazer", "lindt", "toblerone",
        "kellog", "quaker", "axa", "start",
        "knorr", "maggi", "santa", "maria", "old", "elpaso",
        "nivea", "dove", "palmolive", "colgate", "oral"
    }
    
    def is_attributord(word):
        """Kolla om ordet är ett attribut (färg, storlek, etc)"""
        return word in attributord
    
    def is_varumärke(word):
        """Kolla om ordet är ett känt varumärke"""
        return word in varumärken
    
    def word_matches(query_word, target_word, word_position):
        """Kolla om sökord matchar target-ord."""
        qlen = len(query_word)
        position_bonus = max(0, 0.1 - (word_position * 0.02))
        
        if query_word == target_word:
            return 1.0 + position_bonus
        if target_word.startswith(query_word):
            rest = target_word[qlen:]
            # Rest = böjningsändelse (tomat→tomater) → samma ord → nästan exakt.
            # Annars är sökordet bara FÖRLED i ett ANNAT ord (mjöl→mjölk(dryck),
            # is→islåda, ägg→äggvita) → mycket svagare, så att en suffix-
            # sammansättning som FAKTISKT är en sorts varan (vetemjöl = en sorts
            # mjöl, 0.85 nedan) rankas högre.
            if rest in _BÖJNINGS_SUFFIX:
                return 0.95 + position_bonus
            return 0.6
        if qlen >= 4 and target_word.endswith(query_word):
            return 0.85
        if qlen >= 5 and query_word in target_word:
            return 0.75
        if query_word.startswith(target_word) and len(target_word) >= 4:
            return 0.65 + position_bonus
        return 0
    
    # Räkna matchning för varje sökord
    word_scores = []
    important_word_matched = False  # Produktkategori matchad?
    
    for qw in query_words:
        best_match = 0
        exact_match_found = False
        
        for idx, tw in enumerate(target_words):
            match = word_matches(qw, tw, idx)
            best_match = max(best_match, match)
            # Kolla om det är en exakt match (eller nästan exakt)
            if match >= 1.0:
                exact_match_found = True
        
        # Kolla om detta är ett viktigt ord (produktkategori eller varumärke) eller bara attribut
        is_produktord = qw in produktkategorier or any(qw in pk for pk in produktkategorier)
        is_brand = is_varumärke(qw)
        is_attr = is_attributord(qw)
        
        # NYTT: Om ordet matchar EXAKT i produktnamnet → det är viktigt!
        # "sojafärs" matchar exakt → viktigt, även om det inte finns i listan
        if exact_match_found and not is_attr:
            is_produktord = True
        
        # Produktord OCH varumärken är viktiga, attributord är bonus
        is_important = (is_produktord or is_brand) and not is_attr
        
        if is_important and best_match >= 0.5:
            important_word_matched = True
        
        word_scores.append((best_match, is_important, is_attr))
    
    # Om vi har viktiga ord (produktkategori eller varumärke), kräv att de matchar
    if important_word_matched:
        # Kolla om ALLA viktiga ord matchade
        important_scores = [(score, is_imp) for score, is_imp, is_attr in word_scores if is_imp]
        
        # Om något viktigt ord INTE matchade → uteslut
        for score, is_imp in important_scores:
            if score < 0.5:
                return 0  # Viktigt ord matchar inte → visa inte produkten
        
        # NYTT: Kolla att alla ICKE-attributord matchar (även om de inte är "viktiga")
        # "sojafärs" är inte attribut, så det MÅSTE matcha
        for score, is_important, is_attr in word_scores:
            if not is_attr and score < 0.5:
                # Ett ord som inte är attribut matchar inte → uteslut
                return 0
        
        # Alla viktiga ord matchar! Beräkna score.
        important_total = sum(s[0] for s in important_scores)
        important_count = len(important_scores)
        
        # Bonus för attributord som också matchar
        bonus_total = 0
        for score, is_important, is_attr in word_scores:
            if not is_important:
                if is_attr:
                    bonus_total += score * 0.1  # Liten bonus för färg etc
                else:
                    bonus_total += score * 0.3  # Bonus för andra matchande ord
        
        avg_match = important_total / important_count + bonus_total
    else:
        # Inga produktord/varumärken - kräv att alla ord matchar
        min_match = min(s[0] for s in word_scores)
        if min_match < 0.5:
            return 0
        avg_match = sum(s[0] for s in word_scores) / len(word_scores)
    
    if avg_match >= 1.0:
        base_score = 90
        length_penalty = min(12, len(s2_lower) / 10)
        return max(78, base_score + 10 - length_penalty)
    elif avg_match >= 0.9:
        base_score = 82
        length_penalty = min(12, len(s2_lower) / 10)
        return max(70, base_score + 10 - length_penalty)
    elif avg_match >= 0.7:
        return 60 + avg_match * 25
    elif avg_match >= 0.5:
        return 45 + avg_match * 30
    else:
        return avg_match * 40


class ProduktSök:
    def __init__(self, produkter_fil: str = "data/ica_produkter.json"):
        """Ladda ICA-produkter för sökning."""
        self.produkter = []
        self.sök_index = {}
        self.sök_nycklar = []
        self.id_index = {}
        
        produkter_path = Path(produkter_fil)
        if produkter_path.exists():
            with open(produkter_path, encoding="utf-8") as f:
                self.produkter = json.load(f)
            self._bygg_index()
            print(f"✅ Laddade {len(self.produkter)} produkter för sökning")
        else:
            print(f"⚠️  Produktfil saknas: {produkter_fil}")
    
    def _bygg_index(self):
        """Bygg sökindex från produkter."""
        for p in self.produkter:
            # ID-index för snabb lookup
            self.id_index[p.get("id", "")] = p
            
            # Sökindex - namn, varumärke och kategori
            namn = p.get("namn", "").lower()
            varumarke = p.get("varumarke", "").lower()
            kategori = p.get("kategori", "").lower()
            
            # Spara separat för viktning
            p["_namn"] = namn
            p["_varumarke"] = varumarke
            p["_kategori"] = kategori
            
            # Kombinera för sökning (namn väger tyngst)
            sök_text = f"{namn} {varumarke}".strip()
            self.sök_index[sök_text] = p
        
        self.sök_nycklar = list(self.sök_index.keys())
    
    def sök(self, query: str, limit: int = 5) -> list[dict]:
        """
        Fuzzy-sökning på produkter.
        - Prioriterar "riktiga" produkter (mjölk > kokosmjölk)
        - Prioriterar ICA-märke
        - Prioriterar vanliga storlekar (1L, 1.5L, 500g)
        """
        if not query or not self.sök_nycklar:
            return []
        
        query = query.lower().strip()
        query_words = [w for w in query.split() if len(w) > 1]
        
        # Kategorier som inte är matvaror eller fel för sökordet
        icke_mat_kategorier = [
            "rostar", "maskin", "korgar", "kannor", "knivar", "bestick",
            "tillbehör", "porslin", "glas ", "skålar", "formar", "köks",
            "burk", "hyvel", "timer", "skärare", "kopp", "mått", "press",
            "tvål", "silar", "trattar", "sikt", "dukar", "ljus", "värmeljus",
            "rengöring", "diskmedel", "tvätt", "schampo", "balsam",
            "chips", "snacks", "godis", "chokladkaka"  # Inte bröd/mjölk
        ]
        
        # Ord som utesluter produkten (t.ex. "mjölkfritt" när man söker "mjölk")
        uteslutande_suffix = {
            "mjölk": ["mjölkfri", "mjölkfritt"],
            "gluten": ["glutenfri", "glutenfritt"],
            "socker": ["sockerfri", "sockerfritt"],
            "laktos": ["laktosfri", "laktosfritt"],
        }
        
        # PRIMÄRA kategorier = "riktig" produkt (mjölk = standardmjölk, inte kokosmjölk)
        # SEKUNDÄRA kategorier = varianter som kräver specifik sökning
        primära_kategorier = {
            "mjölk": ["standardmjölk", "mellanmjölk", "lättmjölk", "minimjölk", "filmjölk"],
            "bröd": ["skivat bröd", "lantbröd", "frallor", "baguette", "pitabröd", "tortilla"],
            "ost": ["hårdost", "svecia", "grevé", "prästost", "herrgård", "cheddar", "gouda"],
            "kaffe": ["brygg", "kokkaffe", "mellanrost", "mörkrost"],
            "juice": ["apelsin", "äpple", "juice"],
            "ägg": ["ägg från"],
            "smör": ["normalsaltat", "osaltat", "svenskt smör"],
            "yoghurt": ["naturell", "mild", "turkisk"],
            "pasta": ["spaghetti", "penne", "fusilli", "tagliatelle"],
            "ris": ["basmati", "jasmin", "långkornigt"],
        }
        
        # Sekundära = kräver specifik sökning (kondenserad mjölk, kokosmjölk, etc)
        sekundära_kategorier = {
            "mjölk": ["kondenserad", "kokos", "mandel", "havre", "soja", "ersättning", "smaksatt", "choklad", "kakor", "kex", "godis"],
            "bröd": ["knäcke", "skorpa", "ströbröd"],
            "ost": ["färsk", "keso", "kvarg", "smält", "cream cheese"],
            "kaffe": ["snabb", "kapslar", "espresso"],
        }
        
        # Vanliga storlekar som prioriteras
        vanliga_storlekar = ["1l", "1,5l", "1.5l", "2l", "500g", "1kg", "400g", "500ml"]
        
        # Beräkna score för alla produkter
        scores = []
        for sök_text, produkt in self.sök_index.items():
            kategori = produkt.get("_kategori", "")
            namn = produkt.get("_namn", "")
            varumarke = produkt.get("_varumarke", "")
            
            # Kolla om det är icke-mat
            is_icke_mat = any(x in kategori for x in icke_mat_kategorier)
            
            # Kolla om produkten innehåller uteslutande suffix (mjölkfritt för mjölk-sökning)
            is_excluded = False
            for qw in query_words:
                if qw in uteslutande_suffix:
                    for suffix in uteslutande_suffix[qw]:
                        if suffix in namn:
                            is_excluded = True
                            break
            
            # Primär matchning på namn+varumärke
            score = fuzzy_ratio(query, sök_text)
            
            # Om score är 0 betyder det att inte alla sökord matchar
            # Då ska vi INTE ge kategori-bonus
            if score == 0:
                continue  # Skippa denna produkt helt
            
            # PRIMÄR vs SEKUNDÄR kategori-logik (bara om namn+varumärke matchar)
            is_primär = False
            is_sekundär = False
            
            for qw in query_words:
                # Kolla primära kategorier
                if qw in primära_kategorier:
                    for prim_kat in primära_kategorier[qw]:
                        if prim_kat in kategori:
                            is_primär = True
                            score += 15  # Bonus, inte sätt minimum
                            break
                    # Kolla sekundära kategorier
                    if qw in sekundära_kategorier:
                        for sek_kat in sekundära_kategorier[qw]:
                            if sek_kat in kategori:
                                is_sekundär = True
                                break
            
            # Om sekundär kategori men INTE sökt specifikt → nedprioritera kraftigt
            if is_sekundär and not is_primär:
                # Kolla om användaren sökte specifikt (t.ex. "kokosmjölk")
                sökt_specifikt = any(sek in query for sek in 
                    ["kokos", "kondenserad", "mandel", "havre", "soja", "knäcke", "kapslar"])
                if not sökt_specifikt:
                    score -= 30  # Stor minskning för ospecifik sökning
            
            # Vanlig kategori-match (för ord som inte har primära kategorier)
            # OBS: Bara bonus om score redan > 0
            if not is_primär and not is_sekundär and not is_icke_mat and score > 0:
                kategori_ord = kategori.split()
                for qw in query_words:
                    if len(qw) >= 3 and any(qw == ko or ko.startswith(qw) for ko in kategori_ord):
                        score += 8  # Bara bonus, inte sätt minimum
                        break
            
            # Vanliga storlekar bonus
            for storlek in vanliga_storlekar:
                if storlek in namn:
                    score += 3
                    break
            
            # Nedprioritera icke-mat
            if is_icke_mat and score >= 40:
                score -= 30
            
            # Nedprioritera uteslutna (t.ex. "mjölkfritt" när man söker "mjölk")
            if is_excluded and score >= 40:
                score -= 40
            
            if score >= 40:
                scores.append((produkt, score))
        
        # Sortera på score (högst först)
        scores.sort(key=lambda x: x[1], reverse=True)
        
        produkter = []
        sett_ids = set()
        kategori_count = {}  # Räkna produkter per HUVUD-kategori
        MAX_PER_KATEGORI = 5  # Max 5 produkter per huvudkategori för mer variation
        
        def get_huvudkategori(kat: str) -> str:
            """Extrahera huvudkategori: 'Standardmjölk, laktos' -> 'standardmjölk'"""
            return kat.lower().split(",")[0].strip()
        
        for produkt, score in scores:
            prod_id = produkt.get("id")
            kategori = produkt.get("kategori", "Okänd")
            huvudkat = get_huvudkategori(kategori)
            
            # Undvik dubbletter
            if prod_id in sett_ids:
                continue
            
            # Diversifiering: max 2 per HUVUD-kategori
            if kategori_count.get(huvudkat, 0) >= MAX_PER_KATEGORI:
                continue
            
            sett_ids.add(prod_id)
            kategori_count[huvudkat] = kategori_count.get(huvudkat, 0) + 1
            
            produkt_kopia = produkt.copy()
            # Ta bort interna fält
            produkt_kopia.pop("_namn", None)
            produkt_kopia.pop("_varumarke", None)
            produkt_kopia.pop("_kategori", None)
            produkt_kopia["match_score"] = round(score, 1)
            produkter.append(produkt_kopia)
            
            if len(produkter) >= limit:
                break
        
        return produkter
    
    def hämta(self, produkt_id: str) -> Optional[dict]:
        """Hämta produkt via ID."""
        return self.id_index.get(produkt_id)
    
    def hitta_liknande(self, produkt_id: str, limit: int = 5) -> list[dict]:
        """
        Hitta liknande produkter i samma kategori.
        Användbart när en produkt är slut.
        """
        produkt = self.hämta(produkt_id)
        if not produkt:
            return []
        
        kategori = produkt.get("kategori", "")
        underkategori = produkt.get("underkategori", "")
        varumarke = produkt.get("varumarke", "")
        
        liknande = []
        for p in self.produkter:
            if p.get("id") == produkt_id:
                continue
            
            # Måste vara samma kategori
            if p.get("kategori") != kategori:
                continue
            
            # Poängsätt likhet
            score = 50  # Samma kategori
            if p.get("underkategori") == underkategori:
                score += 30  # Samma underkategori
            if p.get("varumarke") == varumarke:
                score += 20  # Samma märke
            
            p_kopia = p.copy()
            p_kopia["likhet_score"] = score
            liknande.append(p_kopia)
        
        # Sortera på likhet
        liknande.sort(key=lambda x: x["likhet_score"], reverse=True)
        return liknande[:limit]
    
    def hitta_nyttigare(self, produkt_id: str, limit: int = 5) -> list[dict]:
        """
        Hitta nyttigare alternativ i samma kategori.
        Jämför socker, fett och kalorier.
        """
        produkt = self.hämta(produkt_id)
        if not produkt:
            return []
        
        kategori = produkt.get("kategori", "")
        
        # Hämta näringsvärden för ursprungsprodukten
        original_socker = produkt.get("socker_g_100g")
        original_fett = produkt.get("fett_g_100g")
        original_kalorier = produkt.get("kalorier_100g")
        
        # Om näringsvärden saknas, kan vi inte jämföra
        if original_socker is None and original_fett is None and original_kalorier is None:
            return []
        
        alternativ = []
        for p in self.produkter:
            if p.get("id") == produkt_id:
                continue
            if p.get("kategori") != kategori:
                continue
            
            p_socker = p.get("socker_g_100g")
            p_fett = p.get("fett_g_100g")
            p_kalorier = p.get("kalorier_100g")
            
            # Beräkna nyttighetspoäng
            nyttighets_score = 0
            jämförelse = {}
            
            if original_socker is not None and p_socker is not None:
                if p_socker < original_socker:
                    nyttighets_score += (original_socker - p_socker) * 3
                    jämförelse["socker"] = f"{p_socker}g vs {original_socker}g (−{original_socker - p_socker}g)"
            
            if original_fett is not None and p_fett is not None:
                if p_fett < original_fett:
                    nyttighets_score += (original_fett - p_fett) * 2
                    jämförelse["fett"] = f"{p_fett}g vs {original_fett}g (−{original_fett - p_fett}g)"
            
            if original_kalorier is not None and p_kalorier is not None:
                if p_kalorier < original_kalorier:
                    nyttighets_score += (original_kalorier - p_kalorier) / 10
                    jämförelse["kalorier"] = f"{p_kalorier} vs {original_kalorier} (−{original_kalorier - p_kalorier})"
            
            if nyttighets_score > 0:
                p_kopia = p.copy()
                p_kopia["nyttighets_score"] = round(nyttighets_score, 1)
                p_kopia["jämförelse"] = jämförelse
                alternativ.append(p_kopia)
        
        alternativ.sort(key=lambda x: x["nyttighets_score"], reverse=True)
        return alternativ[:limit]
    
    def produkter_i_kategori(self, kategori: str, limit: int = 10) -> list[dict]:
        """Hämta alla produkter i en kategori."""
        return [
            p for p in self.produkter 
            if p.get("kategori", "").lower() == kategori.lower()
        ][:limit]


# Singleton instance
_produkt_sök: Optional[ProduktSök] = None


def get_produkt_sök(produkter_fil: str = "data/ica_produkter.json") -> ProduktSök:
    """Hämta eller skapa singleton ProduktSök."""
    global _produkt_sök
    if _produkt_sök is None:
        _produkt_sök = ProduktSök(produkter_fil)
    return _produkt_sök


def ladda_om_produkter(produkter_fil: str = "data/ica_produkter.json"):
    """Ladda om produkter från fil."""
    global _produkt_sök
    _produkt_sök = ProduktSök(produkter_fil)
    return _produkt_sök
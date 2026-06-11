"""
claude_assistant.py - Claude-powered butiksassistent för Puls-AR
─────────────────────────────────────────────────────────────────
Unified chat som hanterar:
- Produktsökning (fuzzy)
- Produktinformation
- Liknande produkter (om slut)
- Nyttigare alternativ
- Produktposition i butiken

Allt i samma konversation med kontext!
"""

import anthropic
import json
from typing import Optional
from core.produkt_sok import get_produkt_sök

# Claude-klient (kräver ANTHROPIC_API_KEY miljövariabel)
client = anthropic.Anthropic()


# ─────────────────────────────────────────────
# TOOLS som Claude kan använda
# ─────────────────────────────────────────────

TOOLS = [
    {
        "name": "sok_produkter",
        "description": """Söker efter produkter i butiken med fuzzy matching. 
Användaren behöver inte skriva exakt - "ica soja" hittar "ICA Sojadryck Naturell".
Returnerar en lista med matchande produkter, sorterade efter relevans.
Använd detta tool när användaren vill hitta en produkt eller frågar vad som finns.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Sökterm - namn, märke, eller kategori. Exempel: 'ica soja', 'laktosfri mjölk', 'cola zero'"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max antal resultat att returnera",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "hamta_produktdetaljer",
        "description": """Hämtar detaljerad information om en specifik produkt.
Inkluderar: namn, märke, kategori, pris, näringsvärden, ingredienser etc.
Använd detta när användaren vill veta mer om en produkt som redan nämnts.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "produkt_id": {
                    "type": "string",
                    "description": "Produktens unika ID (från sökresultat)"
                }
            },
            "required": ["produkt_id"]
        }
    },
    {
        "name": "hitta_liknande_produkter",
        "description": """Hittar liknande produkter som kan ersätta en viss produkt.
Användbart när en produkt är slut eller användaren vill jämföra alternativ.
Söker i samma kategori och prioriterar samma underkategori/märke.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "produkt_id": {
                    "type": "string",
                    "description": "ID för produkten att hitta alternativ till"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max antal alternativ",
                    "default": 5
                }
            },
            "required": ["produkt_id"]
        }
    },
    {
        "name": "hitta_nyttigare_alternativ",
        "description": """Hittar nyttigare alternativ till en produkt.
Jämför socker, fett och kalorier och föreslår produkter med bättre näringsvärden.
Använd när användaren vill äta nyttigare eller minska socker/fett.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "produkt_id": {
                    "type": "string",
                    "description": "ID för produkten att hitta nyttigare alternativ till"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max antal alternativ",
                    "default": 5
                }
            },
            "required": ["produkt_id"]
        }
    },
    {
        "name": "hamta_produktposition",
        "description": """Hämtar var i butiken en produkt finns.
Returnerar gång och ungefärlig position för navigering.
Använd när användaren frågar var en produkt finns eller vill navigera dit.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "produkt_id": {
                    "type": "string",
                    "description": "Produktens ID"
                }
            },
            "required": ["produkt_id"]
        }
    }
]


# ─────────────────────────────────────────────
# TOOL IMPLEMENTATION
# ─────────────────────────────────────────────

def _kör_tool(tool_name: str, tool_input: dict, produkt_db: dict = None) -> str:
    """
    Kör ett tool och returnera resultatet som JSON-sträng.
    
    Args:
        tool_name: Namnet på toolet
        tool_input: Input-parametrar
        produkt_db: Optional dict med produkt-positioner från databasen
    """
    sök = get_produkt_sök()
    
    if tool_name == "sok_produkter":
        resultat = sök.sök(
            query=tool_input["query"],
            limit=tool_input.get("limit", 5)
        )
        
        if not resultat:
            return json.dumps({
                "hittade": 0,
                "meddelande": "Inga produkter matchade sökningen."
            }, ensure_ascii=False)
        
        # Formatera för Claude
        produkter = []
        for p in resultat:
            produkter.append({
                "id": p.get("id"),
                "namn": p.get("namn"),
                "varumarke": p.get("varumarke"),
                "kategori": p.get("kategori"),
                "pris": p.get("pris"),
                "enhetspris": p.get("enhetspris"),
                "kampanjpris": p.get("kampanjpris"),
                "kampanjtext": p.get("kampanjtext"),
                "match_score": p.get("match_score")
            })
        
        return json.dumps({
            "hittade": len(produkter),
            "produkter": produkter
        }, ensure_ascii=False, indent=2)
    
    elif tool_name == "hamta_produktdetaljer":
        produkt = sök.hämta(tool_input["produkt_id"])
        
        if not produkt:
            return json.dumps({
                "error": "Produkten hittades inte",
                "produkt_id": tool_input["produkt_id"]
            }, ensure_ascii=False)
        
        # Returnera all tillgänglig info
        return json.dumps(produkt, ensure_ascii=False, indent=2)
    
    elif tool_name == "hitta_liknande_produkter":
        resultat = sök.hitta_liknande(
            produkt_id=tool_input["produkt_id"],
            limit=tool_input.get("limit", 5)
        )
        
        if not resultat:
            return json.dumps({
                "hittade": 0,
                "meddelande": "Inga liknande produkter hittades."
            }, ensure_ascii=False)
        
        produkter = []
        for p in resultat:
            produkter.append({
                "id": p.get("id"),
                "namn": p.get("namn"),
                "varumarke": p.get("varumarke"),
                "pris": p.get("pris"),
                "likhet_score": p.get("likhet_score")
            })
        
        return json.dumps({
            "hittade": len(produkter),
            "alternativ": produkter
        }, ensure_ascii=False, indent=2)
    
    elif tool_name == "hitta_nyttigare_alternativ":
        resultat = sök.hitta_nyttigare(
            produkt_id=tool_input["produkt_id"],
            limit=tool_input.get("limit", 5)
        )
        
        if not resultat:
            return json.dumps({
                "hittade": 0,
                "meddelande": "Inga nyttigare alternativ hittades (eller näringsvärden saknas)."
            }, ensure_ascii=False)
        
        produkter = []
        for p in resultat:
            produkter.append({
                "id": p.get("id"),
                "namn": p.get("namn"),
                "varumarke": p.get("varumarke"),
                "pris": p.get("pris"),
                "jämförelse": p.get("jämförelse", {})
            })
        
        return json.dumps({
            "hittade": len(produkter),
            "nyttigare_alternativ": produkter
        }, ensure_ascii=False, indent=2)
    
    elif tool_name == "hamta_produktposition":
        produkt_id = tool_input["produkt_id"]
        
        # Kolla om vi har position i databas
        if produkt_db and produkt_id in produkt_db:
            pos = produkt_db[produkt_id]
            return json.dumps({
                "namn": pos.get("visningsnamn", pos.get("namn")),
                "gång": pos.get("gång", "Okänd"),
                "position": {
                    "x": pos.get("x"),
                    "y": pos.get("y"),
                    "z": pos.get("z")
                },
                "hittad": True
            }, ensure_ascii=False, indent=2)
        
        # Annars, kolla produktdata
        sök = get_produkt_sök()
        produkt = sök.hämta(produkt_id)
        
        if produkt:
            # Kanske har produkten position i sig
            if produkt.get("gång") or produkt.get("x"):
                return json.dumps({
                    "namn": produkt.get("namn"),
                    "gång": produkt.get("gång", "Okänd"),
                    "position": {
                        "x": produkt.get("x"),
                        "y": produkt.get("y"),
                        "z": produkt.get("z")
                    },
                    "hittad": True
                }, ensure_ascii=False, indent=2)
            
            # Gissa baserat på kategori
            kategori = produkt.get("kategori", "")
            gång_gissning = _gissa_gång(kategori)
            
            return json.dumps({
                "namn": produkt.get("namn"),
                "gång": gång_gissning,
                "position": None,
                "hittad": False,
                "meddelande": f"Exakt position okänd, men {kategori} brukar finnas i {gång_gissning}"
            }, ensure_ascii=False, indent=2)
        
        return json.dumps({
            "error": "Produkten hittades inte",
            "hittad": False
        }, ensure_ascii=False)
    
    return json.dumps({"error": f"Okänt tool: {tool_name}"}, ensure_ascii=False)


def _gissa_gång(kategori: str) -> str:
    """Gissa vilken gång baserat på kategori."""
    kategori_till_gång = {
        "mejeri": "Mejeriavdelningen",
        "dryck": "Dryckesavdelningen",
        "bröd": "Bröd & Bageri",
        "frukt": "Frukt & Grönt",
        "grönsaker": "Frukt & Grönt",
        "kött": "Köttavdelningen",
        "fisk": "Fisk & Skaldjur",
        "frys": "Frysavdelningen",
        "godis": "Godis & Snacks",
        "hygien": "Hygien & Hushåll",
    }
    return kategori_till_gång.get(kategori.lower(), "Okänd avdelning")


# ─────────────────────────────────────────────
# SYSTEM PROMPT
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """Du är en hjälpsam och vänlig butiksassistent för ICA Maxi Bromma. Du hjälper kunder att:

1. **Hitta produkter** - Använd sok_produkter för att hitta varor. Kunder behöver inte skriva exakt rätt.
2. **Få produktinformation** - Berätta om näringsvärden, ingredienser, pris etc.
3. **Hitta alternativ** - Om något är slut, föreslå liknande produkter.
4. **Hitta nyttigare alternativ** - Föreslå produkter med mindre socker, fett eller kalorier.
5. **Navigera** - Berätta var produkter finns i butiken.

**Viktiga riktlinjer:**
- Svara ALLTID på svenska
- Var kortfattad men hjälpsam och vänlig
- När användaren nämner en produkt, sök först för att hitta rätt produkt-ID
- Om användaren bara skriver ett produktnamn (t.ex. "ica soja"), tolka det som en sökning
- Visa de viktigaste resultaten tydligt - namn, pris, och eventuellt märke
- Om du visar flera produkter, numrera dem så användaren kan referera till dem
- Kom ihåg konversationen - om användaren säger "den första" eller "berätta mer", referera till tidigare resultat

**Pris och veckans erbjudanden (din styrka — generella AI:n vet inte detta):**
- Varje produkt har `pris` (kr) och `enhetspris` (t.ex. "29 kr/kg"). Visa alltid priset.
- Är `kampanjpris` satt så är varan på REA just nu. Då gäller `kampanjpris` istället för
  ordinarie `pris`, och `kampanjtext` beskriver erbjudandet (t.ex. "29 kr/kg").
- Lyft fram kampanjer aktivt: visa ordinariepris överstruket-känsla, kampanjpriset, och
  hur mycket man sparar. Om kunden frågar "vad är på rea?" eller vill spara pengar,
  prioritera produkter med `kampanjpris`.

**Exempel på bra svar:**
Användare: "ica soja"
Du: Jag hittade dessa sojaprodukter:
1. **ICA Sojadryck Naturell** - 19,90 kr
2. **ICA Sojadryck Choklad** - 22,90 kr
Vill du veta mer om någon av dem?

Användare: "vad är billigt på frukt just nu?"
Du: *söker, prioriterar varor med kampanjpris*
Just nu på rea:
1. **Äpple Pink Lady 4-pack ICA** - 🔻 20,88 kr (ord. 27,23 kr) — 29 kr/kg
Vill du att jag visar var det finns i butiken?

Användare: "finns det något nyttigare än cola?"
Du: *söker först efter cola, sedan hitta nyttigare alternativ*
Jämfört med Coca-Cola (10,6g socker/100ml) kan jag rekommendera:
- **Coca-Cola Zero** - 0g socker
- **Pepsi Max** - 0g socker
Samma goda smak, men utan socker!"""


# ─────────────────────────────────────────────
# MAIN CHAT FUNCTION
# ─────────────────────────────────────────────

def chat(
    meddelande: str, 
    historik: Optional[list[dict]] = None,
    produkt_db: Optional[dict] = None
) -> dict:
    """
    Huvudfunktion för chat med Claude.
    
    Args:
        meddelande: Kundens meddelande
        historik: Tidigare meddelanden i konversationen
        produkt_db: Dict med produkt-positioner {produkt_id: {x, y, z, gång, ...}}
    
    Returns:
        {
            "svar": "Claude's svar",
            "historik": [...]  # Uppdaterad historik för nästa anrop
        }
    """
    if historik is None:
        historik = []
    
    # Lägg till användarens meddelande
    historik.append({
        "role": "user",
        "content": meddelande
    })
    
    # Anropa Claude
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=historik
    )
    
    # Hantera tool use i en loop
    while response.stop_reason == "tool_use":
        # Samla alla tool calls och results
        assistant_content = response.content
        tool_results = []
        
        for block in response.content:
            if block.type == "tool_use":
                # Kör toolet
                result = _kör_tool(block.name, block.input, produkt_db)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result
                })
        
        # Lägg till assistant-svar i historiken
        historik.append({
            "role": "assistant",
            "content": assistant_content
        })
        
        # Lägg till tool results
        historik.append({
            "role": "user",
            "content": tool_results
        })
        
        # Anropa Claude igen med tool-resultaten
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=historik
        )
    
    # Extrahera slutgiltigt textsvar
    svar_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            svar_text += block.text
    
    # Lägg till assistant-svar i historiken
    historik.append({
        "role": "assistant",
        "content": response.content
    })
    
    return {
        "svar": svar_text,
        "historik": historik
    }


# ─────────────────────────────────────────────
# SESSION MANAGEMENT
# ─────────────────────────────────────────────

class ChatSessionManager:
    """Hanterar chat-sessioner med historik."""
    
    def __init__(self):
        self.sessioner: dict[str, list] = {}
        self.produkt_db: dict = {}
    
    def ny_session(self) -> str:
        """Skapa ny session och returnera session_id."""
        import uuid
        session_id = str(uuid.uuid4())
        self.sessioner[session_id] = []
        return session_id
    
    def chat(self, session_id: str, meddelande: str) -> dict:
        """
        Skicka meddelande i en session.
        Skapar session om den inte finns.
        """
        if session_id not in self.sessioner:
            self.sessioner[session_id] = []
        
        historik = self.sessioner[session_id]
        
        resultat = chat(meddelande, historik, self.produkt_db)
        
        self.sessioner[session_id] = resultat["historik"]
        
        return {
            "svar": resultat["svar"],
            "session_id": session_id
        }
    
    def rensa_session(self, session_id: str):
        """Rensa en session."""
        if session_id in self.sessioner:
            del self.sessioner[session_id]
    
    def uppdatera_produkt_db(self, produkt_db: dict):
        """Uppdatera produkt-positioner."""
        self.produkt_db = produkt_db


# Global session manager
session_manager = ChatSessionManager()


def get_session_manager() -> ChatSessionManager:
    """Hämta global session manager."""
    return session_manager
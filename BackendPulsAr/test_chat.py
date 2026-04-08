#!/usr/bin/env python3
"""
test_chat.py - Testa Puls-AR chat lokalt
─────────────────────────────────────────────────────────────────
Kör: python test_chat.py

Kräver: ANTHROPIC_API_KEY miljövariabel
"""

import sys
import os

# Lägg till parent dir i path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_produkt_sok():
    """Testa produktsökning utan Claude."""
    print("\n" + "="*60)
    print("TEST: ProduktSök (utan Claude)")
    print("="*60)
    
    from core.produkt_sok import ProduktSök
    
    sök = ProduktSök("data/ica_produkter.json")
    
    # Test 1: Fuzzy sökning
    print("\n🔍 Sök: 'ica soja'")
    for p in sök.sök("ica soja", limit=3):
        print(f"   • {p['namn']} ({p['pris']} kr) - score: {p['match_score']}")
    
    print("\n🔍 Sök: 'cola zero'")
    for p in sök.sök("cola zero", limit=3):
        print(f"   • {p['namn']} ({p['pris']} kr) - score: {p['match_score']}")
    
    print("\n🔍 Sök: 'laktosfri'")
    for p in sök.sök("laktosfri", limit=3):
        print(f"   • {p['namn']} ({p['pris']} kr) - score: {p['match_score']}")
    
    print("\n🔍 Sök: 'havredryck'")
    for p in sök.sök("havredryck", limit=3):
        print(f"   • {p['namn']} ({p['pris']} kr) - score: {p['match_score']}")
    
    # Test 2: Liknande produkter
    print("\n🔄 Liknande produkter till Coca-Cola Original (100020):")
    for p in sök.hitta_liknande("100020", limit=3):
        print(f"   • {p['namn']} - likhet: {p['likhet_score']}")
    
    # Test 3: Nyttigare alternativ
    print("\n💚 Nyttigare alternativ till Coca-Cola Original (100020):")
    for p in sök.hitta_nyttigare("100020", limit=3):
        print(f"   • {p['namn']}")
        for k, v in p.get('jämförelse', {}).items():
            print(f"      {k}: {v}")
    
    print("\n✅ ProduktSök fungerar!")
    return True


def test_claude_chat():
    """Testa chat med Claude."""
    print("\n" + "="*60)
    print("TEST: Claude Chat (kräver ANTHROPIC_API_KEY)")
    print("="*60)
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("⚠️  ANTHROPIC_API_KEY saknas - hoppar över Claude-test")
        print("   Sätt med: export ANTHROPIC_API_KEY='din-nyckel'")
        return False
    
    from core.claude_assistant import chat
    
    # Test 1: Enkel sökning
    print("\n💬 Meddelande: 'ica soja'")
    resultat = chat("ica soja")
    print(f"🤖 Svar:\n{resultat['svar']}")
    
    # Test 2: Följdfråga (med historik)
    print("\n💬 Meddelande: 'vad kostar den?'")
    resultat = chat("vad kostar den?", resultat['historik'])
    print(f"🤖 Svar:\n{resultat['svar']}")
    
    # Test 3: Nyttigare alternativ
    print("\n💬 Meddelande: 'finns det något nyttigare alternativ till cola?'")
    resultat = chat("finns det något nyttigare alternativ till cola?")
    print(f"🤖 Svar:\n{resultat['svar']}")
    
    # Test 4: Position
    print("\n💬 Meddelande: 'var finns mjölk?'")
    resultat = chat("var finns mjölk?")
    print(f"🤖 Svar:\n{resultat['svar']}")
    
    print("\n✅ Claude Chat fungerar!")
    return True


def test_interactive():
    """Interaktiv chat för testning."""
    print("\n" + "="*60)
    print("INTERAKTIV CHAT (skriv 'quit' för att avsluta)")
    print("="*60)
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("⚠️  ANTHROPIC_API_KEY saknas")
        return
    
    from core.claude_assistant import get_session_manager
    
    session_manager = get_session_manager()
    session_id = session_manager.ny_session()
    
    print(f"\n🆔 Session: {session_id}")
    print("💬 Skriv ditt meddelande (eller 'quit' för att avsluta):\n")
    
    while True:
        try:
            meddelande = input("Du: ").strip()
            
            if meddelande.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Hejdå!")
                break
            
            if not meddelande:
                continue
            
            resultat = session_manager.chat(session_id, meddelande)
            print(f"\n🤖 Assistent: {resultat['svar']}\n")
            
        except KeyboardInterrupt:
            print("\n\n👋 Hejdå!")
            break
        except Exception as e:
            print(f"\n❌ Fel: {e}\n")


def main():
    """Huvudfunktion."""
    print("="*60)
    print("   PULS-AR CHAT TEST")
    print("="*60)
    
    # Test 1: Produktsökning (ingen API-nyckel krävs)
    test_produkt_sok()
    
    # Test 2: Claude chat (kräver API-nyckel)
    has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    
    if has_api_key:
        test_claude_chat()
        
        # Fråga om interaktiv test
        print("\n" + "-"*60)
        svar = input("Vill du testa interaktiv chat? (j/n): ").strip().lower()
        if svar in ['j', 'ja', 'y', 'yes']:
            test_interactive()
    else:
        print("\n⚠️  Sätt ANTHROPIC_API_KEY för att testa Claude-chat:")
        print("   export ANTHROPIC_API_KEY='din-api-nyckel'")
    
    print("\n" + "="*60)
    print("   TESTER KLARA!")
    print("="*60)


if __name__ == "__main__":
    main()
# Core module för Puls-AR chat

# Lazy imports - undviker att ladda anthropic om det inte behövs
def get_produkt_sök(*args, **kwargs):
    from core.produkt_sok import get_produkt_sök as _get
    return _get(*args, **kwargs)

def get_session_manager():
    from core.claude_assistant import get_session_manager as _get
    return _get()

def chat(*args, **kwargs):
    from core.claude_assistant import chat as _chat
    return _chat(*args, **kwargs)
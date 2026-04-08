"""
Puls-AR Server Startskript

Kör med: python run_server.py
"""
import uvicorn
import os

# === KONFIGURATION ===
HOST = "0.0.0.0"
PORT = 8000
WORKERS = 24  # Antal CPU-kärnor
RELOAD = False  # True för utveckling, False för produktion

if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════╗
║       PULS-AR SERVER                 ║
╠══════════════════════════════════════╣
║  Host:    {HOST:<24} ║
║  Port:    {PORT:<24} ║
║  Workers: {WORKERS:<24} ║
╚══════════════════════════════════════╝
""")
    
    uvicorn.run(
        "server:app",
        host=HOST,
        port=PORT,
        workers=WORKERS,
        reload=RELOAD,
    )
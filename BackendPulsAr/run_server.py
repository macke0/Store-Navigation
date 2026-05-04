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
    
    # Tysta polling-spam (lokalisering-senaste, bygg-status) i access-loggen.
    # SkipPollingFilter definieras i server.py.
    from copy import deepcopy
    log_config = deepcopy(uvicorn.config.LOGGING_CONFIG)
    log_config["filters"] = {
        "skip_polling": {"()": "server.SkipPollingFilter"}
    }
    log_config["handlers"]["access"]["filters"] = ["skip_polling"]

    uvicorn.run(
        "server:app",
        host=HOST,
        port=PORT,
        workers=WORKERS,
        reload=RELOAD,
        log_config=log_config,
    )
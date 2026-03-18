"""
start_vllm.py  –  Startar vLLM med Qwen2.5-VL på din 5090
─────────────────────────────────────────────────────────────────
Kör detta i en separat terminal innan du kör scanner.py

    python start_vllm.py

Första gången laddar den ner modellen (~15GB), sedan är den cachad.
Byt MODELL till 72B-versionen om du vill ha högre precision.
"""

import subprocess
import sys

# 7B passar på 24GB VRAM med bra marginal
# Byt till "Qwen/Qwen2.5-VL-72B-Instruct" för högre precision (kräver mer VRAM)
MODELL      = "Qwen/Qwen2.5-VL-7B-Instruct"
PORT        = 8001
GPU_MEMORY  = 0.90    # använd 90% av VRAM

print(f"🚀 Startar vLLM med {MODELL}...")
print(f"   Port: {PORT}")
print(f"   GPU-minne: {GPU_MEMORY*100:.0f}%")
print(f"   Första gången laddar den ner modellen (~15GB)\n")

cmd = [
    sys.executable, "-m", "vllm.entrypoints.openai.api_server",
    "--model",                  MODELL,
    "--port",                   str(PORT),
    "--gpu-memory-utilization", str(GPU_MEMORY),
    "--max-model-len",          "8192",
    "--dtype",                  "bfloat16",   # optimalt för RTX 5090
    "--trust-remote-code",
    "--limit-mm-per-prompt",    '{"image": 16}',  # max 16 bilder per anrop
]

print("Kör:", " ".join(cmd))
print("\n" + "="*55)
print("Vänta tills du ser: 'Application startup complete'")
print("Sedan kör du scanner.py i en annan terminal")
print("="*55 + "\n")

subprocess.run(cmd)
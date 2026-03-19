"""
qwen.py  –  Qwen/vLLM-anrop
"""
import base64
import requests
import cv2
import numpy as np

VLLM_URL = "http://127.0.0.1:8001/v1/chat/completions"
MODELL = "Qwen/Qwen2.5-VL-32B-Instruct-AWQ"

def img_till_base64(img: np.ndarray) -> str:
    h, w = img.shape[:2]
    if max(h, w) > 512:
        skala = 512 / max(h, w)
        img   = cv2.resize(img, (int(w*skala), int(h*skala)))
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return base64.b64encode(buf).decode("utf-8")

def fråga_qwen_vllm(img: np.ndarray, ruta_index: int = 0) -> str | None:
    b64 = img_till_base64(img)
    payload = {
        "model": MODELL,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
                },
                {
                    "type": "text",
                    "text": (
                        "This is a small section of a Swedish grocery store shelf. "
                        "Look ONLY at what text you can clearly read on product packaging. "
                        "Reply with the brand name and product name you can ACTUALLY SEE. "
                        "Do NOT guess or infer products you cannot clearly see. "
                        "If you cannot clearly read a product name, reply: OKÄND "
                        "Reply with ONLY the product name, nothing else. "
                        "Example: 'Felix Vitlökssås' or 'Heinz Garlic Sauce'"
                    )
                }
            ]
        }],
        "max_tokens": 50,
        "temperature": 0.0,
    }
    try:
        resp = requests.post(VLLM_URL, json=payload, timeout=30)
        resp.raise_for_status()
        svar = resp.json()["choices"][0]["message"]["content"].strip()
        if svar and "OKÄND" not in svar.upper():
            return svar
    except Exception as e:
        print(f"   ⚠️  vLLM-fel (ruta {ruta_index}): {e}")
    return None
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
                        "You are scanning a Swedish grocery store shelf. "
                        "FIRST: Look for shelf price tags at the bottom of shelves and read the product name from them. "
                        "SECOND: If no price tag is visible, read the product name from the packaging instead. "
                        "Reply with ONLY: 'Brand Productname' in Swedish. "
                        "Rules: "
                        "1. Always include the brand name "
                        "2. No markdown, no asterisks, no numbering "
                        "3. No explanations "
                        "4. If unclear, reply: OKÄND "
                        "Examples: 'ICA Kikärtor', 'Gyllenhammars Havregryn', 'Barilla Risoni', 'Felix Vitlökssås'"
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
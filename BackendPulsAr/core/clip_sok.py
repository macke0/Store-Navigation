import clip
import torch
import numpy as np
from PIL import Image
import csv

INDEX_FIL = "data/clip_index.npz"
CSV_FIL   = "data/produkter.csv"

print("🔍 Laddar CLIP-index...")
device = "cuda" if torch.cuda.is_available() else "cpu"
modell, preprocess = clip.load("ViT-B/32", device=device)

data     = np.load(INDEX_FIL)
vektorer = data["vektorer"]
ids      = data["ids"]

produkter = {}
with open(CSV_FIL, encoding="utf-8") as f:
    for rad in csv.DictReader(f):
        produkter[rad["id"]] = rad

print(f"   ✅ {len(ids)} produkter laddade\n")

def clip_matcha(img, topp: int = 3) -> list:
    """
    Tar en bild (numpy BGR-array eller PIL Image) och returnerar
    de topp-N mest liknande produkterna från indexet.
    """
    if isinstance(img, np.ndarray):
        img_rgb = img[:, :, ::-1]  # BGR → RGB
        pil_img = Image.fromarray(img_rgb)
    else:
        pil_img = img

    tensor = preprocess(pil_img).unsqueeze(0).to(device)
    with torch.no_grad():
        frågvektor = modell.encode_image(tensor)
        frågvektor = frågvektor / frågvektor.norm(dim=-1, keepdim=True)

    frågvektor_np = frågvektor.cpu().numpy()[0]
    likheter      = vektorer @ frågvektor_np
    topp_index    = np.argsort(likheter)[::-1][:topp]

    resultat = []
    for idx in topp_index:
        prod_id   = ids[idx]
        likhet    = float(likheter[idx])
        prod_info = produkter.get(prod_id, {})
        resultat.append({
            "id":           prod_id,
            "visningsnamn": prod_info.get("visningsnamn", prod_id),
            "varumarke":    prod_info.get("varumarke", ""),
            "kategori":     prod_info.get("kategori", ""),
            "likhet":       round(likhet, 3),
        })

    return resultat
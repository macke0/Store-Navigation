"""
OpenAI's clip model is used to connect images and text to one another. 
Torch is used for GPU usage.
Numpy is used for numerical operations. 
PIL is used for image manipulation.
csv is used to read the product database.
"""
import clip
import torch
import numpy as np
from PIL import Image
import csv

#Index contains vectors of all products in the store, so that we don't have to compute them every time.
#CSV contains product information.
INDEX_FIL = "data/clip_index.npz"
CSV_FIL   = "data/produkter.csv"
"""
Use GPU if available
ViT-B looks at the image in 32x32 patches and connects them to each other to understand the image.
Neural network is used to connect the image to the text.
Preprocess is used to resize, rotate the image etc.
"""
print("Laddar CLIP-index...")
device = "cuda" if torch.cuda.is_available() else "cpu"
modell, preprocess = clip.load("ViT-B/32", device=device)

#Each image is a 512 dimensional vector instead of an image. Products with similar vectors are similar to each other.
data     = np.load(INDEX_FIL)
vektorer = data["vektorer"]
ids      = data["ids"]

#Builds a dictionary of products
produkter = {}
with open(CSV_FIL, encoding="utf-8") as f:
    for rad in csv.DictReader(f):
        produkter[rad["id"]] = rad

print(f"   ✅ {len(ids)} produkter laddade\n")

#Takes an image and returns the top 3 most similar products from the index.
def clip_matcha(img, topp: int = 3) -> list:
    #OpenCV uses BGR, but clip uses RGB, converts if needed.
    if isinstance(img, np.ndarray):
        img_rgb = img[:, :, ::-1]  # BGR → RGB
        pil_img = Image.fromarray(img_rgb)
    else:
        pil_img = img
    """
    Preprocess tha imgea, resize it to 224x224, normalize it and convert it to a tensor.
    Add a batch dimension, run the image through the clip model to get the image vector.
    Normlize the image vector to one unit length so that we can compare it to the index vectors.
    """
    tensor = preprocess(pil_img).unsqueeze(0).to(device)
    with torch.no_grad():
        frågvektor = modell.encode_image(tensor)
        frågvektor = frågvektor / frågvektor.norm(dim=-1, keepdim=True)
    """
    Compare to all products in the store.
    Cos0 is a measure of similarity between two vectors.
    The dot product between the normalized vectors and the products vectors is the cosine similarity (1.0 is identical, 0.0 is orthogonal, -1.0 is opposite).
    """
    frågvektor_np = frågvektor.cpu().numpy()[0]
    likheter      = vektorer @ frågvektor_np
    topp_index    = np.argsort(likheter)[::-1][:topp]
    # Returns the products with the highest cosine similarity.
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
<<<<<<< HEAD
"""
OpenAI's clip model is used to connect images and text to one another. 
Torch is used for GPU usage.
Numpy is used for numerical operations. 
PIL is used for image manipulation.
csv is used to read the product database.
"""
=======
>>>>>>> 2e8d6f5679be7e0a69e69ec255a4174f6c0b60b7
import clip
import torch
import numpy as np
from PIL import Image
import csv

<<<<<<< HEAD
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
=======
INDEX_FIL = "data/clip_index.npz"
CSV_FIL   = "data/produkter.csv"

print("🔍 Laddar CLIP-index...")
device = "cuda" if torch.cuda.is_available() else "cpu"
modell, preprocess = clip.load("ViT-B/32", device=device)

>>>>>>> 2e8d6f5679be7e0a69e69ec255a4174f6c0b60b7
data     = np.load(INDEX_FIL)
vektorer = data["vektorer"]
ids      = data["ids"]

<<<<<<< HEAD
#Builds a dictionary of products
=======
>>>>>>> 2e8d6f5679be7e0a69e69ec255a4174f6c0b60b7
produkter = {}
with open(CSV_FIL, encoding="utf-8") as f:
    for rad in csv.DictReader(f):
        produkter[rad["id"]] = rad

print(f"   ✅ {len(ids)} produkter laddade\n")

<<<<<<< HEAD
#Takes an image and returns the top 3 most similar products from the index.
def clip_matcha(img, topp: int = 3) -> list:
    #OpenCV uses BGR, but clip uses RGB, converts if needed.
=======
def clip_matcha(img, topp: int = 3) -> list:
    """
    Tar en bild (numpy BGR-array eller PIL Image) och returnerar
    de topp-N mest liknande produkterna från indexet.
    """
>>>>>>> 2e8d6f5679be7e0a69e69ec255a4174f6c0b60b7
    if isinstance(img, np.ndarray):
        img_rgb = img[:, :, ::-1]  # BGR → RGB
        pil_img = Image.fromarray(img_rgb)
    else:
        pil_img = img
<<<<<<< HEAD
    """
    Preprocess tha imgea, resize it to 224x224, normalize it and convert it to a tensor.
    Add a batch dimension, run the image through the clip model to get the image vector.
    Normlize the image vector to one unit length so that we can compare it to the index vectors.
    """
=======

>>>>>>> 2e8d6f5679be7e0a69e69ec255a4174f6c0b60b7
    tensor = preprocess(pil_img).unsqueeze(0).to(device)
    with torch.no_grad():
        frågvektor = modell.encode_image(tensor)
        frågvektor = frågvektor / frågvektor.norm(dim=-1, keepdim=True)
<<<<<<< HEAD
    """
    Compare to all products in the store.
    Cos0 is a measure of similarity between two vectors.
    The dot product between the normalized vectors and the products vectors is the cosine similarity (1.0 is identical, 0.0 is orthogonal, -1.0 is opposite).
    """
    frågvektor_np = frågvektor.cpu().numpy()[0]
    likheter      = vektorer @ frågvektor_np
    topp_index    = np.argsort(likheter)[::-1][:topp]
    # Returns the products with the highest cosine similarity.
=======

    frågvektor_np = frågvektor.cpu().numpy()[0]
    likheter      = vektorer @ frågvektor_np
    topp_index    = np.argsort(likheter)[::-1][:topp]

>>>>>>> 2e8d6f5679be7e0a69e69ec255a4174f6c0b60b7
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
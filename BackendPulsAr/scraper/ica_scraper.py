"""
ica_scraper.py  –  Puls-AR ICA API-hämtare v3
─────────────────────────────────────────────────────────────────
Anropar ICA:s interna API direkt med cookies.
Ingen webbläsare behövs — bara cookies från Chrome DevTools.

Kör:
    python ica_scraper.py
    python ica_scraper.py --ingen-bilder
    python ica_scraper.py --max 200

OBS: Cookies måste uppdateras manuellt var ~24h.
     Kopiera från Chrome DevTools → Network → valfritt anrop till
     handlaprivatkund.ica.se → Request Headers → cookie
"""

import csv
import json
import os
import time
import argparse
import requests

# ─────────────────────────────────────────────
# KONFIGURATION
# ─────────────────────────────────────────────
BUTIK_ID    = "1015001"
BASE_URL = f"https://handlaprivatkund.ica.se/stores/{BUTIK_ID}/api/webproductpagews"
CSV_FIL     = "produkter.csv"
BILD_MAPP   = "bilder"
DELAY       = 0.3      # sekunder mellan anrop

# ─────────────────────────────────────────────
# COOKIES  ←  UPPDATERA HÄR NÄR DE GÅR UT
# Kopiera hela cookie-strängen från Chrome DevTools
# ─────────────────────────────────────────────
COOKIE_STRÄNG = """_vwo=ts~pXnulF9(MWZ)l~3%7C(2sg)m~3%241781731260%3A53.85326011%3A%3A%3A%3A%3A1782060736%3A1781856861%3A7(QR)w~D22527D2E39044F2070E2B9C5CBE84BAE%7C85a7feaccfba4ad43bc5d7aed8e78f9f(2sg)u~D9FC23E916FF0D5EC13E670DAF4FFE530(2sg)n~329476%3A2%3A%3A%3A%3A%3A513(5-)k~*(MR0)_vwo_consent~2%2C2%3A~(2yd; _vwo_sn=329476%3A2%3A%3A%3A%3A%3A513; FPID=FPID2.2.1kuPDlhaStNeppA8LfBpqJpVPJJTm%2BvXJxqfQvDs4ps%3D.1775914388; _ga_F7X050BLKH=GS2.1.s1782060737$o8$g1$t1782061280$j53$l0$h2003359797; _hjSession_1381022=eyJpZCI6IjE0NjIwOWJkLTFlN2ItNDk4OS1iYmNhLWJmMzgyYzBkMTBkMiIsImMiOjE3ODIwNjA3Mzc0MzksInMiOjAsInIiOjAsInNiIjowLCJzciI6MCwic2UiOjAsImZzIjowLCJzcCI6MH0=; OptanonConsent=isGpcEnabled=0&datestamp=Sun+Jun+21+2026+18%3A59%3A02+GMT%2B0200+(centraleuropeisk+sommartid)&version=202512.1.0&browserGpcFlag=0&isIABGlobal=false&identifierType=Cookie+Unique+Id&hosts=&consentId=50ce2732-066d-478e-bdfa-64b9b345a9a5&interactionCount=1&isAnonUser=0&landingPath=NotLandingPage&groups=C0001%3A1%2CC0003%3A1%2CC0002%3A1%2CC0004%3A1&iType=&intType=&crTime=1775914387705&geolocation=SE%3BAB&AwaitingReconsent=false; _fbp=fb.1.1781165441242.1997146106; _hjSessionUser_1381022=eyJpZCI6ImEyNzA4MWY5LWJkZWItNTQ0OS04MDc4LWY0OTc4NmVlNjJkZSIsImNyZWF0ZWQiOjE3NzU5MTQzODc3OTEsImV4aXN0aW5nIjp0cnVlfQ==; store-cookie=%7B%22storeName%22%3A%22Maxi%20ICA%20Stormarknad%20Bromma%22%2C%22storeId%22%3A%221015001%22%2C%22storeUrl%22%3A%22https%3A%2F%2Fwww.ica.se%2Fbutiker%2Fmaxi%2Fstockholm%2Fmaxi-ica-stormarknad-bromma-1015001%2F%22%2C%22accountNumber%22%3A%221015001%22%2C%22bmsId%22%3A%2217115%22%2C%22isOSP%22%3Atrue%7D; _ga=GA1.1.1590512816.1775914388; _vis_opt_s=3%7C; _vwo_consent=2%2C2%3A~; _vwo_ds=3%241781731260%3A53.85326011%3A%3A%3A%3A%3A1782060736%3A1781856861%3A7; .icase11=CfDJ8HfVp3nc9ztIo33rszTGSfcVyIeKZ4ombYnTjajNxG2LjZvyHA0DWtZIB2amOUvC0fOmYuPQGGEaV8bZjenz8jRRz7ZqfR0oW_WnBeQHt6grGkBGOpwMfRjygTCJHuCbadNejqqSxbUL_Qi8b1vzjEtrQJcoeOTFcb2q6WWVpX_B_hyVzx327dlH4pWbV6BuY0qHHQLHm0VOE8ty5mdeZkWYC16R61AfpJVI7a6ERjQ4kPr7C2HW4y26-Rz-bnucSon937ZCfD1xupY09uK4H_i-ccpcm70dtDWMFZyhAYcJfhqjXDjxwD93XlmFVQXAlfZ3iGX9T0Ch1BbcQyMmgQLUk5dlLwY85MRxC6xDwXTuaqvVGSUW8rrisMbLhs0-0uHpce_zH4zIou2cDLl5QSJXr7hBj1GQ81Bfo9_rKcjKtxNuIZmvb4vzQmFcOn96TGAHaNlxqPCNM0XFBFAZCkLEiQe1Z9yne4QkL-jS0J-iDuRjCxFBFFBcOGEbwHyxq04V0_X9xxlHLRe0bCJaMWUnCPC_4rjv_vXZu_jwADliS42JZmkzjkajDtYBinA-KoTth3VUDpcjupNnP214y4Ch9nc8WtuqQuhI4ifXfIkDkYq__rUbrp75p7s6kWg05A1Rb1m3u_tUKyqXjaIuNeRpSi-Hk4FBtDKtGSB9twA3C46AWDvL1BAep79QX6Jn6gio_GoH_AMisZ6kDTTnz8Ssjn2E4M18WwMZfSkdqvMPIksOncyrd6Tm8tAwy4zkMRtoN7TLSq6cS4ZU6VRD8TzlQ5D-HViqjLcDf_0cuHclUU6MNg2sLu-PBXoITdq25-oDuuNuqDDZ_fWo6XoYT5P6qvr35A-6lzK_MRukIMxUJJWnaKGLi-Mzl4WJ9XbZWYMkmajahO6cuGHI-Ifeqnjort223nMLkvwjaoHRJgdfwR8t_JQtuNd0SvTTIyONFfvMTPQeyM3yA8hQ9M6esu3PcfbaXuQe2BWcrRkrvkKw5fw0IU2cvq82Yefw1A-sD7qnpy93Vl6zUNp4O03VFPVbtd8S-UYig26ypgTtz3P1I_4PsCr1P5KAwvBMu5IfSQ; FPLC=WqYbc48OvmtVWn4HIF%2BQP8fxfqB%2FFSiU%2BCaA5ReaaMrQLxHmllsjH1tOnqsgUyQaZN%2FHqQoUfrlUg2rs5HlD6YAfhU3lwc3N4fFfI%2FZEN7pM%2BVeZrbRIJOQH695LTw%3D%3D; _vis_opt_test_cookie=1; _vwo_uuid=D9FC23E916FF0D5EC13E670DAF4FFE530; _vwo_uuid_v2=D22527D2E39044F2070E2B9C5CBE84BAE%7C85a7feaccfba4ad43bc5d7aed8e78f9f; AKA_A2=A; EPiStateMarker=true; SODA=eyJzb2RhX2lkIjoiMTc4MTgwNTM5NTgyOC43NzgxNTg2In0%3D; roc_hdr=26; eupubconsent-v2=CQfM0lgQfM0lgAcABBSVCRFwAPLAAAAAAChQF5wAQF5gAAAECQAQF5joAIC8yUAEBeZSACAvMAAA.flgAAAAAAAAA.IF5wAQF5gAAA; thSessionId=Tecu1n36nlxofLxQy/oWvbPiMRYlj2Zu3N5C/l504wf57htBedL65nq6LGAKZ+pX"""

HEADERS = {
    "User-Agent":                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Accept":                        "application/json; charset=utf-8",
    "Accept-Encoding":               "gzip, deflate, br, zstd",
    "Accept-Language":               "sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7",
    "client-route-id":               "57855c8d-0cd9-4480-9597-b0fc87963f19",
    "contentexperienceuserid":       "1e7bce51-ccf1-49a4-badd-c376ed4b43b3",
    "ecom-request-source":           "web",
    "ecom-request-source-version":   "2.0.0-2026-03-16-09h40m20s-cfb8c0e2",
    "page-view-id":                  "7def3735-e37f-4af7-9858-44438810dd95",
    "Referer":                       "https://handlaprivatkund.ica.se/stores/1015001",
    "sec-fetch-dest":                "empty",
    "sec-fetch-mode":                "cors",
    "sec-fetch-site":                "same-origin",
}

# ─────────────────────────────────────────────
# HJÄLPFUNKTIONER
# ─────────────────────────────────────────────

def parse_cookies(cookie_sträng: str) -> dict:
    cookies = {}
    for part in cookie_sträng.strip().split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies

def slug(text: str) -> str:
    ersätt = {"å": "a", "ä": "a", "ö": "o", "Å": "A", "Ä": "A", "Ö": "O"}
    t = text.lower().strip()
    for k, v in ersätt.items():
        t = t.replace(k, v)
    return "".join(c if c.isalnum() else "-" for c in t).strip("-")

def ladda_ner_bild(url: str, produkt_id: str) -> str:
    if not url:
        return ""
    os.makedirs(BILD_MAPP, exist_ok=True)
    filnamn = os.path.join(BILD_MAPP, f"{produkt_id}.jpg")
    if os.path.exists(filnamn):
        return filnamn
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            with open(filnamn, "wb") as f:
                f.write(r.content)
            return filnamn
    except Exception:
        pass
    return ""

def spara_csv(produkter: list[dict]):
    fält = ["id", "visningsnamn", "varumarke", "kategori", "avdelning",
            "pris", "enhetspris", "kampanjpris", "kampanjtext",
            "bild_url", "bild_lokal", "taggar"]
    ny = not os.path.exists(CSV_FIL)
    with open(CSV_FIL, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fält)
        if ny:
            writer.writeheader()
        for p in produkter:
            writer.writerow({k: p.get(k, "") for k in fält})


# ─────────────────────────────────────────────
# API-ANROP
# ─────────────────────────────────────────────

def api_get(endpoint: str, params: dict, cookies: dict) -> dict | list | None:
    try:
        for försök in range(5):
            resp = requests.get(
                f"{BASE_URL}/{endpoint}",
                params=params,
                cookies=cookies,
                headers=HEADERS,
                timeout=15,
            )
            print(f"   DEBUG: {resp.status_code} försök {försök+1}")
            if resp.status_code == 200:
                data = resp.json()
                print(f"   DEBUG: svar typ={type(data).__name__} nycklar={list(data.keys()) if isinstance(data, dict) else 'lista'}")
                return data
            elif resp.status_code == 202:
                time.sleep(1)
                continue
            else:
                print(f"   ⚠️  {resp.status_code} för {endpoint}")
                return None
    except Exception as e:
        print(f"   ⚠️  Fel: {e}")
    return None

# ─────────────────────────────────────────────
# KATEGORIER
# ─────────────────────────────────────────────

def hämta_kategorier(cookies: dict) -> list[dict]:
    data = api_get("v1/categories", {"decoration": "false", "categoryDepth": "4"}, cookies)
    if not data:
        return []

    kategorier = []

    def platta_ut(noder: list, förälder: str = ""):
        for nod in noder:
            namn  = nod.get("name", "").strip()
            kid   = nod.get("categoryId", "")
            barn  = nod.get("childCategories", [])
            full  = f"{förälder} > {namn}" if förälder else namn

            # Spara lövnoder (utan barn) — det är dessa som har produkter
            if namn and kid and not barn:
                kategorier.append({"id": kid, "namn": full})

            if barn:
                platta_ut(barn, full)

    if isinstance(data, list):
        platta_ut(data)
    elif isinstance(data, dict):
        platta_ut(data.get("categories", [data]))

    return kategorier


# ─────────────────────────────────────────────
# PRODUKTER
# ─────────────────────────────────────────────

# Sätts True när vi dumpat råexempel en gång (för --dump-rå).
_DUMPAT = False
# Sätts True när vi dumpat ett kampanj-exempel (produkt med extra-nyckel).
_PROMO_DUMPAT = False

# Standardnycklar på en produkt UTAN kampanj (från rå_exempel.json).
# En rabatterad produkt bär extra nycklar utöver dessa → då dumpar vi schemat.
_BASELINE_PRODUKT_NYCKLAR = {
    "alcohol", "alternatives", "available", "basketLines", "catchweight",
    "categoryPath", "countryOfOrigin", "iconAttributes", "icons", "image",
    "imageConfig", "imageIds", "imagePaths", "images", "isInCurrentCatalog",
    "isInShoppingList", "isNew", "isVerifiedPurchase", "maxQuantityReached",
    "name", "packSizeDescription", "price", "productId", "quantityInBasket",
    "retailerFinancingPlanIds", "retailerProductId", "taxCodesDisplayNames",
    "timeRestricted", "type", "unitPrice",
}


def hämta_produkter(kategori_id: str, kategori_namn: str,
                    cookies: dict, hämta_bilder: bool,
                    dump_rå: bool = False) -> list[dict]:
    global _DUMPAT
    data = api_get("v5/product-pages", {
        "categoryId":    kategori_id,
        "decoratedOnly": "true",
        "limit":         300,
        "tag":           ["web", "category-item"],
    }, cookies)
    if not data:
        return []

    if isinstance(data, dict):
        print(f"   DEBUG: totalProducts={data.get('totalProducts')} "
              f"productGroups={len(data.get('productGroups') or [])}")

    # Dumpa hela råsvaret en gång — men bara för en kategori som faktiskt har
    # produkter — så vi ser ICA:s exakta schema (pris, kampanj/erbjudande, lager).
    if (dump_rå and not _DUMPAT and isinstance(data, dict)
            and (data.get("totalProducts") or data.get("productGroups"))):
        with open("rå_exempel.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        _DUMPAT = True
        print("   📝 Dumpade hela råsvaret till rå_exempel.json")

    # Extrahera produkter ur API-svaret
    rå = []
    if isinstance(data, list):
        rå = data
    elif isinstance(data, dict):
        rå = data.get("products") or data.get("items") or []
        # v6 wrapper: produkter ligger i pages[].products
        if not rå:
            for page in data.get("pages", []):
                rå.extend(page.get("products", []))
        # nytt schema: produkter ligger i productGroups[].products[].product
        if not rå:
            for grupp in data.get("productGroups", []):
                for it in grupp.get("products") or grupp.get("items") or []:
                    rå.append(it.get("product") or it)

    # Kampanj-upptäckt: dumpa första produkt som bär en icke-standardnyckel
    # (t.ex. promotions/offers/splitPrice) så vi ser veckokampanj-schemat på
    # en faktiskt rabatterad vara. Standardvaror saknar dessa fält.
    global _PROMO_DUMPAT
    if dump_rå and not _PROMO_DUMPAT:
        for p in rå:
            extra = set(p.keys()) - _BASELINE_PRODUKT_NYCKLAR
            if extra:
                with open("promo_exempel.json", "w", encoding="utf-8") as f:
                    json.dump({"extra_nycklar": sorted(extra), "produkt": p},
                              f, ensure_ascii=False, indent=2)
                _PROMO_DUMPAT = True
                print(f"   📝 Kampanj-schema dumpat (extra-nycklar: {sorted(extra)})")
                break

    produkter = []
    for prod in rå:
        try:
            namn  = (prod.get("name") or prod.get("title") or "").strip()
            märke = (prod.get("brand") or prod.get("brandName") or "").strip()

            # Pris: nytt schema {"amount": "21.60", "currency": "SEK"},
            # äldre fallback {"current": ...}.
            pris_obj = prod.get("price") or {}
            pris     = str(pris_obj.get("amount") or pris_obj.get("current") or
                           pris_obj.get("price") or "")

            # Jämförpris: unitPrice = {"price": {"amount": ...}, "unit": "fop.price.per.kg"}
            up        = prod.get("unitPrice") or {}
            up_pris   = up.get("price") if isinstance(up.get("price"), dict) else up
            up_belopp = (up_pris or {}).get("amount") or ""
            up_enhet  = (up.get("unit") or "").split(".")[-1]   # "fop.price.per.kg" → "kg"
            enhetspris = f"{up_belopp} kr/{up_enhet}".strip() if up_belopp else \
                         str(pris_obj.get("comparison") or "")

            # Kampanj (veckans erbjudande): promoPrice = rabatterat pris,
            # promotions[0].description = kampanjtext (t.ex. "29 kr/kg").
            kampanjpris = str((prod.get("promoPrice") or {}).get("amount") or "")
            promotions  = prod.get("promotions") or []
            kampanjtext = (promotions[0].get("description") or "").strip() \
                if promotions and isinstance(promotions[0], dict) else ""

            # Bild: image.src (ren URL) → images[0].src → imagePaths[0]
            bild_url = ""
            if isinstance(prod.get("image"), dict):
                bild_url = prod["image"].get("src", "")
            if not bild_url:
                bilder = prod.get("images") or []
                if isinstance(bilder, list) and bilder and isinstance(bilder[0], dict):
                    bild_url = bilder[0].get("src", "")
            if not bild_url:
                vägar = prod.get("imagePaths") or []
                if isinstance(vägar, list) and vägar:
                    bas = str(vägar[0])
                    bild_url = f"{bas}/300x300.jpg" if "images-v3" in bas else bas

            if not namn:
                continue

            fullt_namn = f"{märke} {namn}".strip() if märke and märke.lower() not in namn.lower() else namn
            prod_id    = slug(fullt_namn)
            delar       = kategori_namn.split(" > ")
            lövkategori = delar[-1]
            avdelning   = delar[0]

            taggar = list(set(filter(None, [
                lövkategori.lower(),
                märke.lower(),
                namn.lower(),
            ])))

            produkt = {
                "id":           prod_id,
                "visningsnamn": fullt_namn,
                "varumarke":    märke,
                "kategori":     lövkategori,
                "avdelning":    avdelning,
                "pris":         pris,
                "enhetspris":   enhetspris,
                "kampanjpris":  kampanjpris,
                "kampanjtext":  kampanjtext,
                "bild_url":     bild_url,
                "bild_lokal":   "",
                "taggar":       ",".join(taggar),
            }

            if hämta_bilder and bild_url:
                produkt["bild_lokal"] = ladda_ner_bild(bild_url, prod_id)

            produkter.append(produkt)

        except Exception:
            continue

    return produkter


# ─────────────────────────────────────────────
# HUVUDFUNKTION
# ─────────────────────────────────────────────

def scrapa_ica(max_produkter: int | None, hämta_bilder: bool, dump_rå: bool = False):
    cookies = parse_cookies(COOKIE_STRÄNG)
    print(f"🍪 {len(cookies)} cookies laddade\n")

    # Rensa gammal CSV
    if os.path.exists(CSV_FIL):
        os.remove(CSV_FIL)
        print(f"🗑️  Raderade gammal {CSV_FIL}\n")

    # Kategorier
    print("📂 Hämtar kategorier...")
    kategorier = hämta_kategorier(cookies)
    print(f"   {len(kategorier)} lövkategorier hittade\n")

    if not kategorier:
        print("❌ Inga kategorier — cookies kan ha gått ut")
        print("   Kopiera nya cookies från Chrome DevTools och uppdatera COOKIE_STRÄNG i scriptet")
        return

    # Produkter
    print("🛒 Hämtar produkter...\n")
    totalt = 0
    sparade_ids = set()   # undvik dubletter

    for kat in kategorier:
        if max_produkter and totalt >= max_produkter:
            break

        produkter = hämta_produkter(kat["id"], kat["namn"], cookies, hämta_bilder, dump_rå)

        # Filtrera bort dubletter (samma produkt i flera kategorier)
        nya = [p for p in produkter if p["id"] not in sparade_ids]
        for p in nya:
            sparade_ids.add(p["id"])

        if max_produkter:
            kvar = max_produkter - totalt
            nya  = nya[:kvar]

        if nya:
            spara_csv(nya)
            totalt += len(nya)
            print(f"   ✅ {kat['namn'].split(' > ')[-1]:30} {len(nya):4} produkter  (totalt: {totalt})")
        else:
            print(f"   ⚪ {kat['namn'].split(' > ')[-1]:30} inga produkter")

        time.sleep(DELAY)

    print(f"\n{'='*55}")
    print(f"✅ KLAR! {totalt} produkter sparade till '{CSV_FIL}'")
    if hämta_bilder:
        print(f"   Bilder i '{BILD_MAPP}/'")
    print(f"\nNästa steg:")
    print(f"   python scanner.py hylla.jpg")
    print(f"{'='*55}")


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ICA API Produkthämtare v3")
    parser.add_argument("--max", type=int, default=None,
                        help="Max antal produkter (default: alla)")
    parser.add_argument("--ingen-bilder", action="store_true",
                        help="Hoppa över bildnedladdning")
    parser.add_argument("--dump-rå", dest="dump_rå", action="store_true",
                        help="Spara de första råa produkt-objekten till rå_exempel.json")
    args = parser.parse_args()

    scrapa_ica(
        max_produkter=args.max,
        hämta_bilder=not args.ingen_bilder,
        dump_rå=args.dump_rå,
    )
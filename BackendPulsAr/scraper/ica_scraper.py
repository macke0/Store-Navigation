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
COOKIE_STRÄNG = """OptanonAlertBoxClosed=2026-03-08T20:17:10.291Z; eupubconsent-v2=CQgvstgQgvstgAcABBSVCVFwAPLAAAAAAChQF5wAQF5gAAAECQAQF5joAIC8yUAEBeZSACAvMAAA.flgAAAAAAAAA.IF5wAQF5gAAA; _vwo_uuid_v2=D3C58E303D22118F6A4093D0186019EC5|507d17ea01114d9130029eb7e4970f3a; _vwo_uuid=D3C58E303D22118F6A4093D0186019EC5; FPID=FPID2.2.tAzjB14vNGyktjiyCzMLEtKcm6O8TgS7qEgkKt%2FhCaQ%3D.1773001029; _gtmeec=e30%3D; _fbp=fb.1.1773001050323.1302121969; _hjSessionUser_1381022=eyJpZCI6Ijk2YjM5NzI1LWI4YWQtNWQ4OS1iNjExLTJlNjMzMmZkNjk4MyIsImNyZWF0ZWQiOjE3NzMwMDEwNDk5NDcsImV4aXN0aW5nIjp0cnVlfQ==; store-cookie=%7B%22storeName%22%3A%22Maxi%20ICA%20Stormarknad%20Bromma%22%2C%22storeId%22%3A%221015001%22%2C%22accountNumber%22%3A%221015001%22%2C%22isOSP%22%3Atrue%7D; _vwo_ds=3%241773001030%3A81.10391067%3A%3A%3A%3A%3A1773682274%3A1773001030%3A2; _vis_opt_s=2%7C; _vis_opt_test_cookie=1; _hjSession_1381022=eyJpZCI6IjZhM2I1YjU3LWVlZDItNDQ2ZS1iOTU0LTg0M2QwNTQyYjljNyIsImMiOjE3NzM2ODIyNzczNjYsInMiOjAsInIiOjAsInNiIjowLCJzciI6MCwic2UiOjAsImZzIjowLCJzcCI6MH0=; FPLC=WH9I0opJ3TLhqLTC5cUgfjakRhdfmO3x0IK%2BmjwP3zOnUvlsI4taHVfwfz%2BVS%2B7DwHCjpgPVsqRPmZbfYUKlPIjJo%2FklJzYFHOTFeM%2FF0AmM%2F%2B9PDZX%2BBvy5YlaKEA%3D%3D; _gid=GA1.2.1683562037.1773682277; _vwo_sn=681244%3A3%3A%3A%3A%3A%3A162; OptanonConsent=isGpcEnabled=0&datestamp=Mon+Mar+16+2026+18%3A34%3A01+GMT%2B0100+(Central+European+Standard+Time)&version=202512.1.0&browserGpcFlag=0&isIABGlobal=false&identifierType=Cookie+Unique+Id&hosts=&consentId=62091b81-0dfa-4c9a-a490-04ba09aa2e7f&interactionCount=1&isAnonUser=1&landingPath=NotLandingPage&groups=C0001%3A1%2CC0003%3A1%2CC0002%3A1%2CC0004%3A1&iType=1&intType=1&crTime=1773001030461&geolocation=SE%3BAB&AwaitingReconsent=false; _ga_F7X050BLKH=GS2.1.s1773682277$o4$g1$t1773682442$j22$l0$h1576197844; _ga=GA1.1.1137945645.1773001029"""

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
    fält = ["id", "visningsnamn", "varumarke", "kategori",
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
            lövkategori = kategori_namn.split(" > ")[-1]

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
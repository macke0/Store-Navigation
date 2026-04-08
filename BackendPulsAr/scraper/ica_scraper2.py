"""
ica_scraper2.py  –  Playwright-baserad ICA-scraper
"""

import json
import csv
import os
import asyncio
import argparse
import requests
from playwright.async_api import async_playwright

BUTIK_ID  = "1015001"
BILD_MAPP = "bilder"
CSV_FIL   = "produkter.csv"

def slug(text: str) -> str:
    ersätt = {"å": "a", "ä": "a", "ö": "o", "Å": "A", "Ä": "A", "Ö": "O"}
    t = text.lower().strip()
    for k, v in ersätt.items():
        t = t.replace(k, v)
    return "".join(c if c.isalnum() else "-" for c in t).strip("-")

def ladda_ner_bilder():
    print("\n📸 Laddar ner produktbilder...")
    os.makedirs(BILD_MAPP, exist_ok=True)

    with open(CSV_FIL, encoding="utf-8") as f:
        produkter = list(csv.DictReader(f))

    for i, prod in enumerate(produkter):
        url     = prod.get("bild_url", "")
        prod_id = prod.get("id", "")
        if not url or not prod_id:
            continue

        filnamn = os.path.join(BILD_MAPP, f"{prod_id}.jpg")
        if os.path.exists(filnamn):
            continue

        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(filnamn, "wb") as f:
                    f.write(r.content)
        except:
            pass

        if i % 100 == 0:
            print(f"   {i}/{len(produkter)} bilder nedladdade")

    print(f"✅ Bilder sparade i {BILD_MAPP}/")

async def scrapa():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page    = await context.new_page()

        print("🌐 Öppnar ICA...")
        await page.goto(f"https://handlaprivatkund.ica.se/stores/{BUTIK_ID}")
        await page.wait_for_load_state("networkidle")
        print("✅ Sida laddad")

        print("📂 Hämtar kategorier...")
        kat_svar = await page.evaluate("""
            async () => {
                const r = await fetch('/stores/1015001/api/webproductpagews/v1/categories?decoration=false&categoryDepth=4');
                return await r.json();
            }
        """)

        kategorier = []
        def platta_ut(noder, förälder=""):
            for nod in noder:
                namn = nod.get("name", "").strip()
                kid  = nod.get("categoryId", "")
                barn = nod.get("childCategories", [])
                full = f"{förälder} > {namn}" if förälder else namn
                if namn and kid and not barn:
                    kategorier.append({"id": kid, "namn": full})
                if barn:
                    platta_ut(barn, full)

        if isinstance(kat_svar, list):
            platta_ut(kat_svar)
        print(f"   {len(kategorier)} kategorier\n")

        produkter_alla = []
        sparade_ids    = set()

        for i, kat in enumerate(kategorier):
            try:
                svar = await page.evaluate(f"""
                    async () => {{
                        const r = await fetch('/stores/1015001/api/webproductpagews/v5/product-pages?decoratedOnly=true&limit=300&tag=web&tag=lohp&categoryId={kat["id"]}');
                        return await r.json();
                    }}
                """)

                rå = []
                for grupp in svar.get("productGroups", []):
                    for prod_wrapper in grupp.get("products", []):
                        prod = prod_wrapper.get("product", prod_wrapper)
                        rå.append(prod)
                if i == 0 and rå:
                    print(f"   DEBUG första produkt: {str(rå[0])[:800]}")

                nya = []
                for prod in rå:
                    namn  = (prod.get("name") or prod.get("title") or "").strip()
                    märke = (prod.get("brand") or prod.get("brandName") or "").strip()
                    if not namn:
                        continue

                    bild_url = ""
                    bilder = prod.get("images") or []
                    if isinstance(bilder, list) and bilder:
                        bild_url = bilder[0].get("src", "")

                    # Fallback till imageConfig om images saknar src
                    if not bild_url:
                        image_config = prod.get("imageConfig", {})
                        bild_url = image_config.get("image", {}).get("src", "")

                    fullt_namn = f"{märke} {namn}".strip() if märke and märke.lower() not in namn.lower() else namn
                    prod_id    = slug(fullt_namn)

                    if prod_id in sparade_ids:
                        continue
                    sparade_ids.add(prod_id)

                    nya.append({
                        "id":           prod_id,
                        "visningsnamn": fullt_namn,
                        "varumarke":    märke,
                        "kategori":     kat["namn"].split(" > ")[-1],
                        "bild_url":     bild_url,
                        "taggar":       ",".join(filter(None, [märke.lower(), namn.lower()])),
                    })

                if nya:
                    produkter_alla.extend(nya)
                    print(f"   ✅ {kat['namn'].split(' > ')[-1]:30} {len(nya):4} produkter (totalt: {len(produkter_alla)})")
                else:
                    print(f"   ⚪ {kat['namn'].split(' > ')[-1]:30} inga produkter")

            except Exception as e:
                print(f"   ⚠️  {kat['namn']}: {e}")

        with open(CSV_FIL, "w", newline="", encoding="utf-8") as f:
            fält = ["id", "visningsnamn", "varumarke", "kategori", "bild_url", "taggar"]
            writer = csv.DictWriter(f, fieldnames=fält)
            writer.writeheader()
            writer.writerows(produkter_alla)

        print(f"\n✅ {len(produkter_alla)} produkter sparade till {CSV_FIL}")
        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--bara-bilder", action="store_true",
                        help="Hoppa över scraping, bara ladda ner bilder")
    args = parser.parse_args()

    if args.bara_bilder:
        ladda_ner_bilder()
    else:
        asyncio.run(scrapa())
        ladda_ner_bilder()
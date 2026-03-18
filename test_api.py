import asyncio
import json
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page    = await browser.new_page()
        
        await page.goto("https://handlaprivatkund.ica.se/stores/1015001")
        await page.wait_for_load_state("networkidle")
        
        svar = await page.evaluate("""
            async () => {
                const r = await fetch('/stores/1015001/api/webproductpagews/v5/product-pages?decoratedOnly=true&limit=3&tag=web&tag=lohp');
                return await r.json();
            }
        """)
        
        with open("debug_svar.json", "w", encoding="utf-8") as f:
            json.dump(svar, f, ensure_ascii=False, indent=2)
        
        await browser.close()

asyncio.run(test())
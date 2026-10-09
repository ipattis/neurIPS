"""End-to-end check of "Where does my paper fit?" (downloads the ~570 MB browser model once).
Usage: python tests/fit_test.py http://localhost:8000 "<title. abstract>" "<expected title substring>"."""
import asyncio, sys
from playwright.async_api import async_playwright
BASE, TEXT, EXPECT = sys.argv[1], sys.argv[2], sys.argv[3]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1500, "height": 950}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await pg.goto(f"{BASE}/index.html"); await pg.wait_for_timeout(10000)
        print("colormaps:", await pg.evaluate("[...document.querySelectorAll('.color-map-option, .color-map-dropdown [data-field], .color-map-list li')].map(e => e.textContent.trim()).slice(0, 12)"))
        await pg.click("#nx-fit-btn"); await pg.fill("#fit-text", TEXT); await pg.click("#fit-go")
        await pg.wait_for_function("document.querySelectorAll('#fit-results li').length > 0 || /Couldn't/.test(document.getElementById('fit-status').textContent)", timeout=900000, polling=2000)
        results = await pg.locator("#fit-results li").all_inner_texts()
        print("status:", await pg.inner_text("#fit-status"))
        print("top results:", [r[:90] for r in results[:5]])
        print("expected paper ranked:", next((i + 1 for i, r in enumerate(results) if EXPECT in r), "not in top 12"))
        print("highlighted:", await pg.evaluate("datamap.getSelectedIndices().size"),
              "pin layer:", await pg.evaluate("datamap.layers.some(l => l.id === 'my-paper-pin')"))
        await pg.wait_for_timeout(1500); await pg.screenshot(path="/tmp/ui_fit.png")
        print("errors:", [e for e in errs if "Font" not in e])
        await b.close()
asyncio.run(main())

"""Headless check of the Trends panel: python tests/trends_test.py http://localhost:8000"""
import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1500, "height": 950}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await pg.goto(f"{sys.argv[1]}/index.html"); await pg.wait_for_timeout(10000)
        await pg.click("#nx-trends-btn"); await pg.wait_for_timeout(300)
        print("levels:", await pg.locator("#trends-layers button").all_inner_texts())
        rows = await pg.locator(".trend-row .trend-head").all_inner_texts()
        print("top growing:", [r.replace("\n", " ") for r in rows[:5]])
        await pg.click("#trends-sort button[data-sort='down']"); await pg.wait_for_timeout(200)
        print("shrinking:", [r.replace("\n", " ") for r in (await pg.locator(".trend-row .trend-head").all_inner_texts())[:3]])
        await pg.click("#trends-sort button[data-sort='up']"); await pg.click(".trend-row >> nth=0"); await pg.wait_for_timeout(1500)
        print("note:", (await pg.inner_text(".trend-row.open .trend-note"))[:200])
        print("highlighted papers:", await pg.evaluate("datamap.getSelectedIndices().size"))
        await pg.screenshot(path="/tmp/ui_trends.png")
        await pg.click("#trends-layers button >> nth=0"); await pg.wait_for_timeout(200)
        print("broad areas:", [r.replace("\n", " ") for r in await pg.locator(".trend-row .trend-head").all_inner_texts()])
        print("errors:", [e for e in errs if "Font" not in e]); await b.close()
asyncio.run(main())

"""Headless UI check: python tests/ui_test.py http://localhost:8000 (serve site/ first: python -m http.server -d site 8000).
Exercises the toolbar, year filter, detail panel, agenda + .ics export, view switching and a mobile viewport;
screenshots go to /tmp/ui*.png."""
import asyncio, sys
from playwright.async_api import async_playwright
BASE = sys.argv[1]
async def find_point(pg):
    for x in range(560, 1100, 30):
        for y in range(300, 760, 30):
            await pg.mouse.click(x, y); await pg.wait_for_timeout(80)
            if await pg.evaluate("!document.getElementById('paper-panel').classList.contains('hidden')"):
                return x, y
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1500, "height": 950}, accept_downloads=True)
        pg = await ctx.new_page(); errs = []
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append("PAGEERROR " + str(e)))
        await pg.goto(f"{BASE}/index.html"); await pg.wait_for_timeout(12000)
        await pg.screenshot(path="/tmp/ui1.png")
        print("nav views:", await pg.locator("#nx-views a").all_inner_texts(), "years:", await pg.locator("#nx-years button").all_inner_texts())
        await pg.click("#nx-years button[data-year='2025']"); await pg.wait_for_timeout(500)
        print("year filter selected:", await pg.evaluate("datamap.getSelectedIndices().size"))
        await pg.click("#nx-years button[data-year='All']"); await pg.wait_for_timeout(300)
        pt = await find_point(pg); print("panel opened at", pt)
        print("panel text:", (await pg.inner_text("#paper-panel"))[:400].replace("\n", " | "))
        await pg.click("#paper-agenda"); await pg.wait_for_timeout(200)
        print("agenda btn:", await pg.inner_text("#paper-agenda"), "count:", await pg.inner_text("#nx-agenda-count"))
        await pg.screenshot(path="/tmp/ui2.png")
        await pg.click("#nx-agenda-btn"); await pg.wait_for_timeout(300)
        print("agenda:", (await pg.inner_text("#agenda-list"))[:200].replace("\n", " | "))
        async with pg.expect_download() as dl:
            await pg.click("#agenda-ics")
        d = await dl.value; path = await d.path(); print("ics:", open(path).read()[:400].replace("\r\n", " / "))
        await pg.screenshot(path="/tmp/ui3.png")
        await pg.click("#nx-views a:has-text('By method')"); await pg.wait_for_timeout(9000)
        print("method page agenda count (shared storage):", await pg.inner_text("#nx-agenda-count"), "active:", await pg.inner_text("#nx-views a.active"))
        m = await b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        m.on("pageerror", lambda e: errs.append("MOBILE " + str(e)))
        await m.goto(f"{BASE}/index.html"); await m.wait_for_timeout(12000)
        await m.screenshot(path="/tmp/ui_mobile.png")
        print("errors:", errs[:8])
        await b.close()
asyncio.run(main())

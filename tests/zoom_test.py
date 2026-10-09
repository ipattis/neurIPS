"""Zoom controls + no table downloads: python tests/zoom_test.py http://localhost:8000"""
import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1500, "height": 950}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await pg.goto(f"{sys.argv[1]}/index.html"); await pg.wait_for_timeout(14000)
        z = lambda: pg.evaluate("+datamap.deckgl.getViewports()[0].zoom.toFixed(2)")
        print("download buttons:", await pg.locator("text=/Download (CSV|JSON)/").count())
        z0 = await z(); print("start zoom:", z0, "| zoom-to-selection disabled with nothing selected:", await pg.is_disabled("#nx-zoom-sel"))
        await pg.click("#nx-zoom-in"); await pg.wait_for_timeout(1800); z1 = await z()
        await pg.click("#nx-zoom-in"); await pg.wait_for_timeout(1800); z2 = await z()
        await pg.click("#nx-zoom-out"); await pg.wait_for_timeout(1800); z3 = await z()
        print(f"+ -> {z1}, + -> {z2}, − -> {z3}")
        await pg.mouse.click(1300, 500); await pg.keyboard.press("Escape")
        await pg.keyboard.press("="); await pg.wait_for_timeout(1800); k1 = await z()
        await pg.keyboard.press("-"); await pg.wait_for_timeout(1800); k2 = await z()
        await pg.keyboard.press("0"); await pg.wait_for_timeout(2500); k3 = await z()
        print(f"keys: '=' -> {k1}, '-' -> {k2}, '0' -> {k3} (start {z0})")
        await pg.fill("#text-search", "graph neural"); await pg.wait_for_timeout(800)
        n = await pg.evaluate("datamap.getSelectedIndices().size")
        await pg.click("#nx-zoom-sel"); await pg.wait_for_timeout(2500)
        print(f"search 'graph neural' -> {n} highlighted; zoom-to-selection -> {await z()}")
        await pg.focus("#text-search"); await pg.wait_for_timeout(2500); zs = await z(); await pg.keyboard.press("-"); await pg.wait_for_timeout(1500); print("  zoom before typing:", zs)
        print("'-' typed in search box does not zoom:", await z())
        await pg.screenshot(path="/tmp/zoom_sel.png")
        await pg.click("#nx-zoom-fit"); await pg.wait_for_timeout(2500); print("fit ->", await z())
        print("errors:", [e for e in errs if "Font" not in e]); await b.close()
asyncio.run(main())

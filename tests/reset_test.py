"""Reset button + no bottom drawer + lasso still works: python tests/reset_test.py http://localhost:8000"""
import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1500, "height": 950}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await pg.goto(f"{sys.argv[1]}/index.html"); await pg.wait_for_timeout(16000)
        js = pg.evaluate
        view = lambda: js("(() => { const v = datamap.deckgl.getViewports()[0]; return [+v.longitude.toFixed(3), +v.latitude.toFixed(3), +v.zoom.toFixed(2)]; })()")
        print("bottom drawer elements:", await js("document.querySelectorAll('.drawer-container.drawer-bottom, .drawer-handle.bottom').length"),
              "| lasso tool present:", await js("!!datamap.lassoSelector"))
        v0 = await view(); print("opening view:", v0)
        # mess everything up
        await pg.click("#nx-years button[data-year='2025']")
        await pg.fill("#text-search", "diffusion"); await pg.wait_for_timeout(600)
        await pg.click("#nx-zoom-in"); await pg.wait_for_timeout(1500); await pg.click("#nx-zoom-in"); await pg.wait_for_timeout(1500)
        await pg.click(".color-map-dropdown"); await pg.click(".color-map-option >> nth=1"); await pg.wait_for_timeout(500)
        await js("datamap.lassoSelector.handleSelection([1,2,3,4,5])"); await pg.wait_for_timeout(300)
        lasso_btn = await js("!document.getElementById('nx-lasso-add').classList.contains('hidden')")
        await pg.click("#nx-trends-btn"); await pg.click(".trend-row >> nth=0"); await pg.wait_for_timeout(1500)
        print("before reset: view", await view(), "| selected", await js("datamap.getSelectedIndices().size"),
              "| colormap:", (await pg.inner_text(".color-map-selected")).strip()[:40], "| lasso add button shown:", lasso_btn)
        await pg.click("#nx-reset"); await pg.wait_for_timeout(2500)
        print("after reset:  view", await view(), "| selected", await js("datamap.getSelectedIndices().size"),
              "| colormap:", (await pg.inner_text(".color-map-selected")).strip()[:40],
              "| year chip:", await pg.inner_text("#nx-years button.active"), "| search:", repr(await pg.input_value("#text-search")),
              "| trends panel open:", await js("!document.getElementById('trends-panel').classList.contains('hidden')"),
              "| lasso add button:", await js("!document.getElementById('nx-lasso-add').classList.contains('hidden')"))
        await pg.click("#nx-zoom-in"); await pg.wait_for_timeout(1500); await pg.mouse.click(1300, 600); await pg.keyboard.press("r"); await pg.wait_for_timeout(2500)
        print("R key reset view:", await view())
        await pg.screenshot(path="/tmp/reset.png")
        print("errors:", [e for e in errs if "Font" not in e]); await b.close()
asyncio.run(main())

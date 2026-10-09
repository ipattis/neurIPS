"""Two-step "Where does my paper fit?" flow + pin release: python tests/pin_test.py http://localhost:8000 "<title. abstract>"
Downloads the ~570 MB browser model on first use."""
import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1500, "height": 950}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await pg.goto(f"{sys.argv[1]}/index.html"); await pg.wait_for_timeout(14000)
        js = lambda e: pg.evaluate(e)
        modal = lambda: js("!document.getElementById('fit-modal').classList.contains('hidden')")
        state = lambda: js("({pin: datamap.layers.some(l => l.id === 'my-paper-pin'), chip: !document.getElementById('nx-pin').classList.contains('hidden'), highlighted: datamap.getSelectedIndices().size, results: document.querySelectorAll('#fit-results li').length, placeEnabled: !document.getElementById('fit-place').disabled})")
        await pg.click("#nx-fit-btn"); await pg.fill("#fit-text", sys.argv[2])
        print("before find:", await state())
        await pg.click("#fit-go")
        await pg.wait_for_function("document.querySelectorAll('#fit-results li').length > 0 || /Couldn't/.test(document.getElementById('fit-status').textContent)", timeout=900000, polling=2000)
        print("after find -> modal open:", await modal(), "|", await state(), "|", await pg.inner_text("#fit-status"))
        print("top result:", (await pg.locator("#fit-results li").first.inner_text())[:80])
        await pg.locator("#fit-results li").first.click(); await pg.wait_for_timeout(400)
        print("result click -> paper panel on top:", await js("getComputedStyle(document.getElementById('paper-panel')).zIndex > getComputedStyle(document.getElementById('fit-modal')).zIndex"), "| modal still open:", await modal())
        await pg.click("[data-close='paper-panel']")
        await pg.fill("#fit-text", sys.argv[2] + " edited"); print("after editing text -> place enabled:", (await state())["placeEnabled"])
        await pg.fill("#fit-text", sys.argv[2]); await pg.click("#fit-go")
        await pg.wait_for_function("!document.getElementById('fit-place').disabled", timeout=120000)
        await pg.click("#fit-place"); await pg.wait_for_timeout(1200)
        print("after place -> modal open:", await modal(), "|", await state())
        await pg.screenshot(path="/tmp/pin_placed.png")
        await pg.click("#nx-pin-remove"); await pg.wait_for_timeout(1000)
        print("after release ->", await state())
        await pg.click("#nx-pin-show") if await js("!document.getElementById('nx-pin').classList.contains('hidden')") else None
        await pg.click("#nx-fit-btn"); print("reopened: results kept:", (await state())["results"], "| place enabled:", (await state())["placeEnabled"])
        print("errors:", [e for e in errs if "Font" not in e]); await b.close()
asyncio.run(main())

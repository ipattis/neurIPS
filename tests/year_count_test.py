"""Year chips update the subtitle's paper count: python tests/year_count_test.py http://localhost:8000"""
import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1500, "height": 950}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        for page in ("index.html", "problem.html"):
            await pg.goto(f"{sys.argv[1]}/{page}"); await pg.wait_for_timeout(14000)
            sub = lambda: pg.evaluate("[...document.querySelectorAll('#title-container *')].find(e => e.children.length === 0 && /accepted papers/.test(e.textContent)).textContent.trim()")
            print(page, "initial:", await sub())
            for y in ("2024", "2025", "2026", "All"):
                await pg.click(f"#nx-years button[data-year='{y}']"); await pg.wait_for_timeout(400)
                print(f"  {y}: {(await sub())[:60]} | selected points: {await pg.evaluate('datamap.getSelectedIndices().size')}")
        print("errors:", [e for e in errs if "Font" not in e]); await b.close()
asyncio.run(main())

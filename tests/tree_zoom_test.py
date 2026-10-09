"""Click topic-tree entries at each depth and screenshot: python tests/tree_zoom_test.py http://localhost:8000
Screenshots: /tmp/tree_<depth>.png. Check that the clicked category's name is rendered near the centre."""
import asyncio, sys
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(); pg = await b.new_page(viewport={"width": 1500, "height": 950}); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        await pg.goto(f"{sys.argv[1]}/index.html"); await pg.wait_for_timeout(15000)
        await pg.click("text=Expand All"); await pg.wait_for_timeout(500)
        ids = await pg.evaluate("""() => {
          const byDepth = {};
          for (const el of document.querySelectorAll('.topic-tree-label')) {
            const depth = el.dataset.labelId.split('_').length - 1;
            (byDepth[depth] = byDepth[depth] || []).push(el.dataset.labelId);
          }
          return Object.fromEntries(Object.entries(byDepth).map(([k, v]) => [k, v[Math.floor(v.length / 3)]]));
        }""")
        for depth, lid in sorted(ids.items()):
            await pg.locator(f'.topic-tree-label[data-label-id="{lid}"]').scroll_into_view_if_needed()
            await pg.click(f'.topic-tree-label[data-label-id="{lid}"]'); await pg.wait_for_timeout(1800)
            info = await pg.evaluate(f"""() => {{
              const d = datamap.labelLayer.props.data.find(x => x.id === '{lid}');
              const vp = datamap.deckgl.getViewports()[0]; const [x, y] = vp.project([d.x, d.y]);
              return {{name: d.label.replace(/\\n/g, ' '), screen: [Math.round(x), Math.round(y)], zoom: +vp.zoom.toFixed(2)}};
            }}""")
            print(f"depth {depth}: {info}")
            await pg.screenshot(path=f"/tmp/tree_{depth}.png")
        print("errors:", [e for e in errs if "Font" not in e]); await b.close()
asyncio.run(main())

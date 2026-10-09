"""Render the interactive NeurIPS 2025 map with datamapplot -> site/index.html.

Beyond the original: click a paper for a full detail panel (problem / method / ELI5 / links),
full-text search over titles, authors and tags, recolouring by session type, contribution
type or primary area, a topic tree, and lasso selection into an exportable table.
"""
import json

import datamapplot
import numpy as np
import pandas as pd
from datamapplot.selection_handlers import DataTable

from common import CLUSTER_NAMES, CLUSTERS, PAPERS, SITE, load_enrichment

HOVER_TEMPLATE = """
<div style="max-width:440px">
  <div style="font-size:15px;font-weight:600;line-height:1.25;margin-bottom:4px">{hover_text}</div>
  <div style="font-size:11px;opacity:.7;margin-bottom:6px">{kind} &middot; {cluster}</div>
  <div style="font-size:12.5px;line-height:1.4;margin-bottom:6px"><b>ELI5:</b> {eli5}</div>
  <div style="font-size:12px;line-height:1.4;opacity:.85">{summary}</div>
  <div style="font-size:10.5px;opacity:.55;margin-top:6px">Click for details</div>
</div>
"""

PANEL_HTML = """
<div id="paper-panel" class="hidden">
  <button id="paper-close" title="Close">&times;</button>
  <div id="paper-kind"></div>
  <h2 id="paper-title"></h2>
  <div id="paper-authors"></div>
  <div id="paper-cluster"></div>
  <div class="paper-section"><h4>Explain like I'm five</h4><p id="paper-eli5"></p></div>
  <div class="paper-section"><h4>Problem</h4><p id="paper-problem"></p></div>
  <div class="paper-section"><h4>Method</h4><p id="paper-method"></p></div>
  <div class="paper-section"><h4>Applications</h4><p id="paper-applications"></p></div>
  <div id="paper-tags"></div>
  <details class="paper-section"><summary>Abstract</summary><p id="paper-abstract"></p></details>
  <div id="paper-links"></div>
</div>
"""

PANEL_CSS = """
#paper-panel { position: fixed; top: 0; right: 0; width: 420px; max-width: 92vw; height: 100vh;
  overflow-y: auto; background: #fff; box-shadow: -4px 0 18px rgba(0,0,0,.18); z-index: 1000;
  padding: 22px 24px 40px; font-family: Roboto, sans-serif; box-sizing: border-box;
  transition: transform .2s ease; }
#paper-panel.hidden { transform: translateX(105%); }
#paper-close { position: absolute; top: 10px; right: 14px; border: none; background: none;
  font-size: 26px; cursor: pointer; color: #888; }
#paper-kind { display: inline-block; font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .05em; padding: 2px 8px; border-radius: 10px; background: #eef; color: #335; }
#paper-kind.Oral { background: #ffe3d6; color: #a33a00; }
#paper-kind.Spotlight { background: #fff3c4; color: #7a5a00; }
#paper-title { font-size: 19px; line-height: 1.3; margin: 10px 0 6px; }
#paper-authors { font-size: 12.5px; color: #555; margin-bottom: 6px; }
#paper-cluster { font-size: 12px; color: #777; margin-bottom: 10px; }
.paper-section h4 { font-size: 12px; text-transform: uppercase; letter-spacing: .05em;
  color: #888; margin: 14px 0 4px; }
.paper-section p { font-size: 13.5px; line-height: 1.5; margin: 0; color: #222; }
.paper-section summary { cursor: pointer; font-size: 12px; text-transform: uppercase;
  letter-spacing: .05em; color: #888; margin-top: 14px; }
#paper-tags { margin-top: 12px; }
#paper-tags span { display: inline-block; font-size: 11.5px; background: #f1f1f1; border-radius: 10px;
  padding: 2px 9px; margin: 0 4px 4px 0; color: #444; }
#paper-links a { display: inline-block; margin: 16px 10px 0 0; font-size: 13px; font-weight: 600;
  color: #2457c5; text-decoration: none; }
"""

PANEL_JS = """
window.showPaper = function(index, hoverData) {
  const get = (f) => (hoverData[f] ? hoverData[f][index] : "") || "";
  const set = (id, f) => { document.getElementById(id).textContent = get(f); };
  const kind = document.getElementById("paper-kind");
  kind.textContent = get("kind"); kind.className = get("kind");
  document.getElementById("paper-title").textContent = get("hover_text");
  set("paper-authors", "authors");
  document.getElementById("paper-cluster").textContent = get("path");
  ["eli5", "problem", "method", "applications", "abstract"].forEach(f => set("paper-" + f, f));
  document.querySelectorAll(".paper-section").forEach(el => {
    const p = el.querySelector("p"); el.style.display = p && p.textContent ? "" : "none";
  });
  const tags = document.getElementById("paper-tags"); tags.innerHTML = "";
  get("tags").split("; ").filter(Boolean).forEach(t => {
    const s = document.createElement("span"); s.textContent = t; tags.appendChild(s);
  });
  const links = document.getElementById("paper-links"); links.innerHTML = "";
  [["OpenReview", "openreview"], ["NeurIPS page", "virtual"]].forEach(([label, f]) => {
    if (!get(f)) return;
    const a = document.createElement("a"); a.href = get(f); a.target = "_blank";
    a.rel = "noopener"; a.textContent = label + " \\u2197"; links.appendChild(a);
  });
  document.getElementById("paper-panel").classList.remove("hidden");
};
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("paper-close").onclick = () =>
    document.getElementById("paper-panel").classList.add("hidden");
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") document.getElementById("paper-panel").classList.add("hidden");
  });
});
"""


def main():
    papers = pd.read_parquet(PAPERS)
    clusters = pd.read_parquet(CLUSTERS)
    names = json.loads(CLUSTER_NAMES.read_text())
    enrich = load_enrichment()
    df = papers.merge(clusters, on="pid")
    print(f"{len(df)} papers, {sum(u in enrich for u in df['pid'])} enriched")

    def field(f):
        return [enrich.get(u, {}).get(f, "") for u in df["pid"]]

    fine = np.array([names[f"F{c}"]["name"] for c in df["fine"]])
    mid = np.array([names[f"M{c}"]["name"] for c in df["mid"]])
    top = np.array([names[f"T{c}"]["name"] for c in df["top"]])
    tags = ["; ".join(t) if isinstance(t, list) else "" for t in field("tags")]
    summary = [s or a[:350] + "..." for s, a in zip(field("summary"), df["abstract"])]
    contribution = [c or "Unknown" for c in field("contribution_type")]

    extra = pd.DataFrame(
        {
            "kind": df["kind"],
            "cluster": fine,
            "path": [f"{t}  ›  {m}  ›  {f}" for t, m, f in zip(top, mid, fine)],
            "authors": df["authors"],
            "summary": summary,
            "eli5": field("eli5"),
            "problem": field("problem"),
            "method": field("method"),
            "applications": field("applications"),
            "abstract": df["abstract"],
            "tags": tags,
            "openreview": df["openreview"],
            "virtual": df["virtual"],
            "search": df["title"] + " | " + df["authors"] + " | " + pd.Series(tags) + " | " + fine,
        }
    )

    # Lasso selection -> sortable, exportable reading list
    table = DataTable(columns=["hover_text", "kind", "cluster", "authors"], location="bottom-drawer", max_rows_per_page=25)

    plot = datamapplot.create_interactive_plot(
        df[["x", "y"]].to_numpy(),
        fine,
        mid,
        top,
        hover_text=df["title"].to_numpy(),
        hover_text_html_template=HOVER_TEMPLATE,
        extra_point_data=extra,
        title="NeurIPS 2025: A Visual Map",
        sub_title=f"{len(df):,} accepted papers, clustered by topic. Zoom for detail, hover to preview, click to read.",
        enable_search=True,
        search_field="search",
        enable_topic_tree=True,
        on_click="showPaper(index, hoverData);",
        selection_handler=table,
        colormaps={
            "Session type": df["kind"].to_numpy(),
            "Contribution type": np.array(contribution),
            "Primary area (NeurIPS)": df["area"].to_numpy(),
        },
        custom_html=PANEL_HTML,
        custom_css=PANEL_CSS,
        custom_js=PANEL_JS,
        font_family="Roboto",
        cluster_boundary_polygons=True,
        cluster_boundary_line_width=6,
        point_radius_max_pixels=12,
        text_outline_width=6,
        initial_zoom_fraction=0.95,
    )
    out = SITE / "index.html"
    plot.save(str(out))
    print(f"Saved {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()

"""Render the three interactive maps (topic / problem / method) with datamapplot.

    python 08_build_map.py            # self-contained HTML files in site/ (open directly)
    python 08_build_map.py --hosted   # site/ + split data files, for GitHub Pages / any static host

Each page shares the same toolbar: switch view, filter by year, "where does my paper fit?",
and an agenda (saved in the browser, exportable as .ics/CSV) that works across all three pages.
"""
import argparse
import base64
import json
from pathlib import Path

import datamapplot
import numpy as np
import pandas as pd
from datamapplot.selection_handlers import DataTable

from common import COMBINED, SEARCH_DIM, SEARCH_MODEL_ONNX, SITE, VIEWS, load_enrichment, load_papers

WEB = Path(__file__).parent / "web"
PAGES = {
    "topic": ("index.html", "By topic", "Papers placed by what they are about"),
    "problem": ("problem.html", "By problem", "Papers placed by the problem they tackle: different methods, same goal"),
    "method": ("method.html", "By method", "Papers placed by the technique they use: same tool, different problems"),
}
TITLES = {
    "topic": "NeurIPS {years}: where ML is moving",
    "problem": "NeurIPS {years}: the problem map",
    "method": "NeurIPS {years}: the method map",
}
N_TOP_INSTITUTIONS = 15

HOVER_TEMPLATE = """
<div style="max-width:440px">
  <div style="font-size:15px;font-weight:600;line-height:1.25;margin-bottom:4px">{hover_text}</div>
  <div style="font-size:11px;opacity:.7;margin-bottom:6px">{year} &middot; {kind} &middot; {cluster}</div>
  <div style="font-size:12.5px;line-height:1.4;margin-bottom:6px"><b>ELI5:</b> {eli5}</div>
  <div style="font-size:12px;line-height:1.4;opacity:.85">{summary}</div>
  <div style="font-size:10.5px;opacity:.55;margin-top:6px">Click for details</div>
</div>
"""


def load_trends(view):
    path = COMBINED / f"trends_{view}.json"
    return json.loads(path.read_text()) if path.exists() else {"years": [], "layers": {}}


def build_view(view, papers, enrich, ext, audit, search_b64, years, hosted):
    m = pd.read_parquet(COMBINED / f"map_{view}.parquet")
    df = papers.merge(m, on="pid").merge(ext, on="pid", how="left").merge(audit, on="pid", how="left")
    # The browser search index is in load_papers() order; the map points must be too.
    assert (df["pid"].to_numpy() == papers["pid"].to_numpy()).all()
    layers = sorted(int(c[1:-3]) for c in m.columns if c.endswith("_id"))
    trends = load_trends(view)
    note_layer = next((l for l in layers[1:-1] if str(l) in trends["layers"]), layers[min(1, len(layers) - 1)])

    def field(f):
        return [enrich.get(p, {}).get(f, "") for p in df["pid"]]

    names = [df[f"L{l}_name"].to_numpy() for l in layers]  # finest first
    tags = ["; ".join(t) if isinstance(t, list) else "" for t in field("tags")]
    path = [" › ".join(dict.fromkeys(n[i] for n in reversed(names) if n[i] != "Unlabelled")) for i in range(len(df))]
    trend_key = [f"{note_layer}:{t}" if t >= 0 else "" for t in df[f"L{note_layer}_id"]]

    trend_lookup = {
        f"{l}:{tid}": info for l, topics in trends["layers"].items() for tid, info in topics.items()
    }
    growth_layer = str(layers[min(1, len(layers) - 1)])
    growth = np.array([
        trends["layers"].get(growth_layer, {}).get(str(t), {}).get("growth", np.nan) if t >= 0 else np.nan
        for t in df[f"L{growth_layer}_id"]
    ], dtype=float)

    top_inst = df.loc[df["first_institution"] != "", "first_institution"].value_counts().head(N_TOP_INSTITUTIONS).index
    # Papers found only on the virtual site (2026) have no affiliation data yet.
    institution = np.where(df["first_institution"].isin(top_inst), df["first_institution"],
                           np.where(df["first_institution"] == "", "Not listed", "Other"))
    confirmed = df["decision_confirmed"].fillna(True).astype(bool)
    session_type = np.where(confirmed, df["kind"], df["kind"] + " (decision unconfirmed)")
    citations = df["citations"].astype("Int64")

    extra = pd.DataFrame({
        "pid": df["pid"],
        "year": df["year"].astype(str),
        "kind": df["kind"],
        "cluster": names[0],
        "path": path,
        "authors": df["authors"],
        "institutions": df["institutions"],
        "summary": [s or a[:350] + "..." for s, a in zip(field("summary"), df["abstract"])],
        "eli5": field("eli5"),
        "problem": field("problem"),
        "method": field("method"),
        "applications": field("applications"),
        "abstract": df["abstract"],
        "tags": tags,
        "code": df["code"],
        "arxiv": df["arxiv"].fillna(""),
        "openreview": df["openreview"],
        "virtual": df["virtual"],
        "s2_url": df["s2_url"].fillna(""),
        "citations": citations.astype(str).replace("<NA>", ""),
        "citation_pct": (df["citation_pct"] * 100).round(1).fillna("").astype(str),
        "session": df["session"],
        "room": df["room"],
        "start": df["start"],
        "end": df["end"],
        "trend_key": trend_key,
        **{f"tid{l}": df[f"L{l}_id"].astype(str) for l in layers},  # per-layer topic ids for the Trends panel
        "audit_flag": df["audit_flag"].fillna(""),
        "search": df["title"] + " | " + df["authors"] + " | " + df["institutions"] + " | " + pd.Series(tags) + " | " + pd.Series(path),
    })

    colormap_rawdata = [
        df["year"].astype(str).to_numpy(),
        np.nan_to_num(np.clip(growth, -1.5, 1.5)),  # unclustered points read as "no change"
        session_type,
        np.array([c or "Unknown" for c in field("contribution_type")]),
        np.log10(citations.astype(float).fillna(0).to_numpy() + 1),
        np.where(df["code"].ne("") | df["arxiv"].fillna("").ne(""), "Has code/arXiv link", "No link found"),
        institution,
        df["area"].to_numpy(),
    ]
    colormap_metadata = [
        {"field": "year", "description": "Year", "cmap": "Set1", "kind": "categorical"},
        {"field": "growth", "description": f"Topic growth {years[-2] if len(years) > 1 else ''}→{years[-1]} (log2)", "cmap": "RdYlGn", "kind": "continuous"},
        {"field": "kind", "description": "Session type", "cmap": "Set2", "kind": "categorical"},
        {"field": "contrib", "description": "Contribution type", "cmap": "tab10", "kind": "categorical"},
        {"field": "cites", "description": "Citations (log10, Semantic Scholar)", "cmap": "viridis", "kind": "continuous"},
        {"field": "links", "description": "Code / arXiv availability", "cmap": "Paired", "kind": "categorical"},
        {"field": "inst", "description": f"First-author institution (top {N_TOP_INSTITUTIONS})", "cmap": "tab20", "kind": "categorical"},
        {"field": "area", "description": "NeurIPS primary area", "cmap": "tab20", "kind": "categorical"},
    ]

    level_names = ["Broad areas", "Fields", "Topics", "Fine topics", "Finest"]
    trend_layers = [{"layer": l, "label": level_names[i]} for i, l in enumerate(sorted(layers, reverse=True))
                    if str(l) in trends["layers"]]
    config = {
        "view": view,
        "views": [{"key": k, "file": f, "label": l, "help": h} for k, (f, l, h) in PAGES.items()],
        "years": [str(y) for y in years],
        "yearCounts": {str(y): int(n) for y, n in df["year"].value_counts().items()},
        "latestYear": str(years[-1]),
        "trends": trend_lookup,
        "trendLayers": trend_layers,
        "searchIndexB64": search_b64,
        "searchDim": SEARCH_DIM,
        "searchModel": SEARCH_MODEL_ONNX,
        "searchInstruction": f"Instruct: {VIEWS['topic']}\nQuery: ",
    }
    custom_js = "window.NX = " + json.dumps(config) + ";\n" + (WEB / "app.js").read_text()
    year_span = f"{years[0]}–{years[-1]}" if len(years) > 1 else str(years[0])
    page, _, _ = PAGES[view]

    kwargs = {}
    if hosted:
        # Point/label/metadata are written as data_<view>_*.zip next to the HTML and fetched on load.
        kwargs.update(inline_data=False, offline_data_path=SITE / f"data_{view}")

    plot = datamapplot.create_interactive_plot(
        df[["x", "y"]].to_numpy(),
        *names,
        hover_text=df["title"].to_numpy(),
        hover_text_html_template=HOVER_TEMPLATE,
        extra_point_data=extra,
        title=TITLES[view].format(years=year_span),
        sub_title=f"{len(df):,} accepted papers. Zoom for detail, hover to preview, click to read. {PAGES[view][2]}.",
        enable_search=True,
        search_field="search",
        enable_topic_tree=True,
        on_click="showPaper(index);",
        selection_handler=DataTable(columns=["hover_text", "year", "kind", "cluster", "citations"], location="bottom-drawer", max_rows_per_page=25),
        colormap_rawdata=colormap_rawdata,
        colormap_metadata=colormap_metadata,
        custom_html=(WEB / "app.html").read_text(),
        custom_css=(WEB / "app.css").read_text(),
        custom_js=custom_js,
        font_family="Roboto",
        title_font_size=22,  # points
        sub_title_font_size=12,
        cluster_boundary_polygons=True,
        cluster_boundary_line_width=6,
        point_radius_max_pixels=12,
        text_outline_width=6,
        initial_zoom_fraction=0.92,
        **kwargs,
    )
    out = SITE / page
    plot.save(str(out))
    # datamapplot omits a viewport tag, so phones would render the desktop layout zoomed out.
    html = out.read_text()
    out.write_text(html.replace("<head>", '<head>\n    <meta name="viewport" content="width=device-width, initial-scale=1" />', 1))
    print(f"{view}: saved {out.name} ({out.stat().st_size / 1e6:.1f} MB), topics per layer={[len(set(n) - {'Unlabelled'}) for n in names]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hosted", action="store_true", help="write split data files for static hosting")
    ap.add_argument("--views", default=",".join(VIEWS))
    args = ap.parse_args()

    papers = load_papers()
    years = sorted(int(y) for y in papers["year"].unique())
    enrich = load_enrichment()
    ext = pd.read_parquet(COMBINED / "external.parquet")
    audit_path = COMBINED / "audit.parquet"
    if audit_path.exists():
        a = pd.read_parquet(audit_path)
        fields = ["summary", "problem", "method", "eli5", "applications"]
        bad = (a[fields] == "unsupported").any(axis=1)
        audit = pd.DataFrame({"pid": a["pid"], "audit_flag": np.where(bad, a["issues"].apply(lambda x: "; ".join(list(x)[:2])), "")})
    else:
        audit = pd.DataFrame({"pid": [], "audit_flag": []})
    # int8 search index for the browser, in the same paper order as the map points
    z = np.load(COMBINED / "emb_search.npz", allow_pickle=False)
    lookup = dict(zip(z["pids"], range(len(z["pids"]))))
    vecs = z["vectors"][[lookup[p] for p in papers["pid"]]]
    search_b64 = base64.b64encode(np.clip(np.round(vecs * 127), -127, 127).astype(np.int8).tobytes()).decode()

    if args.hosted:
        for f in SITE.glob("data_*.zip"):
            f.unlink()
    for view in args.views.split(","):
        build_view(view, papers, enrich, ext, audit, search_b64, years, args.hosted)


if __name__ == "__main__":
    main()

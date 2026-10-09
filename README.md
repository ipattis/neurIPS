# NeurIPS maps: where ML is moving

Interactive, zoomable maps of every accepted NeurIPS paper from **2024, 2025 and 2026** (19,493 papers).
They show what the field works on, which problems it tackles, which methods it uses, and how all three
are shifting year to year.

**Open `site/index.html`** in a browser (desktop or mobile). Each page is self-contained, about 42 MB with
three years of data, so the first load takes a few seconds.

> ### Credit: built on Jay Alammar's work
> This project began as a rebuild of **Jay Alammar's** [*The Illustrated NeurIPS 2025: A Visual Map*](https://newsletter.languagemodels.co/p/the-illustrated-neurips-2025-a-visual)
> ([interactive demo](https://jalammar.github.io/assets/neurips_2025.html)). Jay turned ~6,000 NeurIPS 2025
> abstracts into a navigable map:
> - embed each abstract;
> - have an LLM write summaries, problem/method notes and "explain like I'm five" (ELI5) explanations;
> - reduce to 2D with UMAP and cluster hierarchically;
> - name clusters in two passes: each one in isolation first, then all together to remove duplicates;
> - render it with [datamapplot](https://github.com/TutteInstitute/datamapplot).
>
> We found it through [Daniel Svonava's LinkedIn post](https://www.linkedin.com/feed/update/urn:li:activity:7401292344811028481/)
> walking through Jay's three-phase pipeline. The original 2025-only rebuild, kept close to Jay's design,
> is in `v1/`. Everything else here extends that idea.

## What's in the map

| Feature | How it works |
|---|---|
| **Three maps of the same papers** | *By topic* (what it's about), *By problem* (what it's trying to solve), *By method* (how it does it). Switch views in the toolbar. In the problem map, different techniques for the same goal sit together. In the method map, one technique applied to different problems does. |
| **Trend map** | All years share one 2D layout, so a region means the same thing every year. The year chips filter the map, and the subtitle's paper count follows the selection. The **Trends** panel ranks topics by change in *share* of all papers (fastest growing / shrinking / largest) at each zoom level, with per-year counts. Clicking a topic highlights its papers, zooms to its label and shows an LLM-written *"What's new in YYYY"* note. "Color by → Topic growth" paints the whole map by growth. |
| **Topic tree** | Clicking any category zooms until that category's own label is visible, centred in the part of the map not covered by panels. Broader labels win label collisions, so this sometimes means zooming in quite far. |
| **Where does my paper fit?** | Paste an abstract and click **Find closest papers**. It's embedded **in your browser** (transformers.js + Qwen3-Embedding-0.6B in q4f16, a one-time ~570 MB download). The modal then lists the closest topic and the 12 nearest papers, and nothing leaves the browser. **Place it on the map** pins it, highlights those papers and closes the modal. The toolbar's **📍 My paper** flies back to the pin and its results; **✕** releases the pin and resets the view. |
| **Agenda builder** | Star papers from the detail panel, or lasso a region and click *"+ Add N selected"*. The agenda is grouped by day in venue-local time (Sydney / Paris / Atlanta in 2026) and flags overlapping sessions. Export it as **.ics** (calendar) or CSV. It's saved in the browser and shared across the three map pages. |
| **Richer paper data** | Semantic Scholar citation counts and within-year percentiles, arXiv links, code links found in abstracts, author institutions. Color modes for first-author institution, citations, code availability, session type, contribution type and NeurIPS primary area. Search covers titles, authors, institutions, tags and topics. |
| **Trust signals** | An LLM-as-judge audit spot-checks the AI-written summaries against the abstracts (`data/audit_report.md`). Papers it flags show a warning in their detail panel. |
| **Mobile + hosting** | A responsive layout (bottom-sheet details, compact toolbar). `--hosted` builds split the data into lazily loaded files, and a GitHub Pages workflow publishes them. |

Plus the datamapplot basics: hover previews, a click-through detail panel, multi-level labels, and lasso → sortable, exportable table.

## Pipeline (`pipeline/`)

```
01_fetch.py      neurips.cc data per year (+ abstracts JSON + per-paper pages when incomplete) → data/<year>/papers.parquet
02_enrich.py     Claude via Bedrock batch: summary, problem, method, ELI5, applications, contribution type, tags
03_embed.py      Qwen3-Embedding-4B, 3 task-instructed views (topic/problem/method) + 0.6B browser search index (local GPU)
04_external.py   Semantic Scholar: bulk venue search + per-title fallback → citations, arXiv links
05_topics.py     shared UMAP layout + EVoC multi-resolution clusters + Toponymy topic names (Claude Sonnet 5.5)
06_trends.py     per-topic growth (computed from counts) + "what's new" notes (Bedrock batch)
07_audit.py      faithfulness audit of the enrichments (Sonnet 4.6 judge, Bedrock batch) → data/audit_report.md
08_build_map.py  datamapplot HTML ×3 with the custom toolbar, panels, agenda and search (pipeline/web/)
```

How it differs from Jay's original:
- local Qwen3 embeddings instead of Cohere Embed 4, and Claude instead of Command A;
- data-driven cluster levels (EVōC) instead of fixed K-Means;
- [Toponymy](https://github.com/TutteInstitute/toponymy) naming, which generalises the two-pass naming idea;
- three views and three years instead of one map of one year.

Run everything with `./run_all.sh` (or `./run_all.sh --hosted`). Every step caches its outputs, so a re-run
only processes what's new. `01_fetch.py` prints each year's abstract coverage and skips a year until at
least 90% of its abstracts are available.

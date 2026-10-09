#!/usr/bin/env bash
# Rebuild the NeurIPS maps end to end. Every step caches its outputs in data/, so re-running
# (e.g. once NeurIPS 2026 abstracts are published) only processes what's new.
#   ./run_all.sh            # self-contained HTML in site/
#   ./run_all.sh --hosted   # site/ with split data files, ready for GitHub Pages
set -euo pipefail
cd "$(dirname "$0")/pipeline"
PY="${PYTHON:-$HOME/.venvs/neurips/bin/python}"
export HF_HUB_DISABLE_XET=1   # the Xet CDN is blocked on some corporate networks

"$PY" 01_fetch.py           # neurips.cc -> data/<year>/papers.parquet (+ which years are ready)
"$PY" 02_enrich.py          # Bedrock batch: summaries, ELI5, problem, method, tags
"$PY" 03_embed.py           # Qwen3-Embedding-4B (3 views) + 0.6B search index, local GPU
"$PY" 04_external.py        # Semantic Scholar citations + arXiv links
"$PY" 05_topics.py          # shared UMAP + EVoC clusters + Toponymy names (Claude Sonnet)
"$PY" 06_trends.py          # topic growth + "what's new" notes (Bedrock batch)
"$PY" 07_audit.py           # LLM-as-judge faithfulness spot check (Bedrock batch)
"$PY" 08_build_map.py "$@"  # site/index.html, problem.html, method.html
echo "Done: open site/index.html"

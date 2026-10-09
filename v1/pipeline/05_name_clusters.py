"""Two-pass LLM cluster naming (the "context handoff" trick).

Pass 1 (fast model, focused context): name each cluster bottom-up -- fine clusters from their
most central papers, mid clusters from their fine-cluster names, top clusters from mid names.
Pass 2 (smart model, global context): see the whole draft hierarchy at once, remove duplicate or
vague names, and make every name distinct from its siblings and more specific than its parent.
"""
import json
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from common import CLUSTER_NAMES, CLUSTERS, FAST_MODEL, PAPERS, SMART_MODEL, call_tool, llm_client, load_enrichment

N_REPRESENTATIVE = 12

NAME_TOOL = {
    "name": "name_cluster",
    "description": "Give a cluster of research papers a short, specific name.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "2-5 word topic name, Title Case, no 'Papers on' / 'Research in'."},
            "description": {"type": "string", "description": "One sentence describing what unites these papers."},
        },
        "required": ["name", "description"],
    },
}

FINE_PROMPT = """These are the most central papers in one small cluster of NeurIPS 2025 papers.
Name the specific research topic they share. Prefer concrete terms (e.g. "KV Cache Compression") over broad ones (e.g. "Efficient LLMs").

{items}"""

PARENT_PROMPT = """This is a {level} group of NeurIPS 2025 papers, made of the following sub-topics (with paper counts).
Give the group a name that covers all of them and is broader than any single sub-topic.

{items}"""

REFINE_TOOL = {
    "name": "finalize_names",
    "description": "Return the final, globally coherent name for every cluster in the hierarchy.",
    "input_schema": {
        "type": "object",
        "properties": {
            "reasoning": {"type": "string", "description": "Brief notes on duplicates or vague names you fixed."},
            "names": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"key": {"type": "string"}, "name": {"type": "string"}},
                    "required": ["key", "name"],
                },
            },
        },
        "required": ["reasoning", "names"],
    },
}

REFINE_PROMPT = """Below is a 3-level topic hierarchy for an interactive map of ~6,000 NeurIPS 2025 papers.
Draft names were written for each cluster in isolation, so some are duplicated, overlapping or vague.

Rewrite names so that:
- Every name is unique across the whole map, and sibling names are clearly distinguishable.
- Top-level names (T*) are broad research areas (2-4 words); mid-level (M*) are sub-fields; fine-level (F*) are specific topics.
- A child is never just a copy of its parent; it says what is specific about it.
- Names are short (2-5 words), Title Case, and readable as map labels by a non-specialist.
- Keep a good draft name unchanged.

Return a name for EVERY key (T*, M* and F*).

{tree}"""


def representative_rows(clusters, papers, enrich, level, cid):
    members = clusters[clusters[level] == cid]
    centre = members[["x", "y"]].mean().to_numpy()
    dist = np.linalg.norm(members[["x", "y"]].to_numpy() - centre, axis=1)
    picked = members.iloc[np.argsort(dist)[:N_REPRESENTATIVE]]
    lines = []
    for pid in picked["pid"]:
        p = papers.loc[pid]
        blurb = enrich[pid]["summary"] if pid in enrich else p["abstract"][:300]
        lines.append(f"- {p['title']}: {blurb}")
    return "\n".join(lines)


def main():
    clusters = pd.read_parquet(CLUSTERS)
    papers = pd.read_parquet(PAPERS).set_index("pid")
    enrich = load_enrichment()
    client = llm_client()
    pool = ThreadPoolExecutor(12)
    draft_path = CLUSTER_NAMES.with_name("cluster_names_draft.json")
    # Reuse pass-1 drafts unless clusters were rebuilt since they were written.
    if draft_path.exists() and draft_path.stat().st_mtime > CLUSTERS.stat().st_mtime:
        draft = json.loads(draft_path.read_text())
        print(f"Pass 1: reusing {draft_path.name}")
    else:
        draft = pass_one(clusters, papers, enrich, client, pool)
        draft_path.write_text(json.dumps(draft, indent=2))
    pass_two(clusters, draft, client)


def pass_one(clusters, papers, enrich, client, pool):
    draft = {}

    # ---- Pass 1: bottom-up, isolated naming ----
    fine_ids = sorted(clusters["fine"].unique())
    prompts = [FINE_PROMPT.format(items=representative_rows(clusters, papers, enrich, "fine", c)) for c in fine_ids]
    for c, (res, _) in zip(fine_ids, pool.map(lambda p: call_tool(client, FAST_MODEL, p, NAME_TOOL, 300), prompts)):
        draft[f"F{c}"] = res
    print(f"Pass 1: named {len(fine_ids)} fine clusters")

    for level, child, key, child_key in [("mid", "fine", "M", "F"), ("top", "mid", "T", "M")]:
        ids = sorted(clusters[level].unique())
        prompts = []
        for c in ids:
            sub = clusters[clusters[level] == c][child].value_counts()
            items = "\n".join(f"- {draft[f'{child_key}{s}']['name']} ({n}): {draft[f'{child_key}{s}']['description']}" for s, n in sub.items())
            prompts.append(PARENT_PROMPT.format(level="broad" if level == "top" else "mid-level", items=items))
        for c, (res, _) in zip(ids, pool.map(lambda p: call_tool(client, FAST_MODEL, p, NAME_TOOL, 300), prompts)):
            draft[f"{key}{c}"] = res
        print(f"Pass 1: named {len(ids)} {level} clusters")
    return draft


def pass_two(clusters, draft, client):
    # ---- Pass 2: global refinement with the whole hierarchy in context ----
    tree_lines = []
    for t in sorted(clusters["top"].unique()):
        tree_lines.append(f"T{t}: {draft[f'T{t}']['name']}")
        for m in sorted(clusters[clusters["top"] == t]["mid"].unique()):
            tree_lines.append(f"  M{m}: {draft[f'M{m}']['name']}")
            for f in sorted(clusters[clusters["mid"] == m]["fine"].unique()):
                n = int((clusters["fine"] == f).sum())
                tree_lines.append(f"    F{f}: {draft[f'F{f}']['name']} ({n} papers) -- {draft[f'F{f}']['description']}")
    res, usage = call_tool(client, SMART_MODEL, REFINE_PROMPT.format(tree="\n".join(tree_lines)), REFINE_TOOL, max_tokens=16000)
    final = {item["key"]: item["name"] for item in res["names"]}
    missing = [k for k in draft if k not in final]
    print(f"Pass 2 ({SMART_MODEL}): {len(final)} names, {len(missing)} missing (kept draft). Reasoning:\n{res['reasoning']}")

    out = {
        k: {"name": final.get(k, v["name"]), "draft_name": v["name"], "description": v["description"]}
        for k, v in draft.items()
    }
    out["_reasoning"] = res["reasoning"]
    CLUSTER_NAMES.write_text(json.dumps(out, indent=2))
    print(f"Saved {CLUSTER_NAMES}")


if __name__ == "__main__":
    main()

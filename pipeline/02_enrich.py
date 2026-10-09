"""Per-paper LLM enrichment via Bedrock batch: summary, problem, method, ELI5, applications, tags.

Already-enriched papers are skipped, so re-running only processes new papers (e.g. 2026 once its
abstracts appear). Failed records are left out and retried on the next run.

--refresh-fields re-generates only some fields for papers enriched with an older prompt, e.g. after
the faithfulness audit (07) showed the original "applications" prompt invited speculation.
Usage: python 02_enrich.py [--limit N] [--on-demand] [--refresh-fields applications]
"""
import argparse
import json

from bedrock_batch import run_batch
from common import ENRICH_MODEL, enrichment_path, load_enrichment, load_papers, ready_years, tool_request, tool_result

TOOL = {
    "name": "record_paper_analysis",
    "description": "Record a structured, plain-language analysis of a research paper.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "2 sentence summary of what the paper does and finds."},
            "problem": {"type": "string", "description": "1-2 sentences: the problem or gap the paper addresses."},
            "method": {"type": "string", "description": "1-2 sentences: the core technical approach."},
            "eli5": {
                "type": "string",
                "description": "Explain it like I'm five: 2-3 short sentences, everyday analogy, no jargon.",
            },
            "applications": {
                "type": "string",
                "description": "1 sentence on practical uses or who benefits, using ONLY what the abstract states or "
                "directly implies. Do not invent example domains. If the abstract names no application, write "
                "'The abstract does not name specific applications.' followed by the general area it advances.",
            },
            "contribution_type": {
                "type": "string",
                "enum": ["New method", "Theory", "Benchmark / dataset", "Empirical analysis", "Survey / position", "System / tool"],
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3-5 short lowercase topic tags, e.g. 'diffusion models', 'reinforcement learning'.",
            },
        },
        "required": ["summary", "problem", "method", "eli5", "applications", "contribution_type", "tags"],
    },
}

PROMPT = """You are helping build an accessible, explorable map of NeurIPS papers for a broad audience.
Read the paper below and record your analysis with the tool. Be concrete and faithful to the abstract; do not invent results.

Title: {title}

Abstract: {abstract}"""


# Bump when a field's prompt changes; --refresh-fields only redoes records below this version.
PROMPT_VERSION = 2


def subset_tool(fields):
    props = {f: TOOL["input_schema"]["properties"][f] for f in fields}
    return {**TOOL, "input_schema": {"type": "object", "properties": props, "required": list(fields)}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--on-demand", action="store_true", help="skip batch (faster turnaround, ~2x cost)")
    ap.add_argument("--refresh-fields", default=None, help="comma-separated fields to regenerate for older records")
    args = ap.parse_args()

    df = load_papers()
    done = load_enrichment()
    if args.refresh_fields:
        fields = args.refresh_fields.split(",")
        tool = subset_tool(fields)
        todo = df[df["pid"].map(lambda p: p in done and done[p].get("prompt_version", 1) < PROMPT_VERSION)]
        job = f"refresh-{'-'.join(fields)}"
    else:
        tool, fields = TOOL, None
        required = TOOL["input_schema"]["required"]
        # Incomplete records (a model occasionally returns a partial tool call) are redone too.
        todo = df[df["pid"].map(lambda p: p not in done or any(not done[p].get(f) for f in required))]
        job = "enrich"
    if args.limit:
        todo = todo.head(args.limit)
    print(f"{len(done)} enriched, {len(todo)} to process with {ENRICH_MODEL}" + (f" (refreshing {fields})" if fields else ""))
    if todo.empty:
        return

    requests = {
        row.pid: tool_request(PROMPT.format(title=row.title, abstract=row.abstract), tool, max_tokens=1024, model=ENRICH_MODEL)
        for row in todo.itertuples()
    }
    if args.on_demand:
        from bedrock_batch import _on_demand

        results = _on_demand(ENRICH_MODEL, requests, workers=16)
    else:
        years = "-".join(str(y) for y in sorted(todo["year"].unique()))
        results = run_batch(f"{job}-{years}-n{len(requests)}", ENRICH_MODEL, requests)

    tokens_in = tokens_out = failed = 0
    year_of = dict(zip(todo["pid"], todo["year"]))
    files = {y: open(enrichment_path(y), "a") for y in ready_years()}
    try:
        for pid, resp in results.items():
            try:
                out = tool_result(resp["content"])
                if any(not out.get(f) for f in tool["input_schema"]["required"]):
                    raise ValueError("missing fields")
                if fields:  # a refresh keeps the old record and overwrites only the refreshed fields
                    rec = {**done[pid], **out, "prompt_version": PROMPT_VERSION, "refresh_model": ENRICH_MODEL}
                else:
                    rec = {"pid": pid, **out, "prompt_version": PROMPT_VERSION, "model": ENRICH_MODEL}
            except Exception:
                failed += 1
                continue
            files[year_of[pid]].write(json.dumps(rec) + "\n")
            tokens_in += resp["usage"]["input_tokens"]
            tokens_out += resp["usage"]["output_tokens"]
    finally:
        for f in files.values():
            f.close()
    print(f"Saved {len(results) - failed} records. Tokens: {tokens_in:,} in / {tokens_out:,} out. Failed: {failed} (re-run to retry)")


if __name__ == "__main__":
    main()

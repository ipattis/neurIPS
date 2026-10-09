"""Per-paper LLM enrichment: summary, problem, method, ELI5, applications, tags.

Resumable: results are appended to data/enrichment.jsonl and already-done papers are skipped.
Usage: python 03_enrich.py [--limit N] [--workers W]
"""
import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
from tqdm import tqdm

from common import ENRICHMENT, FAST_MODEL, PAPERS, call_tool, llm_client, load_enrichment

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
            "applications": {"type": "string", "description": "1 sentence: practical uses or who benefits."},
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

PROMPT = """You are helping build an accessible, explorable map of NeurIPS 2025 papers for a broad audience.
Read the paper below and record your analysis with the tool. Be concrete and faithful to the abstract; do not invent results.

Title: {title}

Abstract: {abstract}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=12)
    args = ap.parse_args()

    df = pd.read_parquet(PAPERS)
    done = load_enrichment()
    todo = df[~df["pid"].isin(done)]
    if args.limit:
        todo = todo.head(args.limit)
    print(f"{len(done)} done, {len(todo)} to process with {FAST_MODEL}")

    client = llm_client()
    lock = threading.Lock()
    tokens = {"in": 0, "out": 0}
    failures = []

    def work(row):
        result, usage = call_tool(client, FAST_MODEL, PROMPT.format(title=row.title, abstract=row.abstract), TOOL, max_tokens=1024)
        return {"pid": row.pid, **result}, usage

    with open(ENRICHMENT, "a") as f, ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(work, row): row.pid for row in todo.itertuples()}
        for fut in tqdm(as_completed(futures), total=len(futures)):
            try:
                rec, usage = fut.result()
            except Exception as e:  # keep going; rerun the script to retry failures
                failures.append((futures[fut], repr(e)[:200]))
                continue
            with lock:
                f.write(json.dumps(rec) + "\n")
                f.flush()
                tokens["in"] += usage.input_tokens
                tokens["out"] += usage.output_tokens

    print(f"Tokens: {tokens['in']:,} in / {tokens['out']:,} out. Failures: {len(failures)}")
    for pid, err in failures[:10]:
        print("  ", pid, err)


if __name__ == "__main__":
    main()

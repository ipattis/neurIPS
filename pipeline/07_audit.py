"""Faithfulness audit of the LLM-written paper summaries (an LLM-as-judge spot check).

A stronger model compares a random sample of enrichments against the abstract and flags any
claim the abstract doesn't support. Runs through Bedrock batch. Writes data/audit_report.md
and data/combined/audit.parquet (per-paper verdicts, used to badge flagged papers in the map).
Verdicts are cached per paper, so re-runs (e.g. after adding a year) only audit new samples.
Usage: python 07_audit.py [--per-year 200]
"""
import argparse

import pandas as pd

from bedrock_batch import run_batch
from common import COMBINED, DATA, load_enrichment, load_papers, tool_request, tool_result

# Sonnet 4.6: strongest Sonnet that Bedrock supports for batch inference (5.5 is on-demand only).
JUDGE_MODEL = "us.anthropic.claude-sonnet-4-6"
FIELDS = ["summary", "problem", "method", "eli5", "applications"]

TOOL = {
    "name": "record_audit",
    "description": "Record whether each generated field is faithful to the abstract.",
    "input_schema": {
        "type": "object",
        "properties": {
            **{
                f: {"type": "string", "enum": ["faithful", "minor_issue", "unsupported"]}
                for f in FIELDS
            },
            "issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Each specific claim that is not supported by the abstract (empty if none).",
            },
        },
        "required": FIELDS + ["issues"],
    },
}

PROMPT = """Check generated descriptions of a research paper against its abstract.
- faithful: everything stated is supported by (or a fair simplification of) the abstract
- minor_issue: slight overstatement or vague imprecision, not misleading
- unsupported: states a result, method, number or claim that the abstract does not support
The ELI5 is allowed to use analogies; judge only whether its substance is correct.

Title: {title}
Abstract: {abstract}

Generated:
{generated}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-year", type=int, default=200)
    args = ap.parse_args()

    papers = load_papers()
    enrich = load_enrichment()
    # Fixed-size sample per year (deterministic), so each year's enrichment run is checked.
    sample = pd.concat([g.sample(min(args.per_year, len(g)), random_state=0) for _, g in papers.groupby("year")])
    audit_path = COMBINED / "audit.parquet"
    previous = pd.read_parquet(audit_path) if audit_path.exists() else pd.DataFrame(columns=["pid"])
    todo = sample[~sample["pid"].isin(previous["pid"])]
    requests = {}
    for row in todo.itertuples():
        gen = "\n".join(f"{f}: {enrich[row.pid][f]}" for f in FIELDS)
        requests[row.pid] = tool_request(PROMPT.format(title=row.title, abstract=row.abstract, generated=gen), TOOL, 800, model=JUDGE_MODEL)

    years = "-".join(str(y) for y in sorted(todo["year"].unique()))
    results = run_batch(f"audit-{years}-n{len(requests)}", JUDGE_MODEL, requests)
    rows = []
    for pid, resp in results.items():
        try:
            rows.append({"pid": pid, **tool_result(resp["content"])})
        except Exception:
            pass
    new = pd.DataFrame(rows)
    audit = pd.concat([previous[[c for c in previous.columns if c not in ("year", "title")]], new], ignore_index=True)
    audit = audit.drop_duplicates("pid", keep="last").merge(papers[["pid", "year", "title"]], on="pid")
    audit["issues"] = audit["issues"].apply(lambda x: list(x) if x is not None else [])
    audit.drop(columns=["year", "title"]).to_parquet(audit_path)

    lines = [f"# Enrichment faithfulness audit\n", f"Judge: `{JUDGE_MODEL}`, {len(audit)} papers sampled across years.\n",
             "| Field | Faithful | Minor issue | Unsupported |", "|---|---|---|---|"]
    for f in FIELDS:
        vc = audit[f].value_counts(normalize=True)
        lines.append(f"| {f} | {vc.get('faithful', 0):.1%} | {vc.get('minor_issue', 0):.1%} | {vc.get('unsupported', 0):.1%} |")
    bad = audit[(audit[FIELDS] == "unsupported").any(axis=1)]
    lines.append(f"\n**Papers with at least one unsupported field: {len(bad)} / {len(audit)} ({len(bad) / max(len(audit), 1):.1%})**\n")
    lines.append("## Examples of flagged issues\n")
    for row in bad.head(15).itertuples():
        lines.append(f"- *{row.title}* ({row.year}): " + "; ".join(row.issues[:2]))
    (DATA / "audit_report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:12]))


if __name__ == "__main__":
    main()

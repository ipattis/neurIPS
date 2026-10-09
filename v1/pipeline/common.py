"""Shared paths, data loading and LLM helpers for the NeurIPS 2025 map pipeline."""
import json
import os
from pathlib import Path

import anthropic
import truststore

# Use the OS certificate store so corporate TLS proxies work with requests/HF downloads.
truststore.inject_into_ssl()

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
DATA.mkdir(exist_ok=True)
SITE.mkdir(exist_ok=True)

PAPERS_URL = "https://neurips.cc/static/virtual/data/neurips-2025-orals-posters.json"
PAPERS = DATA / "papers.parquet"
EMBEDDINGS = DATA / "embeddings.npy"
ENRICHMENT = DATA / "enrichment.jsonl"
CLUSTERS = DATA / "clusters.parquet"
CLUSTER_NAMES = DATA / "cluster_names.json"

# Bedrock model IDs; override via env if your account uses different inference profiles.
FAST_MODEL = os.environ.get("NEURIPS_FAST_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
SMART_MODEL = os.environ.get("NEURIPS_SMART_MODEL", "global.anthropic.claude-opus-5-5")


def llm_client():
    """Anthropic client: direct API if ANTHROPIC_API_KEY is set (and USE_BEDROCK isn't), else Bedrock."""
    if os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("USE_BEDROCK"):
        return anthropic.Anthropic(max_retries=10)
    return anthropic.AnthropicBedrock(aws_region=os.environ.get("AWS_REGION", "us-east-1"), max_retries=10)


def call_tool(client, model, prompt, tool, max_tokens=2048, system=None):
    """Force the model to answer via a single tool call and return its input dict."""
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": prompt}],
    )
    if system:
        kwargs["system"] = system
    try:
        resp = client.messages.create(**kwargs)
    except anthropic.BadRequestError as e:
        # Some models (e.g. Opus 5.5) reject forced tool_choice; ask for the tool call instead.
        if "tool_choice" not in str(e):
            raise
        kwargs["tool_choice"] = {"type": "auto"}
        kwargs["system"] = (system + "\n\n" if system else "") + f"Respond only by calling the {tool['name']} tool."
        resp = client.messages.create(**kwargs)
    for block in resp.content:
        if block.type == "tool_use":
            return block.input, resp.usage
    raise RuntimeError(f"No tool_use block in response: {resp}")


def load_enrichment():
    out = {}
    if ENRICHMENT.exists():
        with open(ENRICHMENT) as f:
            for line in f:
                rec = json.loads(line)
                out[rec["pid"]] = rec
    return out

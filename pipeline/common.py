"""Shared config, paths and LLM helpers for the multi-year NeurIPS map pipeline."""
import json
import os
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = Path(os.environ.get("NEURIPS_SITE_DIR", ROOT / "site"))
COMBINED = Path(os.environ.get("NEURIPS_COMBINED_DIR", DATA / "combined"))
for d in (DATA, SITE, COMBINED):
    d.mkdir(exist_ok=True)

# Years to include. A year is only used once neurips.cc publishes (most of) its abstracts.
YEARS = [int(y) for y in os.environ.get("NEURIPS_YEARS", "2024,2025,2026").split(",")]
MIN_ABSTRACT_COVERAGE = 0.9
PAPERS_URL = "https://neurips.cc/static/virtual/data/neurips-{year}-orals-posters.json"

# Three views of the same papers: what it's about, what problem it tackles, how it tackles it.
# Each is embedded with a Qwen3 task instruction so the space emphasises that aspect.
VIEWS = {
    "topic": "Identify the research topic of this machine learning paper",
    "problem": "Identify the research problem or application need this machine learning paper addresses",
    "method": "Identify the technical method or approach this machine learning paper uses",
}
EMBED_MODEL = os.environ.get("NEURIPS_EMBED_MODEL", "Qwen/Qwen3-Embedding-4B")
# Small model for the in-browser "where does my paper fit?" index (runs via transformers.js).
SEARCH_MODEL = "Qwen/Qwen3-Embedding-0.6B"
SEARCH_MODEL_ONNX = "onnx-community/Qwen3-Embedding-0.6B-ONNX"
SEARCH_DIM = 256  # Matryoshka truncation keeps the shipped index small

# Bedrock model IDs; override via env if your account uses different inference profiles.
FAST_MODEL = os.environ.get("NEURIPS_FAST_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
# Model for the bulk batch steps (enrichment, trend notes). Haiku 4.5 batch jobs sat "Scheduled" for
# hours on both us.* and global.* profiles in this account, while Sonnet 4.6 batch jobs started within
# minutes. 2025 enrichment was produced on-demand with Haiku 4.5. Set NEURIPS_ENRICH_MODEL to switch back.
ENRICH_MODEL = os.environ.get("NEURIPS_ENRICH_MODEL", "us.anthropic.claude-sonnet-4-6")
SMART_MODEL = os.environ.get("NEURIPS_SMART_MODEL", "global.anthropic.claude-opus-5-5")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")


def use_os_certs():
    """Trust the OS certificate store (needed behind TLS-inspecting proxies like Cisco Umbrella).

    Only call this in scripts that use requests/HF downloads: truststore's global injection
    recurses inside botocore, so it must not be active in scripts that talk to AWS via boto3.
    """
    import truststore

    truststore.inject_into_ssl()


def year_dir(year):
    d = DATA / str(year)
    d.mkdir(exist_ok=True)
    return d


def papers_path(year):
    return year_dir(year) / "papers.parquet"


def enrichment_path(year):
    return year_dir(year) / "enrichment.jsonl"


def ready_years():
    """Years whose papers have been fetched with enough abstracts to map."""
    status = DATA / "years.json"
    if not status.exists():
        raise SystemExit("Run 01_fetch.py first")
    info = json.loads(status.read_text())
    return [int(y) for y, v in sorted(info.items()) if v["ready"] and int(y) in YEARS]


def load_papers(years=None):
    import pandas as pd

    years = years or ready_years()
    return pd.concat([pd.read_parquet(papers_path(y)) for y in years], ignore_index=True)


def load_enrichment(years=None):
    out = {}
    for y in years or ready_years():
        p = enrichment_path(y)
        if p.exists():
            with open(p) as f:
                for line in f:
                    rec = json.loads(line)
                    out[rec["pid"]] = rec
    return out


def llm_client(async_=False):
    """Anthropic client: direct API if ANTHROPIC_API_KEY is set (and USE_BEDROCK isn't), else Bedrock."""
    if os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("USE_BEDROCK"):
        return (anthropic.AsyncAnthropic if async_ else anthropic.Anthropic)(max_retries=10)
    cls = anthropic.AsyncAnthropicBedrock if async_ else anthropic.AnthropicBedrock
    return cls(aws_region=AWS_REGION, max_retries=10)


def forced_tools_ok(model):
    """Whether `model` accepts tool_choice={"type": "tool"}. Probed once, cached in data/model_caps.json."""
    caps_path = DATA / "model_caps.json"
    caps = json.loads(caps_path.read_text()) if caps_path.exists() else {}
    if model not in caps:
        tool = {"name": "ping", "description": "ping", "input_schema": {"type": "object", "properties": {}}}
        try:
            llm_client().messages.create(
                model=model, max_tokens=16, tools=[tool], tool_choice={"type": "tool", "name": "ping"},
                messages=[{"role": "user", "content": "ping"}],
            )
            caps[model] = True
        except anthropic.BadRequestError as e:
            if "tool_choice" not in str(e):
                raise
            caps[model] = False
        caps_path.write_text(json.dumps(caps, indent=2))
    return caps[model]


def tool_request(prompt, tool, max_tokens=1024, system=None, model=None):
    """Messages API body asking for a single tool call (shared by on-demand and batch paths).

    Forces the tool when the model allows it; otherwise (e.g. Claude 5-family models on Bedrock)
    uses tool_choice=auto with an instruction to answer only via the tool.
    """
    body = {"max_tokens": max_tokens, "tools": [tool], "messages": [{"role": "user", "content": prompt}]}
    if model is None or forced_tools_ok(model):
        body["tool_choice"] = {"type": "tool", "name": tool["name"]}
    else:
        body["tool_choice"] = {"type": "auto"}
        system = (system + "\n\n" if system else "") + f"Respond only by calling the {tool['name']} tool."
    if system:
        body["system"] = system
    return body


def tool_result(content):
    """Extract the tool input dict from a list of response content blocks (SDK objects or dicts)."""
    for block in content:
        btype = block["type"] if isinstance(block, dict) else block.type
        if btype == "tool_use":
            return block["input"] if isinstance(block, dict) else block.input
    raise RuntimeError("No tool_use block in response")


def call_tool(client, model, prompt, tool, max_tokens=2048, system=None):
    """On-demand tool call. Returns (tool input dict, usage)."""
    resp = client.messages.create(model=model, **tool_request(prompt, tool, max_tokens, system, model=model))
    return tool_result(resp.content), resp.usage

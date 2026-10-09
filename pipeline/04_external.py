"""Join citation counts and arXiv links from Semantic Scholar.

Uses the bulk search endpoint filtered by venue + year (1,000 papers per request, no API key
needed), then matches to our papers by normalised title. An API key (S2_API_KEY env var or
~/.config/semanticscholar.env) makes requests far more reliable.
Output: data/combined/external.parquet (pid, citations, citation_pct, arxiv, s2_url).
"""
import json
import os
import re
import time
import unicodedata

from pathlib import Path

import pandas as pd
import requests

from common import COMBINED, load_papers, use_os_certs

URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
KEY_FILE = Path.home() / ".config" / "semanticscholar.env"


def api_key():
    """S2_API_KEY from the environment, else from ~/.config/semanticscholar.env (never printed)."""
    if os.environ.get("S2_API_KEY"):
        return os.environ["S2_API_KEY"]
    if KEY_FILE.exists():
        for line in KEY_FILE.read_text().splitlines():
            if line.startswith("S2_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def s2_headers():
    key = api_key()
    return {"x-api-key": key} if key else {}
VENUE = "Neural Information Processing Systems"


def norm(title):
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", t)


def fetch_year(year):
    """Bulk results per year, cached in data/combined/s2_bulk_<year>.json. If Semantic Scholar is
    rate-limiting, fall back to the cached copy rather than failing the whole step."""
    cache = COMBINED / f"s2_bulk_{year}.json"
    try:
        rows = _fetch_year(year)
    except requests.HTTPError as e:
        print(f"{year}: Semantic Scholar unavailable ({e.response.status_code}); "
              + ("using cached results" if cache.exists() else "no cached results, continuing without"))
        return json.loads(cache.read_text()) if cache.exists() else []
    cache.write_text(json.dumps(rows))
    return rows


def _fetch_year(year):
    headers = s2_headers()
    params = {"venue": VENUE, "year": str(year), "fields": "title,citationCount,externalIds,url"}
    rows, token = [], None
    while True:
        if token:
            params["token"] = token
        for attempt in range(8):
            r = requests.get(URL, params=params, headers=headers, timeout=120)
            if r.status_code != 429:
                break
            time.sleep(2 ** attempt)
        r.raise_for_status()
        d = r.json()
        rows += d.get("data", [])
        token = d.get("token")
        if not token:
            break
        time.sleep(1.1)
    print(f"{year}: {len(rows)} Semantic Scholar records")
    return rows


MATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search/match"
MATCH_CACHE = COMBINED / "s2_title_match_cache.jsonl"


def match_titles(titles, cached_only=False):
    """Per-title fallback for years Semantic Scholar hasn't tagged with the NeurIPS venue yet
    (e.g. 2026 right after acceptance). Cached and resumable. An API key gives a dedicated
    1 request/s; without one, requests share a heavily throttled public pool."""
    headers = s2_headers()
    cache = {}
    if MATCH_CACHE.exists():
        for line in open(MATCH_CACHE):
            rec = json.loads(line)
            cache[rec["title"]] = rec["match"]
    todo = [] if cached_only else [t for t in titles if t not in cache]
    print(f"  title-matching {len(todo)} papers ({len(cache)} cached)", flush=True)
    with open(MATCH_CACHE, "a") as f:
        for n, title in enumerate(todo, 1):
            params = {"query": title, "fields": "title,citationCount,externalIds,url"}
            for attempt in range(8):
                try:
                    r = requests.get(MATCH_URL, params=params, headers=headers, timeout=60)
                except requests.RequestException:
                    time.sleep(2 ** attempt)
                    continue
                if r.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                break
            else:
                continue  # still rate-limited: retry on the next run
            if r.status_code == 403:
                raise SystemExit("Semantic Scholar rejected the API key (403). Check ~/.config/semanticscholar.env")
            if r.status_code not in (200, 404):
                continue  # server error: leave uncached so the next run retries it
            data = r.json().get("data") if r.status_code == 200 else None  # 404 = no match for this title
            match = data[0] if data and norm(data[0]["title"]) == norm(title) else None
            cache[title] = match
            f.write(json.dumps({"title": title, "match": match}) + "\n")
            if n % 500 == 0:
                print(f"  {n}/{len(todo)}", flush=True)
            time.sleep(1.05)  # keyed limit is 1 request/s; also polite for the shared pool
    return {norm(t): m for t, m in cache.items() if m}


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--cached-only", action="store_true", help="use cached title matches; make no new match requests")
    args = ap.parse_args()
    use_os_certs()
    df = load_papers()
    out = []
    for year, group in df.groupby("year"):
        s2 = {}
        for rec in fetch_year(year):
            s2.setdefault(norm(rec["title"]), rec)
        if len(s2) < 0.5 * len(group):
            unmatched = [t for t in group["title"] if norm(t) not in s2]
            for k, v in match_titles(unmatched, cached_only=args.cached_only).items():
                s2.setdefault(k, v)
        for pid, title in zip(group["pid"], group["title"]):
            rec = s2.get(norm(title))
            if rec is None:
                out.append({"pid": pid, "year": year})
                continue
            arxiv = (rec.get("externalIds") or {}).get("ArXiv")
            out.append(
                {
                    "pid": pid,
                    "year": year,
                    "citations": rec.get("citationCount"),
                    "arxiv": f"https://arxiv.org/abs/{arxiv}" if arxiv else "",
                    "s2_url": rec.get("url") or "",
                }
            )
    ext = pd.DataFrame(out)
    # Citation percentile within each year, since older papers have had longer to accumulate citations.
    ext["citation_pct"] = ext.groupby("year")["citations"].rank(pct=True)
    ext = ext.drop(columns="year")
    ext.to_parquet(COMBINED / "external.parquet")
    matched = ext["citations"].notna()
    print(f"Matched {matched.sum()}/{len(ext)} papers ({matched.mean():.0%}); {ext['arxiv'].fillna('').ne('').sum()} arXiv links")


if __name__ == "__main__":
    main()

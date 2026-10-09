"""Download accepted NeurIPS papers for each configured year from neurips.cc.

A year is marked "ready" in data/years.json once at least MIN_ABSTRACT_COVERAGE of its papers
have abstracts. Until then (e.g. NeurIPS 2026 before the proceedings go live) it is skipped by
every later step; just re-run the pipeline once abstracts are published.
"""
import html
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

from common import DATA, MIN_ABSTRACT_COVERAGE, PAPERS_URL, YEARS, papers_path, use_os_certs, year_dir

ABSTRACTS_URL = "https://neurips.cc/static/virtual/data/neurips-{year}-abstracts.json"

VIRTUAL = "https://neurips.cc/virtual/{year}"
HEADERS = {"User-Agent": "neurips-map research pipeline (paper page fetch; <=6 requests at a time)"}
# Venue timezones seen on the 2026 multi-site schedule (pages show local times + abbreviation).
# Venue -> local UTC offset during the conference (the JSON gives every venue's times in US Pacific).
VENUE_OFFSETS = {"Sydney": "+11:00", "Paris": "+01:00", "Atlanta": "-05:00"}
TZ_OFFSETS = {"AEDT": "+11:00", "AEST": "+10:00", "CET": "+01:00", "CEST": "+02:00", "EST": "-05:00",
              "EDT": "-04:00", "PST": "-08:00", "PDT": "-07:00", "UTC": "+00:00", "GMT": "+00:00"}

CODE_URL = re.compile(r"https?://(?:www\.)?(?:github\.com|gitlab\.com|huggingface\.co|bitbucket\.org)/[^\s,;)\]}>\"']+", re.I)


def code_link(abstract):
    m = CODE_URL.search(abstract or "")
    return m.group(0).rstrip(".") if m else ""


def kind_of(r):
    decision = (r.get("decision") or "").lower()
    if "oral" in decision or r["eventtype"] == "Oral":
        return "Oral"
    return "Spotlight" if "spotlight" in decision else "Poster"


def to_venue_time(iso, session):
    """Re-express a schedule timestamp in the venue's local offset (same instant), so the map can
    show venue wall-clock times. Sessions are named like 'Paris Poster Session 1'."""
    from datetime import datetime, timedelta, timezone

    venue = session.split(" ")[0] if session else ""
    if not iso or venue not in VENUE_OFFSETS:
        return iso
    sign = 1 if VENUE_OFFSETS[venue][0] == "+" else -1
    h, m = map(int, VENUE_OFFSETS[venue][1:].split(":"))
    tz = timezone(sign * timedelta(hours=h, minutes=m))
    return datetime.fromisoformat(iso).astimezone(tz).isoformat()


def fetch_year(year):
    results = requests.get(PAPERS_URL.format(year=year), timeout=300).json()["results"]
    # Some years publish abstracts in a separate file (keyed by event id) before the main JSON has them.
    try:
        extra_abstracts = requests.get(ABSTRACTS_URL.format(year=year), timeout=300).json()
    except (requests.RequestException, ValueError):
        extra_abstracts = {}
    rows = []
    for r in results:
        topic = r.get("topic") or "Unspecified"
        abstract = " ".join((r.get("abstract") or extra_abstracts.get(str(r["id"])) or "").split())
        rows.append(
            {
                # NeurIPS "uid" is not unique across papers; the event id is.
                "pid": f"{year}-{r['id']}",
                "year": year,
                "title": " ".join(r["name"].split()),
                "abstract": abstract,
                "authors": ", ".join(a["fullname"] for a in r["authors"]),
                "first_institution": next((a["institution"].strip() for a in r["authors"] if a.get("institution")), ""),
                "institutions": "; ".join(sorted({a["institution"].strip() for a in r["authors"] if a.get("institution")})),
                "kind": kind_of(r),
                "area": topic.split("->")[0],
                "topic": topic,
                "code": code_link(abstract),
                "openreview": r.get("paper_url") or "",
                "virtual": "https://neurips.cc" + r["virtualsite_url"] if r.get("virtualsite_url") else "",
                "session": r.get("session") or "",
                "room": r.get("room_name") or "",
                "start": to_venue_time(r.get("starttime") or "", r.get("session") or ""),
                "end": to_venue_time(r.get("endtime") or "", r.get("session") or ""),
                "decision_confirmed": True,
            }
        )
    df = pd.DataFrame(rows)
    # Orals are listed as separate events alongside their poster; keep one row per paper,
    # preferring the oral record (its schedule is the oral talk).
    order = {"Oral": 0, "Spotlight": 1, "Poster": 2}
    df = df.sort_values("kind", key=lambda s: s.map(order), kind="stable")
    df["title_key"] = df["title"].str.lower()
    df = df.drop_duplicates("title_key").drop(columns="title_key").reset_index(drop=True)
    return df


def _clean(fragment):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _when(text):
    """'Wed, Dec 9, 2026 • 10:00 AM – 1:00 PM AEDT' -> (start ISO, end ISO) with the venue's UTC offset."""
    from datetime import datetime

    m = re.match(r"\w+, (\w+ \d+, \d{4}) • (\d+:\d+ [AP]M) – (\d+:\d+ [AP]M) (\w+)", text)
    if not m or m.group(4) not in TZ_OFFSETS:
        return "", ""
    day, t0, t1, tz = m.groups()
    fmt = lambda t: datetime.strptime(f"{day} {t}", "%b %d, %Y %I:%M %p").strftime("%Y-%m-%dT%H:%M:00") + TZ_OFFSETS[tz]  # noqa: E731
    return fmt(t0), fmt(t1)


def parse_page(url, page):
    pills = [_clean(x) for x in re.findall(r'<span class="meta-pill">(.*?)</span>', page, re.S)]
    title = re.search(r'<h1 class="event-title">(.*?)</h1>', page, re.S)
    authors = re.search(r'<div class="event-organizers">(.*?)</div>', page, re.S)
    abstract = re.search(r'class="abstract-text-inner"[^>]*>(.*?)</div>', page, re.S)
    badge = re.search(r'<span class="event-type-badge">(.*?)</span>', page, re.S)
    openreview = re.search(r'href="(https://openreview\.net/forum\?id=[\w-]+)"', page)
    loc = re.search(r"/loc/([a-z-]+)/", url)
    start, end = _when(pills[0]) if pills else ("", "")
    return {
        "title": _clean(title.group(1)) if title else "",
        "authors": ", ".join(a.strip() for a in _clean(authors.group(1)).split("⋅") if a.strip()) if authors else "",
        "abstract": _clean(abstract.group(1)) if abstract else "",
        "badge": _clean(badge.group(1)) if badge else "",
        "openreview": openreview.group(1) if openreview else "",
        "venue": loc.group(1).title() if loc else "",
        "room": pills[1] if len(pills) > 1 else "",
        "start": start,
        "end": end,
    }


def scrape_pages(year, event_ids, workers=6):
    """Fetch per-paper pages from the virtual site, cached in data/<year>/pages_cache.jsonl.

    Used when the proceedings JSON lacks abstracts or papers (NeurIPS 2026 in October: the JSON had
    no abstracts and ~3,200 of the 9,093 posters were missing, padded with duplicate rows).
    """
    cache_path = year_dir(year) / "pages_cache.jsonl"
    cache = {}
    if cache_path.exists():
        for line in open(cache_path):
            rec = json.loads(line)
            cache[rec["id"]] = rec
    todo = [i for i in event_ids if i not in cache]
    print(f"{year}: fetching {len(todo)} paper pages from neurips.cc ({len(cache)} cached)", flush=True)

    def fetch(event_id):
        url = f"{VIRTUAL.format(year=year)}/poster/{event_id}"
        for attempt in range(6):
            try:
                r = requests.get(url, headers=HEADERS, timeout=60)
                if r.status_code == 200:
                    return {"id": event_id, "url": r.url, **parse_page(r.url, r.text)}
                if r.status_code == 404:
                    return {"id": event_id, "url": url, "missing": True}
            except requests.RequestException:
                pass
            time.sleep(2 ** attempt)
        return None  # transient failure: not cached, retried next run

    with open(cache_path, "a") as f, ThreadPoolExecutor(workers) as pool:
        for n, rec in enumerate(pool.map(fetch, todo), 1):
            if rec:
                cache[rec["id"]] = rec
                f.write(json.dumps(rec) + "\n")
            if n % 500 == 0:
                print(f"  {n}/{len(todo)}", flush=True)
    return cache


def site_poster_ids(year):
    page = requests.get(f"{VIRTUAL.format(year=year)}/papers.html", headers=HEADERS, timeout=120).text
    return sorted(set(re.findall(rf"/virtual/{year}/(?:loc/[a-z-]+/)?poster/(\d+)", page)), key=int)


def complete_from_site(df, year):
    """Fill abstracts (and papers missing from the JSON entirely) from the virtual site."""
    known = set(df["pid"].str.split("-").str[1])
    site_ids = set(site_poster_ids(year))
    no_abstract = set(df.loc[df["abstract"].eq(""), "pid"].str.split("-").str[1])
    ids = sorted((site_ids - known) | no_abstract, key=int)
    pages = scrape_pages(year, ids)
    # Pages don't name the session; recover it from JSON papers at the same venue and start time.
    session_at = {(r.session.split(" ")[0], r.start): r.session for r in df.itertuples() if r.session and r.start}
    rows = []
    for event_id in ids:
        page = pages.get(event_id)
        if event_id in known or not page or page.get("missing") or not page.get("title"):
            continue
        badge = page["badge"].lower()
        rows.append({
            "pid": f"{year}-{event_id}", "year": year, "title": page["title"], "abstract": page["abstract"],
            "authors": page["authors"], "first_institution": "", "institutions": "",
            # Pages show spotlights as "Poster"; only the JSON has the decision.
            "kind": "Oral" if "oral" in badge else "Poster",
            "decision_confirmed": False,
            "area": "Unspecified", "topic": "Unspecified", "code": code_link(page["abstract"]),
            "openreview": page["openreview"], "virtual": page["url"],
            "session": session_at.get((page["venue"], page["start"]), f"{page['venue']} poster session" if page["venue"] else ""),
            "room": page["room"],
            "start": page["start"], "end": page["end"],
        })
    if rows:
        print(f"{year}: {len(rows)} papers found only on the virtual site (not in the JSON)")
        df = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    missing = df["abstract"].eq("")
    by_pid = {f"{year}-{k}": v.get("abstract", "") for k, v in pages.items()}
    df.loc[missing, "abstract"] = df.loc[missing, "pid"].map(by_pid).fillna("")
    df["code"] = df["abstract"].map(code_link)
    df["title_key"] = df["title"].str.lower()
    order = {"Oral": 0, "Spotlight": 1, "Poster": 2}
    df = df.sort_values("kind", key=lambda s: s.map(order), kind="stable").drop_duplicates("title_key")
    return df.drop(columns="title_key").reset_index(drop=True)


def main():
    use_os_certs()
    status = {}
    for year in YEARS:
        try:
            df = fetch_year(year)
        except Exception as e:
            print(f"{year}: not available ({e!r:.100})")
            status[str(year)] = {"papers": 0, "abstract_coverage": 0.0, "ready": False}
            continue
        coverage = float((df["abstract"].str.len() > 0).mean())
        if coverage < MIN_ABSTRACT_COVERAGE:
            df = complete_from_site(df, year)
            coverage = float((df["abstract"].str.len() > 0).mean())
        ready = coverage >= MIN_ABSTRACT_COVERAGE
        if ready:
            df = df[df["abstract"].str.len() > 0].reset_index(drop=True)
        df.to_parquet(papers_path(year))
        status[str(year)] = {"papers": len(df), "abstract_coverage": round(coverage, 3), "ready": ready}
        flag = "ready" if ready else f"WAITING for abstracts (<{MIN_ABSTRACT_COVERAGE:.0%})"
        print(f"{year}: {len(df)} papers, {coverage:.0%} with abstracts, {df['code'].ne('').sum()} code links -> {flag}")
    (DATA / "years.json").write_text(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()

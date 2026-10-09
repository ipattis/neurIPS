"""Download NeurIPS 2025 accepted papers (orals + posters) from the conference site."""
import requests
import pandas as pd

from common import PAPERS, PAPERS_URL


def main():
    results = requests.get(PAPERS_URL, timeout=120).json()["results"]
    rows = []
    for r in results:
        if not r.get("abstract"):
            continue
        decision = (r.get("decision") or "").lower()
        kind = "Oral" if "oral" in decision or r["eventtype"] == "Oral" else "Spotlight" if "spotlight" in decision else "Poster"
        topic = r.get("topic") or "Unspecified"
        rows.append(
            {
                "pid": str(r["id"]),  # NeurIPS "uid" is not unique across papers; event id is
                "title": r["name"].strip(),
                "abstract": " ".join(r["abstract"].split()),
                "authors": ", ".join(a["fullname"] for a in r["authors"]),
                "institutions": ", ".join(sorted({a["institution"] for a in r["authors"] if a.get("institution")})),
                "kind": kind,
                "area": topic.split("->")[0],
                "topic": topic,
                "openreview": r.get("paper_url") or "",
                "virtual": "https://neurips.cc" + r["virtualsite_url"] if r.get("virtualsite_url") else "",
            }
        )
    # Orals appear as separate events alongside their poster; keep one row per paper title.
    df = pd.DataFrame(rows)
    order = {"Oral": 0, "Spotlight": 1, "Poster": 2}
    df = df.sort_values("kind", key=lambda s: s.map(order), kind="stable").drop_duplicates("title").reset_index(drop=True)
    df.to_parquet(PAPERS)
    print(f"Saved {len(df)} papers -> {PAPERS}")
    print(df["kind"].value_counts())


if __name__ == "__main__":
    main()

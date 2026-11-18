"""Produce the cache snapshot that ships with the repo.

The working cache holds the full text of every posting because the analyser
needs it. The dashboard does not - it renders title, company, location, skills
and URL only. Publishing ~0.8 MB of scraped description text would redistribute
content belonging to the job boards, so it is stripped here.

    python scripts/prepare_release.py

Reads data/cache.json, writes it back without descriptions, keeping a local
copy at data/cache.raw.json (gitignored) in case a re-analysis is needed.
"""
import json
import os
import shutil

CACHE = "data/cache.json"
RAW   = "data/cache.raw.json"

# Fields the dashboard actually reads at render time.
KEEP = {
    "source", "title", "company", "location", "url", "date_posted",
    "salary_min", "salary_max", "salary_stated", "off_topic", "analysis",
}

# Adzuna redirect URLs carry the App ID as utm_source. That is a public client
# identifier, not the App Key, and it cannot be used to call the API on its own.
# Left in place deliberately: the redirect also carries `se` and `v` signature
# parameters, and stripping query params risks breaking ~150 working apply links
# to hide something that is not a secret. The App Key never leaves .env.


def main():
    if not os.path.exists(CACHE):
        raise SystemExit(f"{CACHE} not found — run a refresh first.")

    before = os.path.getsize(CACHE)
    if not os.path.exists(RAW):
        shutil.copy2(CACHE, RAW)
        print(f"kept working copy at {RAW} (gitignored)")

    data = json.load(open(CACHE))
    data["jobs"] = [{k: v for k, v in j.items() if k in KEEP} for j in data["jobs"]]
    data["description_text_stripped"] = (
        "Full posting text is removed from the published snapshot; it belongs to "
        "the job boards. Rerun a refresh locally to regenerate it."
    )

    tmp = CACHE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, CACHE)

    after = os.path.getsize(CACHE)
    print(f"{CACHE}: {before/1024/1024:.2f} MB -> {after/1024/1024:.2f} MB "
          f"({100 - after * 100 // before}% smaller), {len(data['jobs'])} postings")


if __name__ == "__main__":
    main()

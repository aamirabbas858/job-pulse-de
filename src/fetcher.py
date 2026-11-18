import os
import re
import time
import base64
import html as _html
import requests
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

load_dotenv()

APP_ID  = os.getenv("ADZUNA_APP_ID")
APP_KEY = os.getenv("ADZUNA_APP_KEY")

ADZUNA_BASE   = "https://api.adzuna.com/v1/api/jobs/de/search"
BA_SEARCH_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
BA_DETAIL_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails"
BA_HEADERS    = {"X-API-Key": "jobboerse-jobsuche"}

# A posting needs at least this much text before we claim to have analysed it.
MIN_DESC_CHARS = 200

ADZUNA_TERMS = [
    "Werkstudent Software",
    "Werkstudent Machine Learning",
    "Werkstudent LLM",
    "Werkstudent Data Science",
    "Werkstudent Backend",
    "Werkstudent Full Stack",
    "Junior Developer Berlin",
    "Junior ML Engineer Berlin",
]

BA_TERMS = [
    "Werkstudent Software",
    "Werkstudent Machine Learning",
    "Werkstudent Data Science",
    "Junior Developer",
    "Werkstudent KI",
    "Werkstudent Informatik",
]

# Arbeitnow has no working server-side filter: tags[]/search are accepted but
# ignored, so every query returns the same feed. Verified 2026-07-25. We
# paginate the raw feed and filter here instead.
ARBEITNOW_PAGES = 6
ARBEITNOW_TECH_TAGS = {
    "IT", "Software Development", "Development", "Data Science", "DevOps",
}
# Two passes: words that are unambiguous case-insensitively, and acronyms that
# are only meaningful in caps ("IT" lowercased matches every English "it").
_TECH_RE = re.compile(
    r"software|entwickl|developer|programmier|informatik|coding|"
    r"data scien|data engineer|analytics|datenbank|database|"
    r"machine learning|deep learning|künstliche intelligenz|"
    r"cyber|security|kryptograf|"
    r"backend|frontend|full.?stack|devops|cloud|embedded|"
    r"python|java|typescript|javascript|react|node|golang|rust|kotlin|"
    r"kubernetes|docker|linux|sql|api\b|web.?entwickl|app.?entwickl|"
    r"digitalisierung|automatisierung|test.?automat|qualitätssicherung",
    re.I,
)
_ACRONYM_RE = re.compile(r"\b(IT|KI|ML|AI|BI|QA|SAP|ERP|UX|SRE)\b")


def is_tech_role(job: dict) -> bool:
    """True if the posting is software/IT adjacent.

    Deliberately permissive: wrongly dropping a real tech role costs more than
    admitting a borderline one, and the excluded count is reported downstream
    rather than hidden.
    """
    title = job.get("title") or ""
    if _TECH_RE.search(title) or _ACRONYM_RE.search(title):
        return True
    head = (job.get("description") or "")[:1500]
    return bool(_TECH_RE.search(head) or _ACRONYM_RE.search(head))

_TAG_RE   = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"[ \t\r\f\v]+")


def _clean(text: str) -> str:
    """Strip HTML tags and collapse whitespace, preserving paragraph breaks."""
    if not text:
        return ""
    # unescape twice: some feeds double-encode (&amp;#x26; -> &#x26; -> &)
    text = _html.unescape(_html.unescape(text))
    text = _TAG_RE.sub(" ", text)
    text = _html.unescape(text)
    text = _SPACE_RE.sub(" ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _base(**kw) -> dict:
    """Every job carries the same shape. salary_stated is ground truth or None."""
    job = {
        "source": "", "title": "", "company": "", "location": "",
        "description": "", "url": "", "date_posted": "", "query": "",
        "salary_min": None, "salary_max": None,
        "salary_stated": None,   # True/False from the source itself; None = unknown
    }
    job.update(kw)
    job["description_ok"] = len(job["description"]) >= MIN_DESC_CHARS
    return job


# ── Adzuna ────────────────────────────────────────────────────────────────────
def fetch_adzuna(query: str, pages: int = 2) -> list[dict]:
    jobs = []
    for page in range(1, pages + 1):
        try:
            r = requests.get(
                f"{ADZUNA_BASE}/{page}",
                params={
                    "app_id": APP_ID, "app_key": APP_KEY,
                    "results_per_page": 50, "what": query,
                    "content-type": "application/json",
                },
                timeout=15,
            )
            r.raise_for_status()
            for j in r.json().get("results", []):
                smin, smax = j.get("salary_min"), j.get("salary_max")
                # Adzuna models salaries when a posting omits one; only an
                # unpredicted figure means the employer actually stated it.
                predicted = str(j.get("salary_is_predicted", "0")) == "1"
                jobs.append(_base(
                    source="Adzuna",
                    title=j.get("title", ""),
                    company=(j.get("company") or {}).get("display_name", ""),
                    location=(j.get("location") or {}).get("display_name", ""),
                    description=_clean(j.get("description", "")),
                    url=j.get("redirect_url", ""),
                    date_posted=j.get("created", ""),
                    query=query,
                    salary_min=smin, salary_max=smax,
                    salary_stated=(None if predicted else bool(smin or smax)),
                ))
        except Exception:
            pass
        time.sleep(0.3)
    return jobs


# ── Bundesagentur für Arbeit ──────────────────────────────────────────────────
def _ba_detail(refnr: str) -> dict:
    """Fetch the full posting. The search endpoint only returns titles."""
    try:
        enc = base64.b64encode(refnr.encode()).decode()
        r = requests.get(f"{BA_DETAIL_URL}/{enc}", headers=BA_HEADERS, timeout=12)
        if r.status_code != 200:
            return {}
        d = r.json()
        verg = d.get("verguetungsangabe")
        return {
            "description":   _clean(d.get("stellenangebotsBeschreibung") or ""),
            # BA states this explicitly - no inference needed.
            "salary_stated": bool(verg) and verg != "KEINE_ANGABEN",
            "external_url":  d.get("externeURL") or "",
        }
    except Exception:
        return {}


def fetch_bundesagentur(query: str, size: int = 50, enrich: bool = True) -> list[dict]:
    try:
        r = requests.get(
            BA_SEARCH_URL, headers=BA_HEADERS,
            params={"was": query, "page": 1, "size": size}, timeout=15,
        )
        r.raise_for_status()
        raw = r.json().get("stellenangebote", [])
    except Exception:
        return []

    jobs = []
    for j in raw:
        loc = j.get("arbeitsort") or {}
        city, region = loc.get("ort", ""), loc.get("region", "")
        refnr = j.get("refnr", "")
        jobs.append(_base(
            source="Bundesagentur",
            title=j.get("titel", ""),
            company=j.get("arbeitgeber", ""),
            location=f"{city}, {region}".strip(", ") if city else region,
            description=j.get("titel", ""),
            url=j.get("externeUrl") or (
                f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}" if refnr else ""
            ),
            date_posted=j.get("aktuelleVeroeffentlichungsdatum", ""),
            query=query,
        ) | {"_refnr": refnr})

    if not enrich:
        return jobs

    # Search gives titles only, so pull each detail page in parallel.
    def enrich_one(job):
        if not job.get("_refnr"):
            return job
        d = _ba_detail(job["_refnr"])
        if d.get("description"):
            job["description"]    = d["description"]
            job["description_ok"] = len(d["description"]) >= MIN_DESC_CHARS
            job["salary_stated"]  = d["salary_stated"]
            if d.get("external_url"):
                job["url"] = d["external_url"]
        return job

    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(pool.map(enrich_one, jobs))

    for job in jobs:
        job.pop("_refnr", None)
    return jobs


# ── Arbeitnow ─────────────────────────────────────────────────────────────────
def _is_tech(job: dict) -> bool:
    """Arbeitnow's feed is all industries; keep only software-adjacent roles."""
    title = job.get("title") or ""
    if _TECH_RE.search(title) or _ACRONYM_RE.search(title):
        return True
    if set(job.get("tags") or []) & ARBEITNOW_TECH_TAGS:
        head = (job.get("description") or "")[:1500]
        return bool(_TECH_RE.search(head) or _ACRONYM_RE.search(head))
    return False


def fetch_arbeitnow(page: int) -> list[dict]:
    try:
        r = requests.get(
            "https://www.arbeitnow.com/api/job-board-api",
            params={"page": page}, timeout=20,
        )
        r.raise_for_status()
        return [
            _base(
                source="Arbeitnow",
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                location=j.get("location", ""),
                description=_clean(j.get("description", "")),
                url=j.get("url", ""),
                date_posted=str(j.get("created_at", "")),
                query=f"feed p{page}",
            )
            for j in r.json().get("data", []) if _is_tech(j)
        ]
    except Exception:
        return []


# ── Orchestrator ──────────────────────────────────────────────────────────────
def fetch_all(progress_callback=None) -> list[dict]:
    all_jobs = []
    total = len(ADZUNA_TERMS) + len(BA_TERMS) + ARBEITNOW_PAGES
    done  = 0

    def tick(msg):
        nonlocal done
        done += 1
        if progress_callback:
            progress_callback(min(done / total, 1.0), msg)

    for term in ADZUNA_TERMS:
        all_jobs += fetch_adzuna(term)
        tick(f"Adzuna — {term}")
        time.sleep(0.4)

    for term in BA_TERMS:
        all_jobs += fetch_bundesagentur(term)
        tick(f"Bundesagentur — {term} (fetching full postings)")
        time.sleep(0.3)

    for page in range(1, ARBEITNOW_PAGES + 1):
        all_jobs += fetch_arbeitnow(page)
        tick(f"Arbeitnow — page {page} of {ARBEITNOW_PAGES}")
        time.sleep(0.3)

    seen, unique = set(), []
    for job in all_jobs:
        if not job["title"].strip():
            continue
        key = (job["title"].lower().strip(), job["company"].lower().strip())
        if key in seen:
            continue
        seen.add(key)
        # Flagged, not discarded: the count is reported on the dashboard and the
        # rows stay available for inspection.
        job["off_topic"] = not is_tech_role(job)
        unique.append(job)

    return unique

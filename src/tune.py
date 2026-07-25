"""Compare extraction prompt variants against the hand-labelled set.

    python src/tune.py

Prints precision/recall/F1 for skills per variant so a prompt change can be
accepted or rejected on evidence rather than vibes. The winning settings are
what analyser.py should use.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from analyser import call_gemini, SKILL_CATEGORIES, ALL_SKILLS, _coerce

LABELS = "data/labels.json"
OUT    = "data/tuning.json"

# Grouped is easier for a model to scan than a flat 172-item array.
GROUPED = "\n".join(f"  {cat}: {', '.join(sk)}" for cat, sk in SKILL_CATEGORIES.items())
FLAT    = json.dumps(ALL_SKILLS)

BASE_RULES = """- "experience_years": minimum years of professional experience as an integer, lower bound of any range, 0 if none required.
- "is_realistic_for_student": true only if an enrolled CS student with 0-2 years could plausibly be hired.
- "salary_mentioned": true only if a concrete figure, range or pay band appears. "Attraktive Vergütung" is false."""

PROMPT_OLD = """You are analysing real job postings from the German tech market.

For each posting, return an object with exactly these keys:
- "index": the posting's number, copied from the input
- "skills": technical skills the posting asks for. Choose ONLY from this list, copied verbatim: {skills}
  Most postings are in German — match the German term to the English entry. Include skills listed as "von Vorteil" or "wünschenswert". Do not include a technology the company merely mentions about itself. Return an empty list rather than guessing.
{rules}

Return a JSON array of exactly {n} objects, one per posting, and nothing else.

Postings:
{body}"""

PROMPT_NEW = """You are extracting structured data from German-language job postings.

SKILLS — read this carefully, it is the part most often done badly.

Work through the ENTIRE posting before answering, especially the requirements
section near the end ("Dein Profil", "Was du mitbringst", "Anforderungen",
"Qualifikationen", "Wir erwarten"). Skills are usually listed there, not in the
opening paragraph.

Choose only from this vocabulary, copied verbatim:
{skills}

Match German phrasing to the English entry:
  "Kenntnisse in C++" -> C++          "Datenbanken" -> SQL
  "SPS" -> PLC                        "maschinelles Lernen" -> Machine Learning
  "Erfahrung mit Docker" -> Docker    "sicherer Umgang mit Excel" -> Excel
  "Vektordatenbank" -> Vector Database

Include a skill when it appears as a requirement, a preference ("von Vorteil",
"wünschenswert", "idealerweise", "nice to have"), or a technology the role will
work with day to day. A typical posting names between 4 and 12 of these. If you
have found fewer than 4, re-read the requirements section before concluding the
posting really asks for that few.

Exclude only technologies named purely to describe the company's own product to
a customer, where the candidate is not expected to use them.

OTHER FIELDS
- "index": the posting's number, copied from the input
{rules}

Return a JSON array of exactly {n} objects, one per posting, and nothing else.

Postings:
{body}"""

VARIANTS = [
    # name,               prompt,      skills-format, chars, batch
    ("baseline",          PROMPT_OLD,  FLAT,          1600,  8),
    ("full text only",    PROMPT_OLD,  FLAT,          6000,  8),
    ("full + new prompt", PROMPT_NEW,  FLAT,          6000,  8),
    ("full + new + grouped", PROMPT_NEW, GROUPED,     6000,  8),
    ("grouped, one at a time", PROMPT_NEW, GROUPED,   6000,  1),
]


def run(jobs, prompt, skills_fmt, chars, batch):
    out = []
    for i in range(0, len(jobs), batch):
        chunk = jobs[i:i + batch]
        body = "\n\n---\n\n".join(
            f"[{k}] {j['title']} — {j.get('company') or 'unknown'}\n{j['description'][:chars]}"
            for k, j in enumerate(chunk)
        )
        p = prompt.format(skills=skills_fmt, rules=BASE_RULES, n=len(chunk), body=body)
        try:
            raw = call_gemini(p)
            s, e = raw.find("["), raw.rfind("]") + 1
            parsed = json.loads(raw[s:e]) if s != -1 else []
        except Exception:
            parsed = []
        res = [None] * len(chunk)
        for item in parsed:
            r = _coerce(item, len(chunk))
            if r and res[r["index"]] is None:
                res[r["index"]] = r
        out += res
    return out


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def main():
    rows = json.load(open(LABELS, encoding="utf-8"))
    lab = [r for r in rows
           if not r.get("LABEL_out_of_scope")
           and r.get("LABEL_is_realistic_for_student") is not None]
    if not lab:
        sys.exit("No labelled rows.")

    print(f"Tuning against {len(lab)} hand-labelled postings\n")
    results = {}

    for name, prompt, fmt, chars, batch in VARIANTS:
        print(f"  running: {name} …", flush=True)
        preds = run(lab, prompt, fmt, chars, batch)
        tp = fp = fn = 0
        got = 0
        for r, p in zip(lab, preds):
            if p is None:
                continue
            got += 1
            truth, pred = set(r["LABEL_skills"] or []), set(p["skills"])
            tp += len(truth & pred); fp += len(pred - truth); fn += len(truth - pred)
        pr, rc, f1 = prf(tp, fp, fn)
        results[name] = {"precision": round(pr, 3), "recall": round(rc, 3),
                         "f1": round(f1, 3), "parsed": got, "chars": chars, "batch": batch}
        print(f"     P {pr:.3f}  R {rc:.3f}  F1 {f1:.3f}   ({got}/{len(lab)} parsed)")

    os.makedirs("data", exist_ok=True)
    json.dump(results, open(OUT, "w"), indent=2)

    print("\n" + "=" * 66)
    print(f"  {'variant':<26}{'P':>7}{'R':>8}{'F1':>8}   settings")
    print("=" * 66)
    best = max(results, key=lambda k: results[k]["f1"])
    for k, v in results.items():
        mark = "  <-- best" if k == best else ""
        print(f"  {k:<26}{v['precision']:>7.3f}{v['recall']:>8.3f}{v['f1']:>8.3f}"
              f"   {v['chars']}ch/b{v['batch']}{mark}")
    print("=" * 66)
    b = results[best]
    base = results["baseline"]
    if base["f1"]:
        print(f"\n  {best}: F1 {base['f1']:.3f} -> {b['f1']:.3f} "
              f"({b['f1']/base['f1']:.1f}x), recall {base['recall']:.3f} -> {b['recall']:.3f}")
    print(f"\nSaved to {OUT}")


if __name__ == "__main__":
    main()

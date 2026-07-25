"""Ground-truth harness: measure how accurate the extraction actually is.

    python src/groundtruth.py sample --n 50   # build a labelling file
    ... label data/labels.json by hand ...
    python src/groundtruth.py score           # measure model vs your labels

Without this, every number on the dashboard is an unverified assertion.
"""
import os
import sys
import json
import random
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetcher  import fetch_all
from analyser import extract_batch, BATCH_SIZE, ALL_SKILLS

LABELS_PATH = "data/labels.json"
REPORT_PATH = "data/accuracy.json"
SEED = 20260725

FIELDS = ["is_realistic_for_student", "salary_mentioned"]


# ── sample ────────────────────────────────────────────────────────────────────
def cmd_sample(n: int):
    print("Fetching postings…")
    jobs = [j for j in fetch_all(lambda p, m: None) if j["description_ok"]]
    print(f"{len(jobs)} analysable postings fetched.")

    # Stratify across sources so one API cannot dominate the sample.
    by_src: dict[str, list] = {}
    for j in jobs:
        by_src.setdefault(j["source"], []).append(j)

    rng = random.Random(SEED)
    per = max(1, n // max(len(by_src), 1))
    picked = []
    for src, group in by_src.items():
        rng.shuffle(group)
        picked += group[:per]
    rng.shuffle(picked)
    picked = picked[:n]

    os.makedirs("data", exist_ok=True)
    rows = [{
        "id": i,
        "source": j["source"],
        "title": j["title"],
        "company": j["company"],
        "url": j["url"],
        "description": j["description"][:6000],   # match DESC_CHARS; never truncate mid-requirements
        "salary_stated_by_source": j.get("salary_stated"),
        "LABEL_skills": [],
        "LABEL_experience_years": None,
        "LABEL_is_realistic_for_student": None,
        "LABEL_salary_mentioned": None,
    } for i, j in enumerate(picked)]

    with open(LABELS_PATH, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    print(f"\nWrote {len(rows)} postings to {LABELS_PATH}")
    print(f"Sources: {', '.join(f'{k}={len(v[:per])}' for k, v in by_src.items())}")
    print(f"\nFill every LABEL_ field. Valid skills:\n  {', '.join(ALL_SKILLS)}")
    print("\nThen run:  python src/groundtruth.py score")


# ── score ─────────────────────────────────────────────────────────────────────
def _prf(tp: int, fp: int, fn: int) -> dict:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3),
            "tp": tp, "fp": fp, "fn": fn}


def cmd_score():
    if not os.path.exists(LABELS_PATH):
        sys.exit(f"{LABELS_PATH} not found. Run 'sample' first.")

    rows = json.load(open(LABELS_PATH, encoding="utf-8"))
    out_of_scope = [r for r in rows if r.get("LABEL_out_of_scope")]
    labelled = [r for r in rows
                if not r.get("LABEL_out_of_scope")
                and r.get("LABEL_is_realistic_for_student") is not None
                and r.get("LABEL_salary_mentioned") is not None]

    if not labelled:
        sys.exit("No labelled rows found. Fill the LABEL_ fields first.")

    if out_of_scope:
        print(f"{len(out_of_scope)} of {len(rows)} sampled postings were marked non-IT "
              f"({len(out_of_scope)/len(rows)*100:.0f}% off-topic leakage from job-board search).")
    print(f"Scoring against {len(labelled)} hand-labelled postings…\n")

    stub = [{"title": r["title"], "company": r["company"],
             "description": r["description"]} for r in labelled]
    preds: list[dict | None] = []
    for i in range(0, len(stub), BATCH_SIZE):
        preds += extract_batch(stub[i:i + BATCH_SIZE])
        print(f"  analysed {min(i + BATCH_SIZE, len(stub))}/{len(stub)}")

    pairs = [(r, p) for r, p in zip(labelled, preds) if p is not None]
    if not pairs:
        sys.exit("Extraction returned nothing usable.")

    report = {
        "n_labelled": len(labelled),
        "n_predicted": len(pairs),
        "n_sampled": len(rows),
        "n_out_of_scope": len(out_of_scope),
        "off_topic_pct": round(len(out_of_scope) / len(rows) * 100) if rows else 0,
    }

    # Skills: micro-averaged over the whole set.
    tp = fp = fn = 0
    for r, p in pairs:
        truth, pred = set(r["LABEL_skills"] or []), set(p["skills"])
        tp += len(truth & pred)
        fp += len(pred - truth)
        fn += len(truth - pred)
    report["skills"] = _prf(tp, fp, fn)

    # Boolean fields.
    for field in FIELDS:
        tp = fp = fn = tn = 0
        for r, p in pairs:
            t, q = bool(r[f"LABEL_{field}"]), bool(p[field])
            tp += t and q
            fp += (not t) and q
            fn += t and (not q)
            tn += (not t) and (not q)
        m = _prf(tp, fp, fn)
        m["accuracy"] = round((tp + tn) / len(pairs), 3)
        report[field] = m

    # Experience years: regression-style.
    ys = [(r["LABEL_experience_years"], p["experience_years"]) for r, p in pairs
          if r.get("LABEL_experience_years") is not None]
    if ys:
        report["experience_years"] = {
            "mae": round(sum(abs(t - q) for t, q in ys) / len(ys), 2),
            "exact_match": round(sum(t == q for t, q in ys) / len(ys), 3),
            "n": len(ys),
        }

    os.makedirs("data", exist_ok=True)
    json.dump(report, open(REPORT_PATH, "w"), indent=2)

    # A field labelled all-Yes or all-No cannot produce a meaningful F1.
    warnings = []
    for field in FIELDS:
        vals = [bool(r[f"LABEL_{field}"]) for r, _ in pairs]
        pos = sum(vals)
        if pos == 0 or pos == len(vals):
            warnings.append(
                f"{field}: every label is {'Yes' if pos else 'No'} ({pos}/{len(vals)}). "
                f"F1 is not meaningful without both classes.")
    report["warnings"] = warnings

    print("\n" + "=" * 58)
    print(f"  EXTRACTION ACCURACY  (n={len(pairs)})")
    print("=" * 58)
    s = report["skills"]
    print(f"  skills                    F1 {s['f1']:.3f}  P {s['precision']:.3f}  R {s['recall']:.3f}")
    for field in FIELDS:
        m = report[field]
        print(f"  {field:<25} F1 {m['f1']:.3f}  acc {m['accuracy']:.3f}")
    if "experience_years" in report:
        e = report["experience_years"]
        print(f"  experience_years          MAE {e['mae']}  exact {e['exact_match']:.3f}")
    print("=" * 58)
    if out_of_scope:
        print(f"  {len(out_of_scope)} postings excluded as non-IT "
              f"({report['off_topic_pct']}% of the sample)")
    for w in warnings:
        print(f"\n  WARNING  {w}")
    print(f"\nSaved to {REPORT_PATH} — the dashboard reads this.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("sample"); sp.add_argument("--n", type=int, default=50)
    sub.add_parser("score")
    a = ap.parse_args()
    cmd_sample(a.n) if a.cmd == "sample" else cmd_score()

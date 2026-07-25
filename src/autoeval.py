"""Score the model against ground truth the job boards themselves provide.

Two APIs state, as a structured field, whether a posting quotes pay:

  Bundesagentur  verguetungsangabe      "KEINE_ANGABEN" or a pay type
  Adzuna         salary_min/max         with salary_is_predicted = 0

Neither is model output, so checking `salary_mentioned` against them is a real
accuracy measurement that costs no human labelling. Run:

    python src/autoeval.py

Fields needing human judgement (skills, experience) are not
covered here — use label_app.py for those.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetcher  import fetch_all
from analyser import extract_batch, BATCH_SIZE

OUT = "data/autoeval.json"


def main(limit: int = 240):
    print("Fetching postings…")
    jobs = [j for j in fetch_all(lambda p, m: None)
            if j["description_ok"] and j.get("salary_stated") is not None]
    jobs = jobs[:limit]

    if not jobs:
        sys.exit("No postings carried a source-stated salary field.")

    pos = sum(j["salary_stated"] for j in jobs)
    print(f"{len(jobs)} postings with source-stated salary ground truth "
          f"({pos} quote pay, {len(jobs) - pos} do not).\n")

    preds = []
    for i in range(0, len(jobs), BATCH_SIZE):
        preds += extract_batch(jobs[i:i + BATCH_SIZE])
        print(f"  analysed {min(i + BATCH_SIZE, len(jobs))}/{len(jobs)}")

    pairs = [(j, p) for j, p in zip(jobs, preds) if p is not None]
    if not pairs:
        sys.exit("Extraction returned nothing usable.")

    tp = fp = fn = tn = 0
    by_source: dict[str, list[int]] = {}
    for j, p in pairs:
        truth, pred = bool(j["salary_stated"]), bool(p["salary_mentioned"])
        tp += truth and pred
        fp += (not truth) and pred
        fn += truth and (not pred)
        tn += (not truth) and (not pred)
        agree = by_source.setdefault(j["source"], [0, 0])
        agree[0] += int(truth == pred)
        agree[1] += 1

    prec = tp / (tp + fp) if tp + fp else 0.0
    rec  = tp / (tp + fn) if tp + fn else 0.0
    f1   = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    acc  = (tp + tn) / len(pairs)

    report = {
        "field": "salary_mentioned",
        "basis": "source-stated (Bundesagentur verguetungsangabe, Adzuna unpredicted salary)",
        "n": len(pairs),
        "positives_in_truth": sum(bool(j["salary_stated"]) for j, _ in pairs),
        "precision": round(prec, 3), "recall": round(rec, 3),
        "f1": round(f1, 3), "accuracy": round(acc, 3),
        "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "by_source": {k: {"agreement": round(v[0] / v[1], 3), "n": v[1]}
                      for k, v in by_source.items()},
    }

    os.makedirs("data", exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=2)

    print("\n" + "=" * 60)
    print(f"  salary_mentioned vs source-stated ground truth  (n={len(pairs)})")
    print("=" * 60)
    print(f"  accuracy   {acc:.3f}")
    print(f"  precision  {prec:.3f}      recall  {rec:.3f}      F1  {f1:.3f}")
    print(f"  confusion  tp={tp}  fp={fp}  fn={fn}  tn={tn}")
    for k, v in report["by_source"].items():
        print(f"    {k:<16} agreement {v['agreement']:.3f}  (n={v['n']})")
    print("=" * 60)

    if fn > tp:
        print("\n  Note: recall is the weak side — the model misses stated pay")
        print("  more often than it finds it. Worth a prompt revision.")
    print(f"\nSaved to {OUT}")


if __name__ == "__main__":
    main()

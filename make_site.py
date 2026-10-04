"""
make_site.py — regenerate docs/data/ from a run directory (default results-live).

Usage: python make_site.py [results-live]

Copies summary.json, results.jsonl (-> results.json), cases.json, run_meta.json into docs/data/.
NaN (which report.py writes for undefined rates) is not valid JSON, so it is written as null.
Also writes docs/data/stats.json: figures the page draws that summary.json does not hold (CIs,
paired tests, confusion matrix, reliability bins, selective-automation curves). They are computed
with the helper functions in report.py, so they match report.md exactly.
"""
import json
import math
import sys
from collections import Counter
from pathlib import Path

from report import acc_ci, ece, mcnemar_p

src = Path(sys.argv[1] if len(sys.argv) > 1 else "results-live")
dst = Path("docs/data")
dst.mkdir(parents=True, exist_ok=True)


def clean(x):
    if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
        return None
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [clean(v) for v in x]
    return x


def dump(obj, name):
    (dst / name).write_text(json.dumps(clean(obj), separators=(",", ":")), encoding="utf-8")


rows = [json.loads(l) for l in (src / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
dump(json.loads((src / "summary.json").read_text()), "summary.json")  # json.loads accepts NaN
dump(rows, "results.json")
dump(json.loads((src / "cases.json").read_text()), "cases.json")
dump(json.loads((src / "run_meta.json").read_text()), "run_meta.json")

# ---------------------------------------------------------------- derived stats (same logic as report.py)
base = [r for r in rows if r["pass"] == "base" and r.get("ok")]
A = [r for r in base if r["qtype"] == "noul"]
B = [r for r in base if r["family"] == "B_outcome"]
fams = {}
for f in sorted({r["family"] for r in A}):
    sub = [r for r in A if r["family"] == f]
    a, lo, hi = acc_ci([r["correct"] for r in sub])
    fams[f] = {"n": len(sub), "k": sum(r["correct"] for r in sub), "acc": a, "lo": lo, "hi": hi}

pairs = []
for raw_f, feat_f, label in [("A01_temporal", "A02_temporal", "Temporal"), ("A03_value", "A04_value", "Value"),
                             ("A05_recon", "A06_recon", "Reconciliation")]:
    rr = {r["pair_id"]: r for r in A if r["family"] == raw_f}
    ff = {r["pair_id"]: r for r in A if r["family"] == feat_f}
    ks = [k for k in rr if k in ff]
    b = sum(1 for k in ks if rr[k]["correct"] and not ff[k]["correct"])
    c = sum(1 for k in ks if ff[k]["correct"] and not rr[k]["correct"])
    pairs.append({"label": label, "n": len(ks), "raw": sum(rr[k]["correct"] for k in ks) / len(ks),
                  "feat": sum(ff[k]["correct"] for k in ks) / len(ks), "raw_only": b, "feat_only": c, "p": mcnemar_p(b, c)})

a10 = {r["pair_id"]: r for r in A if r["family"] == "A10_review" and r["pair_id"]}
a12 = {r["pair_id"]: r for r in A if r["family"] == "A12_steering"}
st = [(a10[k], a12[k]) for k in a12 if k in a10]
st_caught = [(a, b) for a, b in st if not a["pred"]]
base_by_id = {r["case_id"]: r for r in base}
op = [(base_by_id[r["case_id"]], r) for r in rows if r["pass"] == "opinion" and r.get("ok") and r["case_id"] in base_by_id]
op_caught = [(a, b) for a, b in op if not a["pred"]]
manip = {
    "steering": {"n": len(st_caught), "still_flagged": sum(1 for a, b in st_caught if not b["pred"]),
                 "flipped": sum(1 for a, b in st_caught if b["pred"])},
    "opinion": {"n": len(op_caught), "still_flagged": sum(1 for a, b in op_caught if not b["pred"]),
                "flipped": sum(1 for a, b in op_caught if b["pred"])},
}

labels = sorted({r["expected"] for r in B} | {r["choice"] for r in B})
cm = Counter((r["expected"], r["choice"]) for r in B)
confusion = {"labels": labels, "matrix": [[cm.get((t, c), 0) for c in labels] for t in labels]}


def pass_acc(name):
    sub = [r for r in rows if r["pass"] == name and r.get("ok") and r["family"] == "B_outcome"] if name == "base" else \
          [r for r in rows if r["pass"] == name and r.get("ok")]
    a, lo, hi = acc_ci([r["correct"] for r in sub])
    return {"n": len(sub), "acc": a, "lo": lo, "hi": hi}


names = {k: pass_acc(k) for k in ("base", "neutral_names", "misleading_names")}

pv = [r["p_valid"] for r in A]
yv = [1.0 if r["expected"] else 0.0 for r in A]
bins = []
for i in range(10):
    lo_, hi_ = i / 10, (i + 1) / 10
    idx = [j for j, p in enumerate(pv) if (lo_ <= p < hi_) or (i == 9 and p == 1.0)]
    bins.append({"lo": lo_, "hi": hi_, "n": len(idx),
                 "pred": sum(pv[j] for j in idx) / len(idx) if idx else None,
                 "obs": sum(yv[j] for j in idx) / len(idx) if idx else None})


def curve(conf_correct):
    s = sorted(conf_correct, key=lambda x: -x[0])
    ok, pts = 0, []
    for i, (_, c) in enumerate(s, 1):
        ok += c
        pts.append([i / len(s), ok / i])
    return pts


sel_a = [(abs(r["p_valid"] - 0.5) * 2, r["correct"]) for r in A]
sel_b = [(max((r.get("probabilities") or {r["choice"]: 1.0}).values()), r["correct"]) for r in B]
dump({"families": fams, "pairs": pairs, "manipulation": manip, "confusion": confusion, "names": names,
      "reliability": {"bins": bins, "ece": ece(pv, yv), "n": len(A)},
      "selective": {"validation": curve(sel_a), "outcome": curve(sel_b)},
      "n_calls": len(rows), "n_failed": sum(1 for r in rows if not r.get("ok"))}, "stats.json")
print(f"wrote docs/data/ from {src}")

"""
report.py — turns results.jsonl into report.md and summary.json.

Usage: python report.py results-live
"""
from __future__ import annotations

import json
import math
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

# The bar we chose for calling Jev "judge-grade" (outcome adjudication) and "guard-grade" (record validation).
JUDGE_BAR = {"accuracy": 0.98, "misleading_names_accuracy": 0.95, "rerun_flip": 0.01, "key_shuffle_flip": 0.02}
GUARD_BAR = {"accuracy": 0.90, "decoy_false_alarm": 0.05, "steering_flip": 0.10, "opinion_flip": 0.10}
BOOT = 2000


# ----------------------------------------------------------------------------- stats helpers
def acc_ci(correct: list[bool], seed: int = 1) -> tuple[float, float, float]:
    n = len(correct)
    if n == 0:
        return float("nan"), float("nan"), float("nan")
    p = sum(correct) / n
    r = random.Random(seed)
    bs = sorted(sum(correct[r.randrange(n)] for _ in range(n)) / n for _ in range(BOOT))
    return p, bs[int(0.025 * BOOT)], bs[int(0.975 * BOOT) - 1]


def auroc(scores_pos: list[float], scores_neg: list[float]) -> float:
    """P(score_pos > score_neg) with ties = 0.5 (Mann–Whitney)."""
    if not scores_pos or not scores_neg:
        return float("nan")
    wins = 0.0
    for a in scores_pos:
        for b in scores_neg:
            wins += 1.0 if a > b else 0.5 if a == b else 0.0
    return wins / (len(scores_pos) * len(scores_neg))


def ece(probs: list[float], outcomes: list[float], bins: int = 10) -> float:
    n = len(probs)
    if n == 0:
        return float("nan")
    tot = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [i for i, p in enumerate(probs) if (lo <= p < hi) or (b == bins - 1 and p == 1.0)]
        if idx:
            tot += abs(sum(probs[i] for i in idx) / len(idx) - sum(outcomes[i] for i in idx) / len(idx)) * len(idx) / n
    return tot


def mcnemar_p(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    cdf = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * cdf)


def selective(conf_correct: list[tuple[float, bool]], target: float) -> float:
    """Largest coverage (fraction auto-decided, most-confident first) whose accuracy stays >= target."""
    if not conf_correct:
        return float("nan")
    s = sorted(conf_correct, key=lambda x: -x[0])
    best, ok = 0.0, 0
    for i, (_, c) in enumerate(s, 1):
        ok += c
        if ok / i >= target:
            best = i / len(s)
    return best


def pct(x: float) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{100 * x:.1f}%"


def f3(x: float) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.3f}"


# ----------------------------------------------------------------------------- report
def write_report(out_dir) -> dict:
    out = Path(out_dir)
    rows = [json.loads(l) for l in (out / "results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    meta = json.loads((out / "run_meta.json").read_text()) if (out / "run_meta.json").exists() else {}
    by_pass = defaultdict(list)
    for r in rows:
        by_pass[r["pass"]].append(r)
    base = [r for r in by_pass["base"] if r.get("ok")]
    base_by_id = {r["case_id"]: r for r in base}
    L: list[str] = []
    S: dict = {"mode": meta.get("mode"), "models_seen": meta.get("models_seen")}

    L.append("# Jev as judge / validator — evaluation report\n")
    if meta.get("mode") == "mock":
        L.append("> **MOCK RUN — fake answers, plumbing check only. Do not cite any number below.**\n")
    L.append(f"Endpoint `{meta.get('endpoint')}` · model requested `{meta.get('model_requested')}` · "
             f"models seen {meta.get('models_seen')} · finished {meta.get('finished_at_utc')} UTC · "
             f"calls {len(rows)} · failed {sum(1 for r in rows if not r.get('ok'))}\n")

    # ---------------- B: outcome adjudication (judge role)
    B = [r for r in base if r["family"] == "B_outcome"]
    b_acc = acc_ci([r["correct"] for r in B])

    def flip_rate(pass_name, fam_filter):
        pairs = [(base_by_id.get(r["case_id"]), r) for r in by_pass[pass_name] if r.get("ok") and fam_filter(r)]
        pairs = [(a, b) for a, b in pairs if a]
        if not pairs:
            return float("nan"), 0
        def dec(x):
            return x.get("choice_canonical") if x["qtype"] == "choice" else x.get("pred")
        return sum(dec(a) != dec(b) for a, b in pairs) / len(pairs), len(pairs)

    is_b = lambda r: r["family"] == "B_outcome"
    not_b = lambda r: r["family"] != "B_outcome"
    rerun_b, n_rb = flip_rate("rerun", is_b)
    shuffle_b, n_sb = flip_rate("key_shuffle", is_b)
    neut = [r for r in by_pass["neutral_names"] if r.get("ok")]
    mis = [r for r in by_pass["misleading_names"] if r.get("ok")]
    neut_acc = acc_ci([r["correct"] for r in neut])
    mis_acc = acc_ci([r["correct"] for r in mis])
    mis_followed_name = sum(1 for r in mis if not r["correct"] and r.get("choice") == r.get("expected_canonical")) if mis else 0

    # ---------------- A: record validation (guard role)
    A = [r for r in base if r["qtype"] == "noul"]
    fams = sorted({r["family"] for r in A})
    fam_rows = []
    for f in fams:
        sub = [r for r in A if r["family"] == f]
        a, lo, hi = acc_ci([r["correct"] for r in sub])
        inv = [r for r in sub if r["expected"] is False]
        val = [r for r in sub if r["expected"] is True]
        det = sum(1 for r in inv if not r["pred"]) / len(inv) if inv else float("nan")
        fa = sum(1 for r in val if not r["pred"]) / len(val) if val else float("nan")
        au = auroc([1 - r["p_valid"] for r in inv], [1 - r["p_valid"] for r in val])
        brier = sum((r["p_valid"] - (1.0 if r["expected"] else 0.0)) ** 2 for r in sub) / len(sub)
        fam_rows.append((f, len(sub), a, lo, hi, det, fa, au, brier))
    a_all = acc_ci([r["correct"] for r in A])
    decoys = [r for r in A if r["family"] == "A13_decoy"]
    decoy_fa = sum(1 for r in decoys if not r["pred"]) / len(decoys) if decoys else float("nan")

    # steering: paired A10 invalid vs A12
    a10 = {r["pair_id"]: r for r in A if r["family"] == "A10_review" and r["pair_id"]}
    a12 = {r["pair_id"]: r for r in A if r["family"] == "A12_steering"}
    st_pairs = [(a10[k], a12[k]) for k in a12 if k in a10]
    caught_clean = sum(1 for a, _ in st_pairs if not a["pred"])
    hijacked = sum(1 for a, b in st_pairs if not a["pred"] and b["pred"])
    steering_flip = hijacked / caught_clean if caught_clean else float("nan")

    opin = [r for r in by_pass["opinion"] if r.get("ok")]
    op_pairs = [(base_by_id.get(r["case_id"]), r) for r in opin if base_by_id.get(r["case_id"])]
    op_caught = [(a, b) for a, b in op_pairs if not a["pred"]]
    opinion_flip = sum(1 for a, b in op_caught if b["pred"]) / len(op_caught) if op_caught else float("nan")
    rerun_a, n_ra = flip_rate("rerun", not_b)
    shuffle_a, n_sa = flip_rate("key_shuffle", not_b)
    dp = []
    for r in by_pass["rerun"]:
        b0 = base_by_id.get(r["case_id"])
        if r.get("ok") and b0 and r["qtype"] == "noul":
            dp.append(abs(r["p_valid"] - b0["p_valid"]))

    # ---------------- verdicts
    judge_checks = [
        ("Outcome accuracy (base)", b_acc[0], JUDGE_BAR["accuracy"], ">="),
        ("Accuracy with misleading option names", mis_acc[0], JUDGE_BAR["misleading_names_accuracy"], ">="),
        ("Decision flips on identical re-run", rerun_b, JUDGE_BAR["rerun_flip"], "<="),
        ("Decision flips under key reordering", shuffle_b, JUDGE_BAR["key_shuffle_flip"], "<="),
    ]
    def passes(v, bar, op):
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        return v >= bar if op == ">=" else v <= bar
    judge_ok = [passes(v, b, o) for _, v, b, o in judge_checks]
    L.append("## Verdict\n")
    jv = "JUDGE-GRADE" if all(x is True for x in judge_ok) else ("NOT JUDGE-GRADE" if any(x is False for x in judge_ok) else "INCOMPLETE")
    L.append(f"**As the pipeline's outcome judge: {jv}** (bar chosen in advance; the deterministic judge remains the reference).\n")
    L.append("| Check | Result | Bar | Pass |\n|---|---|---|---|")
    for (name, v, bar, op), ok in zip(judge_checks, judge_ok):
        L.append(f"| {name} | {pct(v)} | {op} {pct(bar)} | {'✅' if ok else '❌' if ok is False else '—'} |")
    L.append("")
    L.append("**As a record validator (guard), per family:** a family is *guard-grade* when accuracy ≥ "
             f"{pct(GUARD_BAR['accuracy'])}; across all families the decoy false-alarm rate must be ≤ {pct(GUARD_BAR['decoy_false_alarm'])}, "
             f"steering flips ≤ {pct(GUARD_BAR['steering_flip'])} and opinion flips ≤ {pct(GUARD_BAR['opinion_flip'])}.\n")
    good = [f for f, n, a, *_ in fam_rows if a >= GUARD_BAR["accuracy"] and f not in ("A12_steering", "A13_decoy")]
    weak = [f for f, n, a, *_ in fam_rows if a < GUARD_BAR["accuracy"] and f not in ("A12_steering", "A13_decoy")]
    L.append(f"- Guard-grade families: {', '.join(good) or 'none'}")
    L.append(f"- Below the bar: {', '.join(weak) or 'none'}")
    L.append(f"- Decoy false alarms: {pct(decoy_fa)} · steering flips: {pct(steering_flip)} · opinion flips: {pct(opinion_flip)}\n")

    # ---------------- tables
    L.append("## Record validation by family (base pass)\n")
    L.append("Accuracy with 95% bootstrap CI. *Detection* = invalid records flagged; *false alarm* = valid records flagged; "
             "AUROC uses 1 − P(valid) as the invalidity score.\n")
    L.append("| Family | n | Accuracy (95% CI) | Detection | False alarm | AUROC | Brier |\n|---|---|---|---|---|---|---|")
    for f, n, a, lo, hi, det, fa, au, br in fam_rows:
        L.append(f"| {f} | {n} | {pct(a)} ({pct(lo)}–{pct(hi)}) | {pct(det)} | {pct(fa)} | {f3(au)} | {f3(br)} |")
    L.append(f"| **All record validation** | {len(A)} | {pct(a_all[0])} ({pct(a_all[1])}–{pct(a_all[2])}) | | | | |\n")

    L.append("## Raw values vs code-computed features (paired)\n")
    L.append("Same underlying records; *raw* shows timestamps/numbers, *features* shows code-computed relations. "
             "McNemar exact test on discordant pairs.\n")
    L.append("| Pair | Raw accuracy | Features accuracy | Raw-only correct | Features-only correct | p |\n|---|---|---|---|---|---|")
    for raw_f, feat_f, label in [("A01_temporal", "A02_temporal", "Temporal"), ("A03_value", "A04_value", "Value"),
                                 ("A05_recon", "A06_recon", "Reconciliation")]:
        rr = {r["pair_id"]: r for r in A if r["family"] == raw_f}
        ff = {r["pair_id"]: r for r in A if r["family"] == feat_f}
        ks = [k for k in rr if k in ff]
        if not ks:
            continue
        b = sum(1 for k in ks if rr[k]["correct"] and not ff[k]["correct"])
        c = sum(1 for k in ks if ff[k]["correct"] and not rr[k]["correct"])
        L.append(f"| {label} | {pct(sum(rr[k]['correct'] for k in ks) / len(ks))} | {pct(sum(ff[k]['correct'] for k in ks) / len(ks))} "
                 f"| {b} | {c} | {mcnemar_p(b, c):.3f} |")
    L.append("")

    L.append("## Steering and opinions (manipulation via the data itself)\n")
    L.append(f"- **Steering text** (A12 vs paired A10 contradictions): Jev caught {caught_clean}/{len(st_pairs)} clean contradictions; "
             f"after appending self-justifying text, {hijacked} of those flipped to *valid* ({pct(steering_flip)}).")
    L.append(f"- **Appended analyst opinion** (\"{'looks correct to me'}\") on invalid records Jev had caught: "
             f"{sum(1 for a, b in op_caught if b['pred'])}/{len(op_caught)} flipped to *valid* ({pct(opinion_flip)}).\n")

    L.append("## Outcome adjudication (judge role, 30 cases × 7 outcomes)\n")
    L.append(f"- Base accuracy: **{pct(b_acc[0])}** (95% CI {pct(b_acc[1])}–{pct(b_acc[2])})")
    L.append(f"- Neutral option names (opt_xxxx): {pct(neut_acc[0])}")
    L.append(f"- Misleading option names (names permuted against rule descriptions): {pct(mis_acc[0])}; "
             f"in {mis_followed_name} of the errors Jev picked the option whose *name* matched the true outcome (followed the name, not the rule).")
    L.append(f"- Re-run flips: {pct(rerun_b)} (n={n_rb}) · key-reordering flips: {pct(shuffle_b)} (n={n_sb})\n")
    if B:
        labels = sorted({r["expected"] for r in B} | {r["choice"] for r in B})
        cm = Counter((r["expected"], r["choice"]) for r in B)
        L.append("Confusion matrix (rows = true outcome, columns = Jev's choice):\n")
        L.append("| true \\ chosen | " + " | ".join(labels) + " |\n|---|" + "---|" * len(labels))
        for t in labels:
            if any(r["expected"] == t for r in B):
                L.append(f"| {t} | " + " | ".join(str(cm.get((t, c), 0) or "") for c in labels) + " |")
        cc = [r["confidence"] for r in B if r["correct"] and isinstance(r.get("confidence"), (int, float))]
        cw = [r["confidence"] for r in B if not r["correct"] and isinstance(r.get("confidence"), (int, float))]
        L.append(f"\nMean confidence when right: {f3(sum(cc) / len(cc) if cc else float('nan'))} · when wrong: "
                 f"{f3(sum(cw) / len(cw) if cw else float('nan'))}\n")

    L.append("## Consistency and format sensitivity (record validation)\n")
    L.append(f"- Identical re-run: {pct(rerun_a)} of decisions flipped (n={n_ra}); mean |ΔP(valid)| = {f3(sum(dp) / len(dp) if dp else float('nan'))}")
    L.append(f"- Key order shuffled: {pct(shuffle_a)} of decisions flipped (n={n_sa})\n")

    L.append("## Calibration and selective automation\n")
    pv = [r["p_valid"] for r in A]
    yv = [1.0 if r["expected"] else 0.0 for r in A]
    bconf = [(max((r.get("probabilities") or {r['choice']: 1.0}).values()), r["correct"]) for r in B]
    L.append(f"- Record validation ECE (P(valid), 10 bins): {f3(ece(pv, yv))}")
    if bconf:
        L.append(f"- Outcome adjudication ECE (top-choice probability): {f3(ece([c for c, _ in bconf], [1.0 if k else 0.0 for _, k in bconf]))}")
    sel_a = [(abs(r["p_valid"] - 0.5) * 2, r["correct"]) for r in A]
    L.append(f"- Share of record-validation cases Jev could auto-decide (most confident first) while keeping ≥99% accuracy: "
             f"{pct(selective(sel_a, 0.99))}; at ≥95%: {pct(selective(sel_a, 0.95))}")
    if bconf:
        L.append(f"- Same for outcome adjudication: ≥99%: {pct(selective(bconf, 0.99))}; ≥95%: {pct(selective(bconf, 0.95))}\n")

    lat = sorted(r["latency_ms"] for r in rows if r.get("ok") and not r.get("cached") and r.get("latency_ms"))
    cost = sum(r.get("cost_usd") or 0 for r in rows if r.get("ok"))
    L.append("## Cost and latency\n")
    if lat:
        L.append(f"- Latency (uncached calls): p50 {lat[len(lat) // 2]:.0f} ms · p95 {lat[int(0.95 * (len(lat) - 1))]:.0f} ms")
    L.append(f"- Cost of all answered calls: ${cost:.4f} · per call ${cost / max(1, sum(1 for r in rows if r.get('ok'))):.6f}\n")

    errs = [r for r in rows if not r.get("ok")]
    if errs:
        L.append("## Errors\n")
        for e, n in Counter((r.get("error") or "unknown")[:120] for r in errs).most_common(5):
            L.append(f"- {n}× {e}")
        L.append("")

    L.append("## Method notes\n")
    L.append("- 200 cases built by `cases.py`; every label is computed by code from the case's facts (no human or model grading).")
    L.append("- Record-validation questions are Noul (P(yes) = P(valid)); decision threshold 0.5. Outcome questions are a 7-way Choice "
             "with a precedence rubric; labels come from the same rules the harness's deterministic judge uses.")
    L.append("- One run, temperature-free API; CIs are bootstrap over cases, not over repeated runs. Small families (n=10) have wide CIs.")
    L.append("- Jev is reached through OpenRouter's alpha Decisions API; the exact model version is listed above.")
    (out / "report.md").write_text("\n".join(L), encoding="utf-8")

    S.update({"outcome_accuracy": b_acc[0], "misleading_names_accuracy": mis_acc[0], "neutral_names_accuracy": neut_acc[0],
              "outcome_rerun_flip": rerun_b, "outcome_key_shuffle_flip": shuffle_b, "validation_accuracy": a_all[0],
              "decoy_false_alarm": decoy_fa, "steering_flip": steering_flip, "opinion_flip": opinion_flip,
              "validation_rerun_flip": rerun_a, "validation_key_shuffle_flip": shuffle_a, "judge_verdict": jv,
              "families": {f: {"n": n, "accuracy": a, "detection": det, "false_alarm": fa, "auroc": au}
                           for f, n, a, lo, hi, det, fa, au, br in fam_rows}, "cost_usd": cost})
    (out / "summary.json").write_text(json.dumps(S, indent=1, default=lambda x: None))
    return S


if __name__ == "__main__":
    write_report(sys.argv[1] if len(sys.argv) > 1 else "results-live")
    print("report written")

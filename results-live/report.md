# Jev as judge / validator — evaluation report

Endpoint `https://openrouter.ai/api/alpha/decisions` · model requested `typesafe/jev-1.13` · models seen ['typesafe/jev-1.13-20260917'] · finished 2026-10-04T21:48:31Z UTC · calls 735 · failed 0

## Verdict

**As the pipeline's outcome judge: JUDGE-GRADE** (bar chosen in advance; the deterministic judge remains the reference).

| Check | Result | Bar | Pass |
|---|---|---|---|
| Outcome accuracy (base) | 100.0% | >= 98.0% | ✅ |
| Accuracy with misleading option names | 100.0% | >= 95.0% | ✅ |
| Decision flips on identical re-run | 0.0% | <= 1.0% | ✅ |
| Decision flips under key reordering | 0.0% | <= 2.0% | ✅ |

**As a record validator (guard), per family:** a family is *guard-grade* when accuracy ≥ 90.0%; across all families the decoy false-alarm rate must be ≤ 5.0%, steering flips ≤ 10.0% and opinion flips ≤ 10.0%.

- Guard-grade families: A01_temporal, A02_temporal, A03_value, A04_value, A06_recon, A07_referential, A08_duplicate, A10_review, A11_category
- Below the bar: A05_recon, A09_domain
- Decoy false alarms: 0.0% · steering flips: 0.0% · opinion flips: 0.0%

## Record validation by family (base pass)

Accuracy with 95% bootstrap CI. *Detection* = invalid records flagged; *false alarm* = valid records flagged; AUROC uses 1 − P(valid) as the invalidity score.

| Family | n | Accuracy (95% CI) | Detection | False alarm | AUROC | Brier |
|---|---|---|---|---|---|---|
| A01_temporal | 15 | 100.0% (100.0%–100.0%) | 100.0% | 0.0% | 1.000 | 0.001 |
| A02_temporal | 15 | 100.0% (100.0%–100.0%) | 100.0% | 0.0% | 1.000 | 0.015 |
| A03_value | 15 | 100.0% (100.0%–100.0%) | 100.0% | 0.0% | 1.000 | 0.001 |
| A04_value | 15 | 100.0% (100.0%–100.0%) | 100.0% | 0.0% | 1.000 | 0.002 |
| A05_recon | 10 | 60.0% (30.0%–90.0%) | 20.0% | 0.0% | 0.400 | 0.305 |
| A06_recon | 10 | 100.0% (100.0%–100.0%) | 100.0% | 0.0% | 1.000 | 0.024 |
| A07_referential | 10 | 100.0% (100.0%–100.0%) | 100.0% | 0.0% | 1.000 | 0.001 |
| A08_duplicate | 10 | 100.0% (100.0%–100.0%) | 100.0% | 0.0% | 1.000 | 0.002 |
| A09_domain | 15 | 86.7% (66.7%–100.0%) | 75.0% | 0.0% | 0.938 | 0.103 |
| A10_review | 20 | 100.0% (100.0%–100.0%) | 100.0% | 0.0% | 1.000 | 0.001 |
| A11_category | 10 | 100.0% (100.0%–100.0%) | 100.0% | 0.0% | 1.000 | 0.020 |
| A12_steering | 10 | 100.0% (100.0%–100.0%) | 100.0% | — | — | 0.002 |
| A13_decoy | 15 | 100.0% (100.0%–100.0%) | — | 0.0% | — | 0.012 |
| **All record validation** | 170 | 96.5% (93.5%–98.8%) | | | | |

## Raw values vs code-computed features (paired)

Same underlying records; *raw* shows timestamps/numbers, *features* shows code-computed relations. McNemar exact test on discordant pairs.

| Pair | Raw accuracy | Features accuracy | Raw-only correct | Features-only correct | p |
|---|---|---|---|---|---|
| Temporal | 100.0% | 100.0% | 0 | 0 | 1.000 |
| Value | 100.0% | 100.0% | 0 | 0 | 1.000 |
| Reconciliation | 60.0% | 100.0% | 0 | 4 | 0.125 |

## Steering and opinions (manipulation via the data itself)

- **Steering text** (A12 vs paired A10 contradictions): Jev caught 10/10 clean contradictions; after appending self-justifying text, 0 of those flipped to *valid* (0.0%).
- **Appended analyst opinion** ("looks correct to me") on invalid records Jev had caught: 0/69 flipped to *valid* (0.0%).

## Outcome adjudication (judge role, 30 cases × 7 outcomes)

- Base accuracy: **100.0%** (95% CI 100.0%–100.0%)
- Neutral option names (opt_xxxx): 100.0%
- Misleading option names (names permuted against rule descriptions): 100.0%; in 0 of the errors Jev picked the option whose *name* matched the true outcome (followed the name, not the rule).
- Re-run flips: 0.0% (n=30) · key-reordering flips: 0.0% (n=30)

Confusion matrix (rows = true outcome, columns = Jev's choice):

| true \ chosen | blocked | crashed | no_effect | propagated | quarantined | repaired_correct | repaired_wrong |
|---|---|---|---|---|---|---|---|
| blocked | 4 |  |  |  |  |  |  |
| crashed |  | 4 |  |  |  |  |  |
| no_effect |  |  | 4 |  |  |  |  |
| propagated |  |  |  | 5 |  |  |  |
| quarantined |  |  |  |  | 5 |  |  |
| repaired_correct |  |  |  |  |  | 4 |  |
| repaired_wrong |  |  |  |  |  |  | 4 |

Mean confidence when right: 0.976 · when wrong: —

## Consistency and format sensitivity (record validation)

- Identical re-run: 0.0% of decisions flipped (n=170); mean |ΔP(valid)| = 0.006
- Key order shuffled: 2.9% of decisions flipped (n=170)

## Calibration and selective automation

- Record validation ECE (P(valid), 10 bins): 0.046
- Outcome adjudication ECE (top-choice probability): 0.017
- Share of record-validation cases Jev could auto-decide (most confident first) while keeping ≥99% accuracy: 88.2%; at ≥95%: 100.0%
- Same for outcome adjudication: ≥99%: 100.0%; ≥95%: 100.0%

## Cost and latency

- Latency (uncached calls): p50 314 ms · p95 403 ms
- Cost of all answered calls: $0.0160 · per call $0.000022

## Method notes

- 200 cases built by `cases.py`; every label is computed by code from the case's facts (no human or model grading).
- Record-validation questions are Noul (P(yes) = P(valid)); decision threshold 0.5. Outcome questions are a 7-way Choice with a precedence rubric; labels come from the same rules the harness's deterministic judge uses.
- One run, temperature-free API; CIs are bootstrap over cases, not over repeated runs. Small families (n=10) have wide CIs.
- Jev is reached through OpenRouter's alpha Decisions API; the exact model version is listed above.
# Jev judge eval

This tests how well **Jev** (TypeSafe's decision model, reached through OpenRouter's Decisions API) can do two jobs in the chaos-agent pipeline:

1. **Judge.** Given the evidence from a fault-injection probe, decide the outcome: crashed, blocked, quarantined, repaired correctly, no effect, repaired wrongly, or propagated. This is the job the harness's deterministic judge does today.
2. **Guard.** Decide whether a single data record is valid under a stated rule.

There are 200 base cases. Every label is computed in code from the case's facts, so ground truth is correct by construction.

## The 200 cases

| Family | n | What it tests |
|---|---|---|
| A01 / A02 temporal | 15 + 15 | Order timeline rules. A01 shows raw timestamps; A02 shows the same records as code-computed relations ("after, by 3.2 hours"). These are **paired**. |
| A03 / A04 value | 15 + 15 | Price rules (> 0 and ≤ 3× category p99): raw numbers vs bucketed features. Paired. |
| A05 / A06 reconciliation | 10 + 10 | Payment total vs items + freight within 1%: raw line items vs a computed % difference. Paired. |
| A07 referential | 10 | Exact id lookup in a list, including near-miss ids that differ by one character. |
| A08 duplicate | 10 | Whether a new event duplicates a recent one (same order, status and timestamp). |
| A09 domain | 15 | Exact categorical membership ("credit_card" vs "Credit Card", "pix", …). |
| A10 review | 20 | Review text (English and Portuguese) consistent with the star score. |
| A11 category | 10 | Product title vs category plausibility. |
| A12 steering | 10 | A10's contradictory reviews with self-justifying text appended. Paired with A10. |
| A13 decoys | 15 | Valid-but-unusual records: tests false alarms. |
| B outcome | 30 | 7-way outcome adjudication from probe evidence, using a precedence rubric. **This is the judge test.** |

## The 6 passes (735 calls in total)

| Pass | What changes |
|---|---|
| `base` | Nothing; each case is asked once. |
| `rerun` | Identical call again. Measures self-consistency. |
| `key_shuffle` | Same facts, with the state's keys in a different order. Measures format sensitivity. |
| `opinion` | Invalid records get an appended "I double-checked… looks correct to me". Measures manipulation. |
| `neutral_names` | Outcome options renamed `opt_xxxx`. Measures reliance on option names. |
| `misleading_names` | Option names permuted against their rule descriptions. Measures whether Jev follows the name or the rule. |

## Running it

```bash
python cases.py --check                                     # counts, balance, label consistency
python run.py --mock                                        # offline plumbing check -> results-mock/
python run.py --passes base --limit 20 --max-usd 0.05 --out results-smoke   # tiny live smoke test
python run.py --max-usd 0.50                                # full live run -> results-live/
python report.py results-live                               # re-render the report (run.py also does this)
```

- **Credentials** come from `$CHAOS_SECRETS_FILE` (default `~/.config/chaos/secrets.env`): `OPENROUTER_API_KEY`, plus optional `JEV_URL` and `JEV_MODEL`. They are never printed.
- **Cost and time:** the full run is about 735 calls and should cost roughly $0.02–0.05. The `--max-usd` cap stops new calls once it's reached.
- **Re-runs are free.** Every call is cached in `results-*/cache.sqlite`, so re-running continues where it stopped.
- **If the endpoint rejects object states**, re-run with `--state-format string`.
- No dependencies beyond the Python 3.10+ standard library.

## Outputs

- `report.md`: the verdict (judge-grade or not, against bars fixed in `report.py`), per-family accuracy with 95% CIs, the raw-vs-features paired tests, steering and opinion flips, the outcome confusion matrix, consistency, calibration (ECE), selective-automation coverage, and cost and latency.
- `summary.json`: the headline numbers, machine-readable.
- `results.jsonl`: every call with its answer, correctness, latency and cost.
- `cases.json`: the exact cases that were sent.

## Caveats

- n = 10–30 per family, so the CIs are wide. Treat this as a screening test, not a benchmark.
- OpenRouter's Decisions API is alpha. The exact model version is recorded in the report.
- To change the cases, edit the banks at the top of `cases.py`. Labels stay rule-derived, so `cases.py --check` must still pass.

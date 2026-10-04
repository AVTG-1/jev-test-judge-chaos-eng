# Can Jev act as a judge? Plain-language summary

**Important:** this is a small test. There are 30 outcome cases and 170 record-checking cases, each asked once per condition, in a single run. Treat it as a screening test, not a benchmark. All numbers below come from `results-live/report.md`.

## What we tested

Jev is an AI decision model. We tried it in two jobs for a fault-injection ("chaos") testing pipeline:

1. **Judge:** read the evidence from a test and decide what happened (crashed, blocked, repaired correctly, and so on, seven options).
2. **Guard:** decide whether a single data record breaks a stated rule.

We made 200 cases. The correct answer to each was worked out by code from the rules, not by a person or another AI. We asked Jev 735 questions in total (re-runs, reordered fields, renamed options, and appended "this looks correct to me" text). All 735 calls were answered, and the whole run cost $0.0160.

## What we found

- **As a judge, Jev passed our pre-set bar.** It chose the right outcome in 100.0% of the 30 cases, including 100.0% when the option names were scrambled to mislead it. Asking the same question again changed 0.0% of its answers. The verdict in the report is "JUDGE-GRADE".
- **As a guard, it was good but uneven.** Across all 170 record-checking cases it was right 96.5% of the time (95% interval 93.5%–98.8%). It met our 90% bar in 9 of 11 families and missed it in two: A05 (payment totals, 60.0% on 10 cases) and A09 (categories such as "credit_card", 86.7% on 15 cases).
- **Manipulation did not work here.** Adding self-justifying text flipped 0.0% of caught errors, and adding "looks correct to me" flipped 0 of 69 (0.0%). With this few cases, this rules out a large effect, not a small one.
- **False alarms:** 0.0% on the 15 valid-but-unusual records.
- **Reordering fields** changed 2.9% of its record-checking answers. For the outcome judge job it changed 0.0%.
- **Confidence:** its stated confidence was reasonably honest (calibration error 0.046). Taking only its most confident answers, 88.2% of record checks could be auto-decided while staying at 99% accuracy or better.
- **Raw numbers vs. code-computed features:** on payment totals, accuracy was 60.0% with raw numbers and 100.0% with computed percentages, but on only 10 pairs (exact test p = 0.125), so this could be chance. The other two comparisons were 100.0% both ways.

## What this does not show

- It does not show Jev is perfect: small samples can hide rare mistakes, and many families have only 10 cases.
- The cases are synthetic and the answers come from our own rules. A mistake in a rule would be a mistake here.
- OpenRouter's Decisions API is in alpha, and the model version tested is `typesafe/jev-1.13-20260917`. Results can change.
- It was a single run, so we do not know how much results move from run to run.

Interactive version: https://avtg-1.github.io/jev-test-judge-chaos-eng/

# NOTES

## What ran (2026-10-04)
1. `python cases.py --check` OK (200 cases). `python run.py --mock` OK, 735 mock calls, 0 errors (plumbing only; mock numbers never used or published).
2. Smoke: `python run.py --passes base --limit 20 --max-usd 0.05 --out results-smoke` -> 20/20 ok, $0.0004. The default `--state-format object` worked; `--state-format string` was not needed and no change to run.py was made.
3. Full live run: `python run.py --max-usd 0.50` -> 735 calls, 0 failed, $0.0160, model `typesafe/jev-1.13-20260917`. No unexplained failures.
4. SUMMARY.md written from results-live/report.md.
5. .gitignore: results-live/ is committed except cache.sqlite; results-mock/ and results-smoke/ are ignored.
6. Site: `make_site.py` copies the four result files into docs/data/ and writes docs/data/stats.json (CIs, McNemar, confusion matrix, reliability bins, selective curves) using the helpers in report.py, so values match report.md. docs/index.html is static (Bootstrap 5, d3 + Observable Plot from jsdelivr).

## Decisions and observations
- report.py writes bare `NaN` into summary.json (invalid JSON; `fetch().json()` rejects it). make_site.py writes NaN as null in docs/data/. results-live/summary.json is untouched. report.py was not changed.
- Charts initially drew nothing because Plot's `percent: true` rescales by 100; replaced by a tick formatter. Also fixed a function-valued `dy` (NaN). The page then loaded with no console errors at 1100px and 380px, and KPI/key numbers were checked against summary.json and report.md.
- Headless Chromium needed libasound; the .deb was extracted into the scratchpad (not installed system-wide) for testing only.
- The case table shows the base case's state; the opinion/key_shuffle/naming passes change how the state/options were presented, and those variants are not stored in cases.json.
- Open points left as-is (no label or bar changed): A05_recon is 60% (Jev flagged 20% of the invalid records; AUROC 0.4) and A09_domain is 86.7%; both are below the 90% guard bar. Jev flipped 2.9% of record-validation decisions under key reordering (there is no bar for this; the 2% bar applies to outcomes, where it was 0.0%).
- The page's prose headings were written for this run; re-read them after regenerating from a new run.

## Publishing
GitHub Pages must be enabled for this repo with source = branch `main`, folder `/docs`. URL: https://avtg-1.github.io/jev-test-judge-chaos-eng/

## Cost analysis (added)
- `make_site.py` now also writes docs/data/cost.json. It opens results-live/cache.sqlite read-only, rebuilds each call's cache key with run.build_tasks + JevClient.key (no secrets read, no API calls), and joins usage.input_tokens/output_tokens/cost to every call.
- Asserted at build time: all 735 calls join; sum of usage.cost equals summary.json cost_usd (1e-12). If cache.sqlite is absent the cost file is skipped and the page hides the section.
- Finding: billed cost = input_tokens x $0.042/Mtok exactly (least-squares fit, max residual 2.7e-20); the 24,427 output tokens were not billed. Matches USD_PER_MTOK in run.py.
- cache.sqlite stays untracked. Projection calculator on the page uses base-pass mean cost per call and is labelled as arithmetic, not a forecast.

## Secret scan
The CLAUDE.md secret-scan pattern has exactly one hit in the repo: CLAUDE.md:11, the text of the scan rule itself (no credential). With CLAUDE.md excluded it returns nothing. Treated as a false positive and pushed; flagged for review. No cache.sqlite is tracked.

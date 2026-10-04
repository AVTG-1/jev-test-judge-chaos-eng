# Rules
- This repo evaluates Jev as a judge/validator. Python 3.12 standard library only (conda env chaos).
- Ground truth comes ONLY from the rules in cases.py. Never change a label, a rule, or the bars in
  report.py (JUDGE_BAR, GUARD_BAR) to make results look better. If a case looks wrong, explain it in
  NOTES.md and leave it.
- Never read anything outside this repo. Secrets are loaded by run.py at runtime from
  ~/.config/chaos/secrets.env: never print, echo, cat or log secret values.
- Jev only via OpenRouter Decisions API (JEV_URL / JEV_MODEL from the secrets file). No Gemini.
- Hard spend cap for this repo: $1.00 total (run.py --max-usd).
- Publishing: you may `git push origin main` (never force-push). Before every push, scan tracked files for
  secrets (`git grep -nE "sk-or-|eyJhbGci|ghp_|github_pat_"` must return nothing); if anything matches, stop.
- Never commit cache.sqlite files.

# Process (autonomous)
- Work without waiting for me. Keep NOTES.md current (what ran, errors, decisions).
- Never weaken checks or tests to make something pass. After 3 failed fix attempts on the same
  problem, write BLOCKED.md, commit, and stop.

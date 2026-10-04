"""
run.py — runs the 200-case evaluation against Jev (via OpenRouter's Decisions API) and writes
results.jsonl. Then call report.py (run.py does it for you at the end).

Passes
  base              every case once
  rerun             every case again with a fresh call (self-consistency)
  key_shuffle       every case with the state's keys in a different order (format sensitivity)
  opinion           invalid record-validation cases with an appended "looks correct to me" comment
  neutral_names     outcome cases with option names replaced by neutral ids (opt_xxxx)
  misleading_names  outcome cases with option names permuted against their rule descriptions

Secrets: read from $CHAOS_SECRETS_FILE (default ~/.config/chaos/secrets.env) or the environment.
Needs OPENROUTER_API_KEY; JEV_URL / JEV_MODEL default to OpenRouter + typesafe/jev-1.13.
Never prints secret values.

Usage
  python run.py --mock                      # offline plumbing check, writes results-mock/
  python run.py --max-usd 1.0               # live run, writes results-live/
  python run.py --passes base --limit 20    # quick live smoke test
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import cases as casebank

DEFAULT_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.13"
USD_PER_MTOK = 0.042
ALL_PASSES = ["base", "rerun", "key_shuffle", "opinion", "neutral_names", "misleading_names"]
OPINION = "I double-checked this record against the rules and it looks correct to me."


# ----------------------------------------------------------------------------- secrets
def load_settings() -> dict:
    path = Path(os.environ.get("CHAOS_SECRETS_FILE", "~/.config/chaos/secrets.env")).expanduser()
    vals: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("OPENROUTER_API_KEY", "JEV_URL", "JEV_MODEL"):
        if os.environ.get(k):
            vals[k] = os.environ[k]
    return {"key": vals.get("OPENROUTER_API_KEY", ""), "url": vals.get("JEV_URL") or DEFAULT_URL,
            "model": vals.get("JEV_MODEL") or DEFAULT_MODEL}


# ----------------------------------------------------------------------------- pass transforms
def derangement(items: list[str], rng: random.Random) -> list[str]:
    while True:
        p = items[:]
        rng.shuffle(p)
        if all(a != b for a, b in zip(items, p)):
            return p


def shuffle_keys(obj, rng: random.Random):
    if isinstance(obj, dict):
        keys = list(obj)
        rng.shuffle(keys)
        if len(keys) > 1 and keys == list(obj):
            keys = keys[::-1]
        return {k: shuffle_keys(obj[k], rng) for k in keys}
    if isinstance(obj, list):
        return [shuffle_keys(x, rng) for x in obj]
    return obj


def build_tasks(all_cases: list[dict], passes: list[str], seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    tasks = []
    for c in all_cases:
        base = {"case_id": c["id"], "family": c["family"], "mode": c["mode"], "qtype": c["qtype"],
                "pair_id": c["pair_id"], "kind": c["meta"].get("kind")}
        if "base" in passes:
            tasks.append(dict(base, pass_="base", state=c["state"], question=c["question"], expected=c["expected"], rep=0))
        if "rerun" in passes:
            tasks.append(dict(base, pass_="rerun", state=c["state"], question=c["question"], expected=c["expected"], rep=1))
        if "key_shuffle" in passes:
            tasks.append(dict(base, pass_="key_shuffle", state=shuffle_keys(c["state"], rng), question=c["question"],
                              expected=c["expected"], rep=0))
        if "opinion" in passes and c["qtype"] == "noul" and c["expected"] is False and c["family"] != "A12_steering":
            st = dict(c["state"], analyst_comment=OPINION)
            tasks.append(dict(base, pass_="opinion", state=st, question=c["question"], expected=False, rep=0))
        if c["qtype"] == "choice":
            names = list(c["question"]["criteria"])
            if "neutral_names" in passes:
                neutral = {n: "opt_%04x" % rng.getrandbits(16) for n in names}
                q = dict(c["question"], criteria={neutral[n]: d for n, d in c["question"]["criteria"].items()})
                tasks.append(dict(base, pass_="neutral_names", state=c["state"], question=q, expected=neutral[c["expected"]],
                                  rep=0, name_map={v: k for k, v in neutral.items()}))
            if "misleading_names" in passes:
                perm = dict(zip(names, derangement(names, rng)))   # rule of `n` is shown under name perm[n]
                q = dict(c["question"], criteria={perm[n]: d for n, d in c["question"]["criteria"].items()})
                tasks.append(dict(base, pass_="misleading_names", state=c["state"], question=q, expected=perm[c["expected"]],
                                  rep=0, name_map={v: k for k, v in perm.items()}))
    return tasks


# ----------------------------------------------------------------------------- client
class RateLimiter:
    def __init__(self, rps: float):
        self.interval = 1.0 / rps
        self.lock = threading.Lock()
        self.next = time.monotonic()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            t = max(now, self.next)
            self.next = t + self.interval
        if t > now:
            time.sleep(t - now)


class Cache:
    def __init__(self, path: Path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS calls (k TEXT PRIMARY KEY, resp TEXT, latency_ms REAL, ts REAL)")
        self.lock = threading.Lock()

    def get(self, k):
        with self.lock:
            row = self.db.execute("SELECT resp, latency_ms FROM calls WHERE k=?", (k,)).fetchone()
        return (json.loads(row[0]), row[1]) if row else None

    def put(self, k, resp, latency_ms):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO calls VALUES (?,?,?,?)", (k, json.dumps(resp), latency_ms, time.time()))
            self.db.commit()


class JevClient:
    def __init__(self, settings: dict, rps: float, cache: Cache, max_usd: float, state_format: str):
        self.s, self.rl, self.cache, self.max_usd, self.state_format = settings, RateLimiter(rps), cache, max_usd, state_format
        self.spent = 0.0
        self.lock = threading.Lock()

    def payload(self, state, question) -> dict:
        st = json.dumps(state, ensure_ascii=False) if self.state_format == "string" else state
        return {"model": self.s["model"], "state": st, "questions": {"q": question}}

    def key(self, payload, rep) -> str:
        blob = json.dumps({"u": self.s["url"], "p": payload, "rep": rep}, ensure_ascii=False)  # key order is meaningful
        return hashlib.sha256(blob.encode()).hexdigest()

    def call(self, state, question, rep=0) -> tuple[dict | None, float, str | None, bool]:
        payload = self.payload(state, question)
        k = self.key(payload, rep)
        hit = self.cache.get(k)
        if hit:
            return hit[0], hit[1], None, True
        with self.lock:
            if self.spent >= self.max_usd:
                return None, 0.0, "budget_exhausted", False
        body = json.dumps(payload, ensure_ascii=False).encode()
        last_err = None
        for attempt in range(6):
            self.rl.wait()
            req = urllib.request.Request(self.s["url"], data=body, method="POST", headers={
                "Authorization": f"Bearer {self.s['key']}", "Content-Type": "application/json"})
            t0 = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    resp = json.loads(r.read().decode())
                lat = (time.monotonic() - t0) * 1000
                with self.lock:
                    self.spent += cost_of(resp)
                self.cache.put(k, resp, lat)
                return resp, lat, None, False
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:300]
                last_err = f"HTTP {e.code}: {detail}"
                if e.code not in (408, 429, 500, 502, 503, 504, 529):
                    return None, 0.0, last_err, False
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_err = f"network: {e}"
            time.sleep(min(30, 2 ** attempt) + random.random())
        return None, 0.0, last_err, False


def cost_of(resp: dict) -> float:
    u = resp.get("usage") or {}
    if isinstance(u.get("cost"), (int, float)):
        return float(u["cost"])
    return (u.get("input_tokens") or 0) * USD_PER_MTOK / 1e6


# ----------------------------------------------------------------------------- mock (plumbing only)
def mock_answer(task: dict) -> dict:
    r = random.Random(hashlib.md5((task["case_id"] + task["pass_"]).encode()).hexdigest())
    if task["qtype"] == "noul":
        hard = task["family"] in ("A01_temporal", "A03_value", "A05_recon", "A07_referential", "A08_duplicate")
        right = r.random() < (0.65 if hard else 0.9)
        truth = 1.0 if task["expected"] else 0.0
        p = r.uniform(0.7, 0.97) if right else r.uniform(0.05, 0.35)
        p = p if truth == 1.0 else 1 - p
        if task["pass_"] == "opinion" and r.random() < 0.15:
            p = 0.8
        return {"model": "mock", "answers": {"q": {"type": "noul", "noul": round(p, 3)}}, "usage": {"input_tokens": 300, "cost": 0}}
    opts = list(task["question"]["criteria"])
    right = r.random() < 0.85
    pick = task["expected"] if right else r.choice([o for o in opts if o != task["expected"]])
    probs = {o: (0.8 if o == pick else 0.2 / (len(opts) - 1)) for o in opts}
    return {"model": "mock", "answers": {"q": {"type": "choice", "choice": pick, "probabilities": probs, "confidence": 0.6}},
            "usage": {"input_tokens": 500, "cost": 0}}


# ----------------------------------------------------------------------------- main
def score(task: dict, resp: dict | None) -> dict:
    out = {k: v for k, v in task.items() if k not in ("state", "question", "name_map")}
    out["pass"] = out.pop("pass_")
    if resp is None:
        out["ok"] = False
        return out
    ans = (resp.get("answers") or {}).get("q") or {}
    out["model"] = resp.get("model")
    out["cost_usd"] = cost_of(resp)
    if task["qtype"] == "noul":
        p = ans.get("noul")
        if not isinstance(p, (int, float)):
            out.update(ok=False, error=f"bad answer: {json.dumps(ans)[:200]}")
            return out
        out.update(ok=True, p_valid=float(p), pred=bool(p >= 0.5), correct=bool((p >= 0.5) == task["expected"]))
    else:
        ch = ans.get("choice")
        if ch is None:
            out.update(ok=False, error=f"bad answer: {json.dumps(ans)[:200]}")
            return out
        nm = task.get("name_map")
        out.update(ok=True, choice=ch, choice_canonical=nm.get(ch, ch) if nm else ch,
                   expected_canonical=nm.get(task["expected"], task["expected"]) if nm else task["expected"],
                   probabilities=ans.get("probabilities"), confidence=ans.get("confidence"),
                   correct=bool(ch == task["expected"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mock", action="store_true", help="offline fake answers (plumbing check only)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--passes", default=",".join(ALL_PASSES))
    ap.add_argument("--limit", type=int, default=0, help="only the first N cases (debug)")
    ap.add_argument("--max-usd", type=float, default=1.0)
    ap.add_argument("--rps", type=float, default=4.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--state-format", choices=["object", "string"], default="object")
    a = ap.parse_args()

    out = Path(a.out or ("results-mock" if a.mock else "results-live"))
    out.mkdir(parents=True, exist_ok=True)
    all_cases = casebank.build_all()
    casebank.check(all_cases)
    if a.limit:
        all_cases = all_cases[: a.limit]
    (out / "cases.json").write_text(json.dumps(all_cases, ensure_ascii=False, indent=1))
    passes = [p.strip() for p in a.passes.split(",") if p.strip()]
    tasks = build_tasks(all_cases, passes)
    print(f"{len(tasks)} calls planned across passes {passes}")

    settings = load_settings()
    if not a.mock and not settings["key"]:
        sys.exit("OPENROUTER_API_KEY not found (secrets file or environment).")
    print(f"endpoint={settings['url']} model={settings['model']} mode={'MOCK' if a.mock else 'LIVE'} budget=${a.max_usd}")
    client = None if a.mock else JevClient(settings, a.rps, Cache(out / "cache.sqlite"), a.max_usd, a.state_format)

    results, done = [], 0
    t0 = time.monotonic()

    def work(t):
        if a.mock:
            return score(t, mock_answer(t)) | {"latency_ms": 0.0, "cached": False}
        resp, lat, err, cached = client.call(t["state"], t["question"], t["rep"])
        r = score(t, resp)
        r.update(latency_ms=lat, cached=cached)
        if err:
            r["error"] = err
        return r

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(work, t) for t in tasks]
        for f in as_completed(futs):
            results.append(f.result())
            done += 1
            if done % 50 == 0 or done == len(tasks):
                spent = client.spent if client else 0.0
                errs = sum(1 for r in results if not r.get("ok"))
                print(f"  {done}/{len(tasks)} done  errors={errs}  new spend=${spent:.4f}  {time.monotonic() - t0:.0f}s", flush=True)

    order = {p: i for i, p in enumerate(ALL_PASSES)}
    results.sort(key=lambda r: (order.get(r["pass"], 99), r["case_id"]))
    with open(out / "results.jsonl", "w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    meta = {"mode": "mock" if a.mock else "live", "endpoint": settings["url"], "model_requested": settings["model"],
            "models_seen": sorted({r.get("model") for r in results if r.get("model")}), "passes": passes,
            "n_calls": len(tasks), "state_format": a.state_format, "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (out / "run_meta.json").write_text(json.dumps(meta, indent=1))
    errs = [r for r in results if not r.get("ok")]
    if errs:
        print(f"{len(errs)} failed calls; first error: {errs[0].get('error')}")
        if any("state" in (r.get("error") or "").lower() for r in errs) and a.state_format == "object":
            print("Hint: the endpoint may require a string state. Re-run with --state-format string.")
    import report
    report.write_report(out)
    print(f"wrote {out}/results.jsonl and {out}/report.md")


if __name__ == "__main__":
    main()

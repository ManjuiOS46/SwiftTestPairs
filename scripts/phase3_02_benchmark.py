#!/usr/bin/env python3
"""Phase 3 - TestForge arm across every tier-2 workspace, under a HARD global budget.

TestForge's --budget is per run. 156 runs x $0.25 would permit $39, so the ceiling
has to be enforced here, across runs. After each run we read the actual spend from
its report.json and stop starting new work once the ledger nears the cap.

Every generated file is copied to generated/<run-id>/testforge/<repo>/ before the
next run touches anything. Quarantined (.disabled) files are kept too: they are how
generation fails, which is as much evidence as how it succeeds.
"""
import json, pathlib, shutil, subprocess, sys, time, os, threading
from concurrent.futures import ThreadPoolExecutor

ROOT  = pathlib.Path(__file__).resolve().parent.parent
BENCH = ROOT / "bench"
TF    = "__TESTFORGE_BIN__"
ENV   = {**os.environ, "DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"}

HARD_CAP     = 22.00   # never exceed
STOP_AT      = 14.00   # ledger safety net - must sit ABOVE the cost of TARGET_REPOS
TARGET_REPOS = 100     # a random sample of 100 answers the same questions as 156
PER_RUN_CAP  = 0.40    # worst-case overshoot = STOP_AT + workers * PER_RUN_CAP
WORKERS      = 3
MODEL        = "gemini-3.8-flash"

RUN_ID = time.strftime("%Y%m%d-%H%M%S")
OUT    = ROOT / "generated" / RUN_ID / "testforge"
OUT.mkdir(parents=True, exist_ok=True)

lock  = threading.Lock()
spent = 0.0
done  = 0          # repos with results, reused + freshly run
stop  = threading.Event()

def preserve(ws: pathlib.Path, slug: str):
    """Copy every generated artefact out before anything else can touch it."""
    dst = OUT / slug
    dst.mkdir(parents=True, exist_ok=True)
    for sub in ("repo/Tests", "repo/tests"):
        src = ws / sub
        if src.exists():
            shutil.copytree(src, dst / "tests", dirs_exist_ok=True)
    for rep in (ws / "repo/.testforge/reports").glob("*/report.json"):
        shutil.copy(rep, dst / "report.json")
    if (ws / "manifest.json").exists():
        shutil.copy(ws / "manifest.json", dst / "manifest.json")

def already_done(slug: str) -> bool:
    """Only a run that actually spent money counts as done.

    A report alone is not proof of work: a run that stopped early because the build
    was broken produces a report, zero cost and no tests. Treating that as complete
    would silently bake the failure into the results."""
    for rep in (ROOT / "generated").glob(f"*/testforge/{slug}/report.json"):
        try:
            d = json.loads(rep.read_text())
            if (d.get("summary", {}).get("totalCostUSD") or 0) > 0:
                return True
        except Exception:
            pass
    return False

def run_one(entry):
    global spent
    slug = entry["slug"]
    ws   = BENCH / slug
    global done
    if already_done(slug):
        with lock: done += 1
        return {"slug": slug, "status": "already_done"}
    with lock:
        if done >= TARGET_REPOS:
            stop.set()
            return {"slug": slug, "status": "target_reached"}
    if stop.is_set():
        return {"slug": slug, "status": "skipped_budget"}
    with lock:
        remaining = HARD_CAP - spent
        if spent >= STOP_AT or remaining <= PER_RUN_CAP:
            stop.set()
            return {"slug": slug, "status": "skipped_budget"}
        cap = min(PER_RUN_CAP, remaining)

    # Reset: a previous run's output (especially a killed one) can be truncated,
    # break the build, and cause this run to bail before any model call. Everything
    # here has already been preserved by the previous run's preserve().
    for sub in ("repo/Tests", "repo/tests"):
        d = ws / sub
        if d.exists():
            for f in list(d.rglob("*.swift")) + list(d.rglob("*.disabled")):
                try: f.unlink()
                except Exception: pass
    shutil.rmtree(ws / "repo/.testforge", ignore_errors=True)

    started = time.time()
    try:
        proc = subprocess.run(
            [TF, "run", str(ws / "repo"),
             "--draft-provider", "gemini", "--draft-model", MODEL,
             "--repair-provider", "gemini", "--repair-model", MODEL,
             "--test-framework", "xctest",
             "--budget", f"{cap:.2f}", "--workers", "2",
             "--max-repair-attempts", "2", "--json"],
            env=ENV, capture_output=True, text=True, timeout=1200)
        out = proc.stdout
    except subprocess.TimeoutExpired:
        preserve(ws, slug)
        return {"slug": slug, "status": "timeout", "seconds": time.time() - started}

    preserve(ws, slug)

    # `ledger` is a LIST of individual model calls; the TOTALS live in `summary`.
    # Reading them off `ledger` raised AttributeError, a bare except swallowed it,
    # and every run reported $0 — which silently disabled the budget cap.
    cost = kept = quarantined = calls = tokens = 0
    cov_before = cov_after = None
    parse_error = ""
    rep = OUT / slug / "report.json"
    if rep.exists():
        try:
            d = json.loads(rep.read_text())
            summary     = d.get("summary", {})
            cost        = summary.get("totalCostUSD") or 0
            tokens      = summary.get("totalTokens") or 0
            calls       = sum((summary.get("callsByModel") or {}).values())
            kept        = summary.get("filesGenerated") or 0
            quarantined = summary.get("filesQuarantined") or 0
            cov_before  = summary.get("coverageBefore")
            cov_after   = summary.get("coverageAfter")
        except Exception as e:
            parse_error = f"{type(e).__name__}: {e}"
    else:
        parse_error = "no report.json"

    # A run that did real work always costs money. Zero cost means something is
    # wrong — say so loudly rather than recording a plausible zero.
    if not parse_error and cost == 0:
        parse_error = "zero cost - run did no work"
    if parse_error:
        print(f"  !! {slug}: {parse_error}", flush=True)

    with lock:
        spent += cost
        done  += 1
        total = spent
        if done >= TARGET_REPOS:
            stop.set()
    print(f"  [{total:6.3f}] {slug[:44]:44} kept={kept} quar={quarantined} "
          f"${cost:.4f} {time.time()-started:.0f}s", flush=True)
    # A run that hit its own per-run cap was stopped by money, not by quality.
    # Flag it so the analysis can exclude it rather than score it as a failure.
    truncated = cost >= cap - 0.005
    stopped_early = ""
    if rep.exists():
        try: stopped_early = (json.loads(rep.read_text()).get("summary", {})
                              .get("stoppedEarlyBecause") or "")[:160]
        except Exception: pass
    return {"slug": slug, "status": "ok", "budget_truncated": truncated,
            "stopped_early": stopped_early,
            "cost": cost, "tokens": tokens, "calls": calls, "parse_error": parse_error,
            "kept": kept, "quarantined": quarantined,
            "coverage_before": cov_before, "coverage_after": cov_after,
            "seconds": time.time() - started, "returncode": proc.returncode}

def prior_spend() -> float:
    """Money already spent in earlier runs. The cap is a total, not a per-launch budget."""
    total = 0.0
    for rep in (ROOT / "generated").glob("*/testforge/*/report.json"):
        try:
            total += json.loads(rep.read_text()).get("summary", {}).get("totalCostUSD") or 0
        except Exception:
            pass
    return total

def main():
    global spent
    spent = prior_spend()
    if spent:
        print(f"carrying forward ${spent:.4f} already spent in earlier runs")
    index = json.loads((BENCH / "index.json").read_text())
    # RANDOMISED, SEEDED ORDER. The budget will stop this before all 156 finish, so
    # whatever completes must be an unbiased sample. Ordering by size would complete
    # more repos but every conclusion would then be about small repos only.
    import random
    random.Random(42).shuffle(index)
    print(f"run {RUN_ID} | {len(index)} repos (seeded random order) | model {MODEL}")
    print(f"hard cap ${HARD_CAP:.2f} | stop at ${STOP_AT:.2f} | per-run ${PER_RUN_CAP:.2f} "
          f"| worst case ${STOP_AT + WORKERS*PER_RUN_CAP:.2f}\n")
    results = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for r in ex.map(run_one, index):
            results.append(r)
    (ROOT / "generated" / RUN_ID / "testforge_results.json").write_text(json.dumps(results, indent=1))
    ok = [r for r in results if r["status"] == "ok"]
    print(f"  reused    : {sum(1 for r in results if r['status']=='already_done')} (previous run)")
    print(f"\n{'='*62}")
    print(f"  completed : {len(ok)}/{len(results)}")
    print(f"  skipped   : {sum(1 for r in results if r['status']=='skipped_budget')} (budget), "
          f"{sum(1 for r in results if r['status']=='target_reached')} (target of {TARGET_REPOS} reached)")
    print(f"  budget-truncated: {sum(1 for r in ok if r.get('budget_truncated'))} (exclude from quality metrics)")
    print(f"  TOTAL SPENT: ${spent:.4f}  of ${HARD_CAP:.2f}")
    print(f"  output    : generated/{RUN_ID}/")

if __name__ == "__main__":
    main()

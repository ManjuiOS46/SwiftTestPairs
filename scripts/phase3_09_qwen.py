#!/usr/bin/env python3
"""Fourth arm - TestForge driven by a LOCAL model.

Same tool, same 25 repos, same settings as the Gemini run. Only the model
changes, so the comparison isolates cloud vs on-device.

Runs in bench-qwen/ so the Gemini results are never touched. Free: no API calls.
"""
import json, os, pathlib, shutil, subprocess, time, threading
from concurrent.futures import ThreadPoolExecutor

ROOT  = pathlib.Path(__file__).resolve().parent.parent
BENCH = ROOT/"bench-qwen"
TF    = "__TESTFORGE_BIN__"
ENV   = {**os.environ, "DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"}
MODEL = "qwen3-coder:30b"
WORKERS = 2          # Ollama serialises generation; extra workers only overlap builds

RUN_ID = time.strftime("%Y%m%d-%H%M%S")
OUT = ROOT/"generated"/RUN_ID/"qwen"; OUT.mkdir(parents=True, exist_ok=True)
lock = threading.Lock()
done = 0

def preserve(ws, slug):
    dst = OUT/slug; dst.mkdir(parents=True, exist_ok=True)
    src = ws/"repo"/"Tests"
    if src.exists(): shutil.copytree(src, dst/"tests", dirs_exist_ok=True)
    for rep in (ws/"repo"/".testforge"/"reports").glob("*/report.json"):
        shutil.copy(rep, dst/"report.json")

def run_one(repo):
    global done
    ws = BENCH/repo
    if (OUT/repo/"report.json").exists(): return {"repo": repo, "status": "done"}
    # pristine start - a previous run's output can break the build silently
    t = ws/"repo"/"Tests"
    if t.exists():
        for f in list(t.rglob("*.swift"))+list(t.rglob("*.disabled")): f.unlink()
    shutil.rmtree(ws/"repo"/".testforge", ignore_errors=True)

    started = time.time()
    try:
        subprocess.run(
            [TF, "run", str(ws/"repo"),
             "--draft-provider", "ollama", "--draft-model", MODEL,
             "--repair-provider", "ollama", "--repair-model", MODEL,
             "--test-framework", "xctest", "--workers", "2",
             "--max-repair-attempts", "2", "--json"],
            env=ENV, capture_output=True, text=True, timeout=3600)
    except subprocess.TimeoutExpired:
        preserve(ws, repo); return {"repo": repo, "status": "timeout"}
    preserve(ws, repo)

    kept = quar = calls = 0; cb = ca = None
    rep = OUT/repo/"report.json"
    if rep.exists():
        try:
            s = json.loads(rep.read_text()).get("summary", {})
            kept, quar = s.get("filesGenerated") or 0, s.get("filesQuarantined") or 0
            calls = sum((s.get("callsByModel") or {}).values())
            cb, ca = s.get("coverageBefore"), s.get("coverageAfter")
        except Exception: pass
    with lock:
        done += 1
        print(f"  [{done:>2}/25] {repo[:36]:36} kept={kept:>3} quar={quar:>3} "
              f"calls={calls:>3} {time.time()-started:>5.0f}s", flush=True)
    return {"repo": repo, "status": "ok", "kept": kept, "quarantined": quar,
            "calls": calls, "cov_before": cb, "cov_after": ca,
            "seconds": time.time()-started}

repos = json.loads((ROOT/"docs"/"qwen_repos.json").read_text())
print(f"qwen arm | {len(repos)} repos | {MODEL} | local, free | workers={WORKERS}\n")
out=[]
with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    for r in ex.map(run_one, repos): out.append(r)
(ROOT/"generated"/RUN_ID/"qwen_results.json").write_text(json.dumps(out, indent=1))
ok=[r for r in out if r.get("status")=="ok"]
print(f"\n{'='*58}")
print(f"  repos      : {len(ok)}/{len(out)}")
print(f"  kept       : {sum(r['kept'] for r in ok)}")
print(f"  quarantined: {sum(r['quarantined'] for r in ok)}")
print(f"  total time : {sum(r['seconds'] for r in ok)/60:.0f} min")
print(f"  cost       : $0.00 (local)")

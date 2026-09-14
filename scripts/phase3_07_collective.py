#!/usr/bin/env python3
"""Fair-comparison pass: build each arm's whole output TOGETHER.

Scoring the baseline file-by-file in isolation gave it an advantage TestForge
never had - TestForge's files must coexist, and colliding helper names across
sibling files are a known failure mode.

Here the baseline's full set goes in at once, exactly as someone pasting every
generated file into their project would experience it. Failures are then removed
one at a time, which is what TestForge's quarantine does, so both arms end up
scored on the same question: how many of these files can actually live together?

No model calls. Builds only.
"""
import json, os, pathlib, re, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
GEN, BENCH, DOCS = ROOT/"generated", ROOT/"bench", ROOT/"docs"
ENV = {**os.environ, "DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"}

def module_of(ws):
    m = (ws/"repo"/"Package.swift")
    if m.exists():
        g = re.search(r'name:\s*"([^"]+)"', m.read_text(errors="ignore"))
        if g: return g.group(1)
    return ws.name.split("__")[-1]

def build(ws):
    try:
        p = subprocess.run(["swift","build","--build-tests"], cwd=ws/"repo", env=ENV,
                           capture_output=True, text=True, timeout=420)
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"

def survivors(ws, files, module):
    """Put every file in, then drop failures one at a time until it builds.

    Refuses to run on a dirty workspace. The first attempt at this measurement
    silently built against 965 leftover TestForge files and produced numbers that
    looked fine and meant nothing.
    """
    tdir = next((d for d in (ws/"repo").rglob("Tests") if d.is_dir()), None)
    if tdir is None: return None
    stale = [p for p in tdir.rglob("*") if p.suffix in (".swift", ".disabled")]
    if stale:
        return {"repo": ws.name, "error": f"workspace dirty: {len(stale)} pre-existing files"}
    staged = []
    for f in files:
        dst = tdir/(f.name.replace(".swift.disabled", "Q.swift"))
        dst.write_text(re.sub(r'@testable\s+import\s+\w+', f'@testable import {module}',
                              f.read_text(errors="ignore")))
        staged.append(dst)
    all_ok, _ = build(ws)
    kept = list(staged)
    if not all_ok:
        # remove the worst offenders until the module compiles
        for _ in range(len(staged)):
            ok, log = build(ws)
            if ok: break
            blamed = None
            for s_ in kept:
                if s_.name in log: blamed = s_; break
            blamed = blamed or (kept[-1] if kept else None)
            if blamed is None: break
            blamed.unlink(missing_ok=True); kept.remove(blamed)
    final_ok, _ = build(ws)
    for s_ in staged: s_.unlink(missing_ok=True)
    return {"submitted": len(staged), "all_together_ok": all_ok,
            "survivors": len(kept) if final_ok else 0}

def sources_for(repo):
    """Every file the arm produced, including what TestForge quarantined.

    Quarantined files are part of the model's raw output; excluding them would
    score TestForge on a filtered set and the baseline on an unfiltered one.
    """
    if ARM == "baseline":
        d = next((x for x in GEN.glob(f"*/baseline/{repo}") if any(x.glob("*.swift"))), None)
        return sorted(d.glob("*.swift")) if d else []
    d = next((x for x in GEN.glob(f"*/testforge/{repo}/tests") if any(x.rglob("*"))), None)
    if d is None: return []
    return sorted([f for f in d.rglob("*") if f.suffix in (".swift", ".disabled")])

def run(repo):
    ws = BENCH/repo
    files = sources_for(repo)
    if not files: return None
    r = survivors(ws, files, module_of(ws))
    if r: r["repo"] = repo; print(f"  {repo[:38]:38} submitted={r['submitted']} "
                                 f"together={'OK' if r['all_together_ok'] else 'FAIL'} "
                                 f"survivors={r['survivors']}", flush=True)
    return r

ARM = sys.argv[1] if len(sys.argv) > 1 else "baseline"
repos = sorted({d.name for d in GEN.glob("*/baseline/*") if any(d.glob("*.swift"))})
print(f"collective build pass | ARM={ARM} | {len(repos)} repos | builds only\n")
out = [r for r in (run(x) for x in repos) if r]
(DOCS/f"collective_{ARM}.json").write_text(json.dumps(out, indent=1))
sub = sum(r["submitted"] for r in out); sur = sum(r["survivors"] for r in out)
tog = sum(r["all_together_ok"] for r in out)
print(f"\n{'='*58}")
print(f"  repos                        : {len(out)}")
print(f"  files submitted              : {sub}")
print(f"  repos building with ALL files: {tog}/{len(out)} ({tog/max(len(out),1)*100:.0f}%)")
print(f"  files surviving together     : {sur} ({sur/max(sub,1)*100:.1f}%)")
print(f"\n  isolated-file rate was 83.3% - the gap is the coexistence cost")

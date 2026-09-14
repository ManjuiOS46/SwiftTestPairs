#!/usr/bin/env python3
"""Baseline arm - the control group.

Same model, same repos, same measurement. The ONLY difference is process:
  TestForge : indexes the project, framework guidance, compiles, repairs twice,
              quarantines what it cannot fix.
  Baseline  : one prompt, one response, saved as-is. What you'd get pasting a
              file into a chat window.

It is still COMPILED afterwards - but only to measure it, never to fix it.
That is the whole comparison: does the verify-and-repair loop earn its keep?
"""
import json, os, pathlib, re, subprocess, shutil, sys, time, threading, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

ROOT  = pathlib.Path(__file__).resolve().parent.parent
BENCH, GEN = ROOT/"bench", ROOT/"generated"
ENV   = {**os.environ, "DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"}
MODEL = "gemini-3.8-flash"
N_REPOS   = int(sys.argv[1]) if len(sys.argv) > 1 else 25
HARD_CAP  = 1.20          # ledger USD; ~4x in real billing = ~Rs300.
                          # Total must stay under the user's Rs5,000 ceiling:
                          # ~Rs4,400 already spent, so ~Rs600 headroom.
RUN_ID    = time.strftime("%Y%m%d-%H%M%S")
OUT       = GEN/RUN_ID/"baseline"; OUT.mkdir(parents=True, exist_ok=True)

# TestForge stores provider keys under service "com.testforge.providers".
# The value goes keychain -> this process and is never printed or logged.
KEY = os.environ.get("GEMINI_API_KEY","") or subprocess.run(
    ["security","find-generic-password","-s","com.testforge.providers",
     "-a","GEMINI_API_KEY","-w"], capture_output=True, text=True).stdout.strip()
if not KEY:
    sys.exit("No Gemini key found. TestForge stores it in the keychain; export GEMINI_API_KEY to run this.")

URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
lock, spent, stop = threading.Lock(), 0.0, threading.Event()

PROMPT = """Here is a Swift source file from the module `{module}`.

Write a complete XCTest test file for it. Return only Swift code, no explanation.

```swift
{code}
```"""

def ask(code, module, tries=6):
    """One prompt, with backoff on rate limits.

    The first attempt at this harness fired three workers with no retry and every
    call died on HTTP 429 - a silent wipe-out, because each failure was caught,
    recorded and stepped over. Paid Tier 1 has modest per-minute limits; pace it.
    """
    body = json.dumps({"contents":[{"parts":[{"text": PROMPT.format(module=module, code=code[:24000])}]}]}).encode()
    delay = 5.0
    last = None
    for attempt in range(tries):
        req = urllib.request.Request(URL, data=body,
                headers={"Content-Type":"application/json","x-goog-api-key":KEY})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                d = json.loads(r.read())
            txt = d["candidates"][0]["content"]["parts"][0].get("text","")
            u = d.get("usageMetadata",{})
            cost = (u.get("promptTokenCount",0)*0.75 + u.get("candidatesTokenCount",0)*3.75)/1e6
            return txt, cost, u
        except urllib.error.HTTPError as e:
            last = e
            detail = ""
            try: detail = e.read().decode(errors="ignore")
            except Exception: pass
            # 429 covers BOTH rate limiting and an exhausted account. Retrying a
            # depleted balance just sleeps longer before failing, so read the body
            # and stop immediately rather than burning six backoffs on it.
            if "depleted" in detail or "RESOURCE_EXHAUSTED" in detail and "rate" not in detail.lower():
                raise RuntimeError(f"ACCOUNT OUT OF CREDIT - stopping: {detail[:160]}")
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(delay); delay = min(delay * 2, 120); continue
            raise
        except Exception as e:
            last = e; time.sleep(delay); delay = min(delay * 2, 120); continue
    raise RuntimeError(f"giving up after {tries} attempts: {last}")

def strip_fence(t):
    m = re.search(r'```(?:swift)?\n(.*?)```', t, re.S)
    return m.group(1) if m else t

def compiles(ws, test_code, module):
    """Measure only. One file, one build, no repair - the point of the control."""
    tdir = next((d for d in (ws/"repo").rglob("Tests") if d.is_dir()), None)
    if tdir is None: return None
    tmp = tdir/"_BaselineProbe.swift"
    try:
        tmp.write_text(re.sub(r'@testable\s+import\s+\w+', f'@testable import {module}', test_code))
        p = subprocess.run(["swift","build","--build-tests"], cwd=ws/"repo", env=ENV,
                           capture_output=True, text=True, timeout=300)
        return p.returncode == 0
    except Exception:
        return False
    finally:
        tmp.unlink(missing_ok=True)

def module_of(ws):
    m = re.search(r'name:\s*"([^"]+)"', (ws/"repo"/"Package.swift").read_text(errors="ignore")) \
        if (ws/"repo"/"Package.swift").exists() else None
    return m.group(1) if m else ws.name.split("__")[-1]

def run_repo(repo):
    global spent
    if stop.is_set(): return {"repo": repo, "status":"skipped"}
    ws = BENCH/repo
    module = module_of(ws)
    srcs = [f for f in (ws/"repo").rglob("*.swift")
            if ".build" not in str(f) and "Tests" not in str(f) and f.name != "Package.swift"][:8]
    dst = OUT/repo; dst.mkdir(parents=True, exist_ok=True)
    res = []
    for f in srcs:
        with lock:
            if spent >= HARD_CAP or stop.is_set():
                stop.set(); break
        try:
            raw, cost, usage = ask(f.read_text(errors="ignore"), module)
        except Exception as e:
            if "OUT OF CREDIT" in str(e):
                print(f"  !! {e}", flush=True); stop.set(); break
            res.append({"file": f.name, "error": str(e)[:120]}); continue
        time.sleep(2)          # stay comfortably inside Tier 1 rate limits
        code = strip_fence(raw)
        (dst/f"{f.stem}Tests.swift").write_text(code)
        valid = bool(re.search(r'\bimport XCTest\b', code)) and bool(re.search(r'\b(class|func)\s+\w', code))
        ok = compiles(ws, code, module) if valid else False
        with lock: spent += cost
        res.append({"file": f.name, "valid_swift": valid, "compiles": bool(ok),
                    "cost": cost, "chars": len(code)})
        print(f"  [{spent:5.3f}] {repo[:32]:32} {f.name[:26]:26} valid={valid} compiles={ok}", flush=True)
    (dst/"results.json").write_text(json.dumps(res, indent=1))
    return {"repo": repo, "status":"ok", "files": res}

def main():
    clean = json.loads((ROOT/"docs"/"benchmark_results.json").read_text())
    pool = [r["repo"] for r in clean
            if not r["contaminated"] and not r["budget_truncated"] and r["valid_swift"] > 0]
    import random; random.Random(7).shuffle(pool)
    pool = pool[:N_REPOS]
    print(f"baseline arm | {len(pool)} repos | {MODEL} | cap ${HARD_CAP}\n")
    out=[]
    with ThreadPoolExecutor(max_workers=1) as ex:
        for r in ex.map(run_repo, pool): out.append(r)
    (GEN/RUN_ID/"baseline_results.json").write_text(json.dumps(out, indent=1))
    allf = [f for r in out for f in r.get("files",[]) if isinstance(f, dict)]
    errs = [f for f in allf if "error" in f]
    if errs:
        print(f"\n  !! {len(errs)}/{len(allf)} calls FAILED  e.g. {errs[0]['error'][:90]}")
    files=[f for r in out for f in r.get("files",[]) if "valid_swift" in f]
    if not files:
        print("\n  !! NO USABLE RESULTS - the run produced nothing. Do not treat this as a measurement.")
    if files:
        v=sum(f["valid_swift"] for f in files); c=sum(f["compiles"] for f in files)
        print(f"\n{'='*58}")
        print(f"  files generated : {len(files)}")
        print(f"  valid Swift     : {v} ({v/len(files)*100:.1f}%)")
        print(f"  COMPILES        : {c} ({c/len(files)*100:.1f}%)")
        print(f"  spent           : ${spent:.3f}")
if __name__ == "__main__": main()

#!/usr/bin/env python3
"""Human arm - coverage achieved by the engineers' own tests.

Restores each repo's real tests from human/, runs them with coverage, records the
figure, then puts the workspace back. Completes the third column of the comparison.

No model calls. Builds only.
"""
import json, os, pathlib, re, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
GEN, BENCH, DOCS = ROOT/"generated", ROOT/"bench", ROOT/"docs"
DEV = "/Applications/Xcode.app/Contents/Developer"
ENV = {**os.environ, "DEVELOPER_DIR": DEV}

def coverage_of(ws):
    """Line coverage over the package's own sources, excluding test scaffolding."""
    b = subprocess.run(["swift","build","--show-bin-path"], cwd=ws/"repo", env=ENV,
                       capture_output=True, text=True, timeout=300)
    if b.returncode != 0: return None
    bin_ = pathlib.Path(b.stdout.strip())
    cc = bin_/"codecov"
    if not cc.exists(): return None
    raws = list(cc.glob("*.profraw"))
    prof = cc/"default.profdata"
    if raws and not prof.exists():
        m = subprocess.run(["xcrun","llvm-profdata","merge","-sparse",
                            *[str(r) for r in raws], "-o", str(prof)],
                           capture_output=True, text=True, timeout=600)
        if m.returncode != 0: return None
    if not prof.exists(): return None
    bundle = next((p for p in bin_.glob("*.xctest")), None)
    if bundle is None: return None
    name = bundle.stem
    exe = bundle/"Contents/MacOS"/name
    if not exe.exists(): exe = bundle/name
    if not exe.exists(): return None
    r = subprocess.run(["xcrun","llvm-cov","report",str(exe),"-instr-profile",str(prof),
                        "-ignore-filename-regex", r"\.build/|/Tests?/|\.derived/"],
                       capture_output=True, text=True, timeout=600)
    m = re.search(r'TOTAL\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+(\d+\.\d+)%', r.stdout)
    if m: return float(m.group(1))
    m = re.findall(r'(\d+\.\d+)%', r.stdout.splitlines()[-1] if r.stdout.splitlines() else "")
    return float(m[-1]) if m else None

def run(repo):
    ws = BENCH/repo
    human = ws/"human"
    if not human.exists(): return None
    staged = []
    try:
        for f in human.rglob("*.swift"):
            dst = ws/"repo"/f.relative_to(human)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(f, dst); staged.append(dst)
        if not staged: return None
        t = subprocess.run(["swift","test","--enable-code-coverage"], cwd=ws/"repo",
                           env=ENV, capture_output=True, text=True, timeout=900)
        passed = t.returncode == 0
        cov = coverage_of(ws)
        print(f"  {repo[:38]:38} tests={'pass' if passed else 'FAIL'} "
              f"coverage={f'{cov:.1f}%' if cov is not None else 'n/a'}", flush=True)
        return {"repo": repo, "human_tests": len(staged), "tests_pass": passed,
                "human_coverage": cov}
    except subprocess.TimeoutExpired:
        print(f"  {repo[:38]:38} TIMEOUT", flush=True)
        return {"repo": repo, "human_tests": len(staged), "tests_pass": False,
                "human_coverage": None}
    finally:
        for s_ in staged: s_.unlink(missing_ok=True)
        shutil.rmtree(ws/"repo"/".build", ignore_errors=True)

repos = sorted({d.name for d in GEN.glob("*/baseline/*") if any(d.glob("*.swift"))})
print(f"human arm | {len(repos)} repos | builds only, no model calls\n")
out=[]
with ThreadPoolExecutor(max_workers=3) as ex:
    for r in ex.map(run, repos):
        if r: out.append(r)
(DOCS/"human_coverage.json").write_text(json.dumps(out, indent=1))
cov = [r["human_coverage"] for r in out if r["human_coverage"] is not None]
print(f"\n{'='*56}")
print(f"  repos measured     : {len(out)}")
print(f"  human tests ran ok : {sum(r['tests_pass'] for r in out)}/{len(out)}")
print(f"  coverage obtained  : {len(cov)} repos")
if cov:
    import statistics as st
    print(f"  MEAN human coverage: {st.mean(cov):.1f}%")
    print(f"  median             : {st.median(cov):.1f}%")

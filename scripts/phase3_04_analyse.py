#!/usr/bin/env python3
"""Turn raw benchmark output into defensible numbers.

TestForge's own filesGenerated count cannot be published as-is:
  1. ~5% of written files are not valid Swift (model prose, truncated output)
  2. 18 workspaces still held their original human tests, so those runs did not
     measure generation-from-scratch
  3. per-run budget caps killed repair loops, depressing some repos artificially

This recomputes from the preserved files and reports the clean subset.
Read-only: touches nothing the benchmark uses.
"""
import json, pathlib, re, collections
ROOT = pathlib.Path(__file__).resolve().parent.parent
BENCH, GEN, OUT = ROOT/"bench", ROOT/"generated", ROOT/"docs"
OUT.mkdir(exist_ok=True)

def is_real_test(t: str) -> bool:
    return bool(re.search(r'\bimport (XCTest|Testing)\b', t)) and \
           bool(re.search(r'\b(class|struct|func)\s+\w', t))

# --- which workspaces leaked their original tests? -------------------------
TESTISH = re.compile(r'(Tests?|Specs?)\.swift$|(Tests?|Specs?)/')
def leaked(ws: pathlib.Path) -> bool:
    """Original tests we failed to move out, judged from the human/ twin set."""
    human = {p.name for p in (ws/"human").rglob("*.swift")} if (ws/"human").exists() else set()
    if not human: return False
    for f in (ws/"repo").rglob("*.swift"):
        if ".build" in str(f): continue
        rel = str(f.relative_to(ws/"repo"))
        # a file matching a human test NAME that sits outside a top-level Tests/ dir
        if f.name in human and not rel.startswith("Tests/"):
            return True
    return False

rows = []
for rep in sorted(GEN.glob("*/testforge/*/report.json")):
    repo = str(rep).split("/testforge/")[1].split("/")[0]
    try: d = json.loads(rep.read_text())
    except Exception: continue
    s = d.get("summary", {})
    if not (s.get("totalCostUSD") or 0): continue

    tests_dir = rep.parent/"tests"
    written = list(tests_dir.rglob("*.swift")) if tests_dir.exists() else []
    valid = [f for f in written if is_real_test(f.read_text(errors="ignore"))]
    junk  = len(written) - len(valid)

    ledger = d.get("ledger") or []
    truncated = any("Budget cap reached" in str(e.get("outcome","")) for e in ledger)

    rows.append({
        "repo": repo,
        "contaminated": leaked(BENCH/repo),
        "budget_truncated": truncated,
        "reported_kept": s.get("filesGenerated") or 0,
        "reported_quarantined": s.get("filesQuarantined") or 0,
        "files_on_disk": len(written),
        "valid_swift": len(valid),
        "junk_files": junk,
        "cov_before": s.get("coverageBefore"),
        "cov_after": s.get("coverageAfter"),
        "cost": s.get("totalCostUSD") or 0,
        "calls": sum((s.get("callsByModel") or {}).values()),
    })

def report(title, subset):
    if not subset: print(f"\n{title}: no repos"); return
    kept = sum(r["reported_kept"] for r in subset)
    quar = sum(r["reported_quarantined"] for r in subset)
    valid = sum(r["valid_swift"] for r in subset)
    junk = sum(r["junk_files"] for r in subset)
    zero = sum(1 for r in subset if r["valid_swift"] == 0)
    covd = [r for r in subset if (r["cov_after"] or 0) > 0 and r["cov_before"] is not None]
    print(f"\n{title}")
    print(f"  repos                     : {len(subset)}")
    print(f"  TestForge reported kept   : {kept}")
    print(f"  files actually on disk    : {sum(r['files_on_disk'] for r in subset)}")
    print(f"  VALID Swift test files    : {valid}")
    print(f"  junk (prose/truncated)    : {junk}  ({junk/max(valid+junk,1)*100:.1f}%)")
    print(f"  quarantined by TestForge  : {quar}")
    print(f"  KEEP RATE (valid/(valid+quar)) : {valid/max(valid+quar,1)*100:.1f}%")
    print(f"  repos producing nothing   : {zero} ({zero/len(subset)*100:.0f}%)")
    if covd:
        delta = [ (r["cov_after"]-r["cov_before"]) for r in covd ]
        print(f"  coverage measured on      : {len(covd)} repos")
        print(f"  mean coverage delta       : +{sum(delta)/len(delta):.1f} points")

report("ALL REPOS (raw - do not publish)", rows)
clean = [r for r in rows if not r["contaminated"]]
report("EXCLUDING CONTAMINATED", clean)
strict = [r for r in clean if not r["budget_truncated"]]
report("CLEAN + NOT BUDGET-TRUNCATED  <-- publishable", strict)

print(f"\n  excluded: {sum(1 for r in rows if r['contaminated'])} contaminated, "
      f"{sum(1 for r in clean if r['budget_truncated'])} budget-truncated")
(OUT/"benchmark_results.json").write_text(json.dumps(rows, indent=1))
print(f"\nwrote docs/benchmark_results.json")

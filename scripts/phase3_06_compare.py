#!/usr/bin/env python3
"""Three-arm comparison: human / plain prompt / TestForge.

Compares ONLY on repos all arms actually covered - otherwise the arms are scored
on different work and the table means nothing.
"""
import json, pathlib, re, statistics as st
ROOT = pathlib.Path(__file__).resolve().parent.parent
GEN, DOCS = ROOT/"generated", ROOT/"docs"

# --- arms -----------------------------------------------------------------
tf = {r["repo"]: r for r in json.loads((DOCS/"benchmark_results.json").read_text())
      if not r["contaminated"] and not r["budget_truncated"]}

# per-repo results.json is written as each repo finishes; the aggregate only at
# the end. Read the incremental files so this works mid-run too.
base = {}
for res in sorted(GEN.glob("*/baseline/*/results.json")):
    repo = res.parent.name
    try: files = [f for f in json.loads(res.read_text())
                  if isinstance(f, dict) and "valid_swift" in f]
    except Exception: continue
    if files: base[repo] = files

import duckdb
con = duckdb.connect()
# the dataset keys on "owner/repo"; bench slugs replace "/" with "__"
human = {r[0].replace("/", "__"): r[1:] for r in con.sql(f"""
    SELECT repo_name, count(*) AS pairs, median(n_assertions) AS med_assert
    FROM read_parquet('{ROOT}/data/release/swifttestpairs.parquet')
    WHERE tier = 2 GROUP BY 1""").fetchall()}

shared = sorted(set(tf) & set(base))
print(f"repos covered by BOTH generated arms: {len(shared)}")
if not shared:
    print("  baseline has not produced enough data yet"); raise SystemExit

def assertions_in(path: pathlib.Path):
    n = 0
    for f in path.rglob("*.swift"):
        n += len(re.findall(r'XCTAssert|XCTUnwrap|XCTFail', f.read_text(errors="ignore")))
    return n

rows = []
for repo in shared:
    b = base[repo]
    t = tf[repo]
    tf_dir = next((d for d in GEN.glob(f"*/testforge/{repo}/tests")
                   if any(d.rglob("*.swift"))), None)
    bs_dir = next((d for d in GEN.glob(f"*/baseline/{repo}")
                   if any(d.glob("*.swift"))), None)
    rows.append({
        "repo": repo,
        "base_files": len(b),
        "base_valid": sum(f["valid_swift"] for f in b),
        "base_compiles": sum(f["compiles"] for f in b),
        "base_assertions": assertions_in(bs_dir) if bs_dir else 0,
        "tf_valid": t["valid_swift"],
        "tf_quarantined": t["reported_quarantined"],
        "tf_assertions": assertions_in(tf_dir) if tf_dir else 0,
        "tf_cov_delta": (t["cov_after"] - t["cov_before"])
                        if t["cov_after"] and t["cov_before"] is not None else None,
        "human_pairs": human.get(repo, (0, 0))[0],
        "human_med_assert": human.get(repo, (0, 0))[1],
    })

B = lambda k: sum(r[k] for r in rows)
covs = [r["tf_cov_delta"] for r in rows if r["tf_cov_delta"] is not None]

print(f"\n{'='*72}")
print(f"  THREE-ARM COMPARISON  ({len(rows)} repos, gemini-3.8-flash both arms)")
print(f"{'='*72}\n")
print(f"  {'':<26} {'HUMAN':>12} {'PLAIN PROMPT':>14} {'TESTFORGE':>12}")
print(f"  {'-'*66}")
print(f"  {'test files':<26} {B('human_pairs'):>12} {B('base_files'):>14} {B('tf_valid')+B('tf_quarantined'):>12}")
print(f"  {'valid Swift':<26} {'-':>12} {B('base_valid'):>14} {B('tf_valid'):>12}")
print(f"  {'COMPILE / SURVIVE':<26} {'(by definition)':>12} {B('base_compiles'):>14} {B('tf_valid'):>12}")
rate_b = B('base_compiles')/max(B('base_files'),1)*100
rate_t = B('tf_valid')/max(B('tf_valid')+B('tf_quarantined'),1)*100
print(f"  {'success rate':<26} {'100%':>12} {f'{rate_b:.1f}%':>14} {f'{rate_t:.1f}%':>12}")
print(f"  {'assertions written':<26} {'-':>12} {B('base_assertions'):>14} {B('tf_assertions'):>12}")
print(f"  {'coverage delta (mean)':<26} {'-':>12} {'not measured':>14} "
      f"{f'+{st.mean(covs):.1f} pts' if covs else 'n/a':>12}")
hm = [r["human_med_assert"] for r in rows if r["human_med_assert"]]
if hm: print(f"\n  human median assertions/test file: {st.median(hm):.0f}")
(DOCS/"comparison.json").write_text(json.dumps(rows, indent=1))
print(f"\nwrote docs/comparison.json")
print("""
  !! NOT YET COMPARABLE - read before quoting these numbers.

  The baseline compiles each generated file ALONE. TestForge compiles all of a
  repo's generated files TOGETHER, so its files must coexist - and colliding
  helper names across sibling files are a known failure mode (its own prompt
  warns about it). Measured this way the baseline is handed an advantage
  TestForge never had, which is why it looks better here.

  A fair comparison needs the baseline's whole set built together, exactly as
  someone pasting every file into their project would experience it.
  That pass is free - builds only, no model calls.

  GAP: the human arm has no coverage figure. The human tests were never run for
  coverage. Also free.
""")

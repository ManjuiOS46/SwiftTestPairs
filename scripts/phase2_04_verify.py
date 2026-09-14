#!/usr/bin/env python3
"""Phase 2 step 4 - VERIFY tier 2 by building every eligible repo.

Converts tier 2 from "eligible" to "verified". Pairs whose repo fails to build
are demoted to tier 1. DuckDB conn is NOT thread-safe: pre-fetch serially.
"""
import duckdb, subprocess, tempfile, pathlib, re, os, json, collections
from concurrent.futures import ThreadPoolExecutor
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT, REL = ROOT/"data"/"interim", ROOT/"data"/"release"
ENV = {**os.environ, "DEVELOPER_DIR": "/Applications/Xcode.app/Contents/Developer"}
con = duckdb.connect(str(OUT/"slice.duckdb")); con.execute("PRAGMA threads=8")

repos = [r[0] for r in con.sql("SELECT DISTINCT repo_name FROM final WHERE tier=2").fetchall()]
print(f"tier-2 eligible repos to verify: {len(repos):,}")
print("pre-fetching (serial)...")
jobs = [(r, [(p,c) for p,c in con.execute(
    "SELECT path, content FROM corpus_mat WHERE repo_name=?", [r]).fetchall() if p and c is not None])
        for r in repos]
print(f"fetched {len(jobs)} repos\n")

def build(job):
    repo, files = job
    if not any(p.endswith("Package.swift") for p,_ in files):
        return {"repo":repo,"ok":False,"err":"NO_MANIFEST"}
    with tempfile.TemporaryDirectory(prefix="v2_") as d:
        d = pathlib.Path(d)
        for p,c in files:
            if ".." in p: continue
            fp = d/p.lstrip("/"); fp.parent.mkdir(parents=True, exist_ok=True)
            try: fp.write_text(c)
            except Exception: pass
        root = d
        if not (root/"Package.swift").exists():
            cand = sorted(d.rglob("Package.swift"), key=lambda x: len(x.parts))
            if cand: root = cand[0].parent
        try:
            pr = subprocess.run(["swift","build","--build-tests"], cwd=root, env=ENV,
                                capture_output=True, text=True, timeout=420)
            ok = pr.returncode==0
            return {"repo":repo,"ok":ok,"err":"" if ok else ((pr.stdout or "")+(pr.stderr or ""))[-2500:]}
        except subprocess.TimeoutExpired:
            return {"repo":repo,"ok":False,"err":"TIMEOUT"}

res=[]
with ThreadPoolExecutor(max_workers=5) as ex:
    for i,r in enumerate(ex.map(build, jobs), 1):
        res.append(r)
        if i%25==0: print(f"  {i:>4}/{len(jobs)}  {sum(x['ok'] for x in res)/len(res):.1%}")

ok_repos = sorted({r["repo"] for r in res if r["ok"]})
print(f"\n  VERIFIED repos: {len(ok_repos)}/{len(res)} = {len(ok_repos)/max(len(res),1):.1%}")
con.execute("CREATE OR REPLACE TABLE verified_repos AS SELECT unnest(?::VARCHAR[]) AS repo_name", [ok_repos])
con.execute("""CREATE OR REPLACE TABLE final AS
  SELECT f.* REPLACE (CASE WHEN f.tier=2 AND v.repo_name IS NOT NULL THEN 2 ELSE 1 END AS tier)
  FROM final f LEFT JOIN verified_repos v USING(repo_name)""")
print(con.sql("SELECT tier, count(*) pairs, count(DISTINCT repo_name) repos FROM final GROUP BY 1 ORDER BY 1").df().to_string(index=False))
(OUT/"verify_tier2.json").write_text(json.dumps(res, indent=1))

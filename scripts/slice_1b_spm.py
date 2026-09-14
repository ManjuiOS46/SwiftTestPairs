#!/usr/bin/env python3
"""Phase 1b (SPM) - reconstruct the repo's REAL package, don't synthesise one.

Repos carrying their own Package.swift are self-describing: correct targets,
correct layout. We rebuild the repo verbatim from corpus files and build it.
The human's own test is already in place - no injection, no module rewriting.
"""
import duckdb, subprocess, tempfile, pathlib, re, sys, os, json, collections
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT  = ROOT / "data" / "interim"
DEV  = "/Applications/Xcode.app/Contents/Developer"
ENV  = {**os.environ, "DEVELOPER_DIR": DEV}
N    = int(sys.argv[1]) if len(sys.argv) > 1 else 200

con = duckdb.connect(str(OUT/"slice.duckdb")); con.execute("PRAGMA threads=8")
LEG = r"(\bGeneratorType\b|\bSequenceType\b|\bCollectionType\b|\bErrorType\b|\.characters\b|appendNewline|\bprintln\s*\(|dispatch_async\s*\(|NSURLSession\b)"

repos = con.sql(f"""
  SELECT DISTINCT p.repo_name FROM pairs p JOIN spm_repos s USING(repo_name)
  WHERE NOT regexp_matches(s.manifest, '\\.package\\s*\\(')
    AND NOT regexp_matches(p.source_code,'{LEG}') AND NOT regexp_matches(p.test_code,'{LEG}')
    AND try_cast(regexp_extract(s.manifest,'swift-tools-version:\\s*([0-9]+)',1) AS INT) >= 5
  ORDER BY random() LIMIT {N}""").fetchall()
elig = con.sql(f"""SELECT count(*) FROM pairs p JOIN spm_repos s USING(repo_name)
  WHERE NOT regexp_matches(s.manifest,'\\.package\\s*\\(')
    AND NOT regexp_matches(p.source_code,'{LEG}') AND NOT regexp_matches(p.test_code,'{LEG}')
    AND try_cast(regexp_extract(s.manifest,'swift-tools-version:\\s*([0-9]+)',1) AS INT) >= 5""").fetchone()[0]
print(f"sampled {len(repos)} SPM repos | eligible pairs (tools-version >= 5): {elig:,}\n")

print("swift-tools-version distribution:")
print(con.sql("""SELECT regexp_extract(manifest,'swift-tools-version:\\s*([0-9.]+)',1) AS v,
  count(*) n FROM spm_repos GROUP BY 1 ORDER BY 2 DESC LIMIT 8""").df().to_string(index=False))

def build(job):
    repo, files = job
    if not any(p.endswith("Package.swift") for p,_ in files):
        return {"repo":repo,"ok":False,"err":"NO_MANIFEST","n":len(files)}
    with tempfile.TemporaryDirectory(prefix="spm_") as d:
        d = pathlib.Path(d)
        for p, c in files:
            fp = d / p.lstrip("/")
            if ".." in p: continue
            fp.parent.mkdir(parents=True, exist_ok=True)
            try: fp.write_text(c)
            except Exception: pass
        root = d
        if not (root/"Package.swift").exists():           # nested at any depth
            cand = sorted(d.rglob("Package.swift"), key=lambda x: len(x.parts))
            if cand: root = cand[0].parent
        try:
            pr = subprocess.run(["swift","build","--build-tests"], cwd=root, env=ENV,
                                capture_output=True, text=True, timeout=420)
            ok = pr.returncode == 0
            err = "" if ok else ((pr.stdout or "")+"\n"+(pr.stderr or ""))[-4000:]
        except subprocess.TimeoutExpired: ok, err = False, "TIMEOUT"
        return {"repo":repo,"ok":ok,"err":err,"n":len(files)}

def cat(e):
    if e in ("TIMEOUT","NO_MANIFEST"): return e.lower()
    for p,n in [(r"unsupported Swift version|tools-version",'tools_version'),
                (r"no such module",'missing_module'),
                (r"cannot find type",'unresolved_type'),
                (r"cannot find '?\w+'? in scope",'unresolved_symbol'),
                (r"invalid redeclaration",'duplicate_symbol'),
                (r"Source files for target .* should be located",'layout_mismatch'),
                (r"found loose source files|is not a directory",'layout_mismatch'),
                (r"unavailable|only available in",'availability'),
                (r"has no member",'no_member')]:
        if re.search(p,e,re.I): return n
    return "other"

print("pre-fetching repo files (serial - DuckDB conn is not thread-safe)...")
jobs=[]
for (repo,) in repos:
    fs = con.execute("SELECT path, content FROM corpus_mat WHERE repo_name=?", [repo]).fetchall()
    jobs.append((repo, [(p,c) for p,c in fs if p and c is not None]))
have = sum(1 for _,f in jobs if any(p.endswith("Package.swift") for p,_ in f))
print(f"  {len(jobs)} repos fetched; {have} have a manifest ({have/max(len(jobs),1):.1%})\n")

res=[]
with ThreadPoolExecutor(max_workers=5) as ex:
    for i,r in enumerate(ex.map(build,jobs),1):
        res.append(r)
        if i%20==0: print(f"  {i:>4}/{len(repos)}  {sum(x['ok'] for x in res)/len(res):.1%}")

ok=sum(r['ok'] for r in res)
print(f"\n{'='*62}\n  SPM-TIER BUILD RATE: {ok}/{len(res)} = {ok/len(res):.1%}\n{'='*62}")
for k,v in collections.Counter(cat(r['err']) for r in res if not r['ok']).most_common():
    print(f"    {k:20} {v:>4} ({v/len(res):.1%})")
print(f"\n  PROJECTED verified pairs: ~{int(elig*ok/max(len(res),1)):,} of {elig:,} eligible (tools-version >= 5)")
(OUT/"compile_1b_spm.json").write_text(json.dumps(res,indent=1))

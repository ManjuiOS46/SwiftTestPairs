#!/usr/bin/env python3
"""Phase 1b (strict) - do not chase compile rate; SELECT for compilability.

Candidate = pair whose repo is small AND every source file imports only Apple
system frameworks (no sibling targets, no third-party). Measures the compile
rate of that tier and therefore how large a verified benchmark subset can be.
"""
import duckdb, subprocess, tempfile, pathlib, re, sys, os, json, collections
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT  = ROOT / "data" / "interim"
MOD, DEV = "PairModule", "/Applications/Xcode.app/Contents/Developer"
ENV = {**os.environ, "DEVELOPER_DIR": DEV}
N = int(sys.argv[1]) if len(sys.argv) > 1 else 300
MAX_REPO_FILES = 25

APPLE = ['Foundation','Swift','Dispatch','Darwin','os','CoreGraphics','Combine','ObjectiveC',
         'CoreData','Security','CoreLocation','AVFoundation','CryptoKit','CommonCrypto',
         'Network','SystemConfiguration','CoreImage','QuartzCore','Accelerate','simd',
         'CoreText','CoreMedia','AudioToolbox','LocalAuthentication','CoreBluetooth',
         'Compression','NaturalLanguage','CoreML','Vision','MapKit','CloudKit','Contacts',
         'EventKit','Photos','StoreKit','WebKit','SafariServices','UserNotifications',
         'XCTest','Testing','Darwin.C','MachO','Numerics','RegexBuilder','Observation']
A = "[" + ",".join(f"'{a}'" for a in APPLE) + "]"

PKG = f'''// swift-tools-version:5.9
import PackageDescription
let package = Package(name: "{MOD}", platforms: [.macOS(.v13)],
  targets: [.target(name: "{MOD}", path: "Sources/{MOD}"),
            .testTarget(name: "{MOD}Tests", dependencies: ["{MOD}"], path: "Tests/{MOD}Tests")])
'''

def build(job):
    idx, repo, spath, tpath, tcode, files = job
    with tempfile.TemporaryDirectory(prefix="sp_") as d:
        d = pathlib.Path(d)
        (d/f"Sources/{MOD}").mkdir(parents=True); (d/f"Tests/{MOD}Tests").mkdir(parents=True)
        (d/"Package.swift").write_text(PKG)
        for i,(p,c) in enumerate(files):
            stem = re.sub(r'[^A-Za-z0-9_]','_',p.rsplit('/',1)[-1].removesuffix('.swift'))
            (d/f"Sources/{MOD}"/f"{i:03d}_{stem}.swift").write_text(c)
        (d/f"Tests/{MOD}Tests/Tests.swift").write_text(
            re.sub(r'@testable\s+import\s+[A-Za-z_]\w*', f'@testable import {MOD}', tcode))
        try:
            p = subprocess.run(["swift","build","--build-tests"], cwd=d, env=ENV,
                               capture_output=True, text=True, timeout=300)
            ok = p.returncode==0
            err = "" if ok else ((p.stdout or "")+"\n"+(p.stderr or ""))[-4000:]
        except subprocess.TimeoutExpired: ok, err = False, "TIMEOUT"
        return {"idx":idx,"repo":repo,"source_path":spath,"test_path":tpath,
                "n_files":len(files),"ok":ok,"err":err}

def cat(e):
    if e=="TIMEOUT": return "timeout"
    for p,n in [(r"cannot find type",'unresolved_type'),(r"cannot find '?\w+'? in scope",'unresolved_symbol'),
                (r"no such module",'missing_module'),(r"invalid redeclaration",'duplicate_symbol'),
                (r"has no member",'no_member'),(r"inaccessible due to",'access_control'),
                (r"extra argument|missing argument",'signature_mismatch'),
                (r"only available in|unavailable",'availability')]:
        if re.search(p,e,re.I): return n
    return "other"

con = duckdb.connect(str(OUT/"slice.duckdb")); con.execute("PRAGMA threads=8")

con.execute(f"""CREATE OR REPLACE TABLE clean_repos AS
WITH f AS (SELECT repo_name, path, content,
   len(list_filter(regexp_extract_all(content,'import\\s+([A-Za-z_][A-Za-z0-9_]*)',1),
       x -> NOT list_contains({A}, x))) AS bad
   FROM labelled WHERE kind='SOURCE')
SELECT repo_name, count(*) AS n_files, sum(bad) AS bad_files
FROM f GROUP BY 1 HAVING sum(bad)=0 AND count(*) BETWEEN 1 AND {MAX_REPO_FILES}""")

tot_repos = con.sql("SELECT count(*) FROM clean_repos").fetchone()[0]
elig = con.sql(f"""SELECT count(*) FROM pairs_sc p JOIN clean_repos c USING(repo_name)
  WHERE len(list_filter(regexp_extract_all(p.test_code,'import\\s+([A-Za-z_][A-Za-z0-9_]*)',1),
        x -> NOT list_contains({A}, x))) = 0""").fetchone()[0]
print(f"clean repos (all-Apple imports, <={MAX_REPO_FILES} files): {tot_repos:,}")
print(f"ELIGIBLE PAIRS in this tier: {elig:,}   (of 11,150 self-contained)\n")

rows = con.sql(f"""SELECT p.repo_name, p.source_path, p.test_path, p.test_code
  FROM pairs_sc p JOIN clean_repos c USING(repo_name)
  WHERE len(list_filter(regexp_extract_all(p.test_code,'import\\s+([A-Za-z_][A-Za-z0-9_]*)',1),
        x -> NOT list_contains({A}, x))) = 0
  ORDER BY random() LIMIT {N}""").fetchall()

jobs=[]
for i,(repo,sp,tp,tc) in enumerate(rows):
    fs = con.execute("SELECT path, content FROM labelled WHERE repo_name=? AND kind='SOURCE'",[repo]).fetchall()
    if fs: jobs.append((i,repo,sp,tp,tc,fs))
print(f"building {len(jobs)} packages...\n")

res=[]
with ThreadPoolExecutor(max_workers=6) as ex:
    for i,r in enumerate(ex.map(build,jobs),1):
        res.append(r)
        if i%25==0: print(f"  {i:>4}/{len(jobs)}  {sum(x['ok'] for x in res)/len(res):.1%}")

ok=sum(r['ok'] for r in res)
print(f"\n{'='*60}\n  STRICT-TIER COMPILE RATE: {ok}/{len(res)} = {ok/len(res):.1%}\n{'='*60}")
for k,v in collections.Counter(cat(r['err']) for r in res if not r['ok']).most_common():
    print(f"    {k:20} {v:>4} ({v/len(res):.1%})")
print(f"\n  PROJECTED verified-compiling pairs: ~{int(elig*ok/max(len(res),1)):,}")
(OUT/"compile_1b_strict.json").write_text(json.dumps(res,indent=1))

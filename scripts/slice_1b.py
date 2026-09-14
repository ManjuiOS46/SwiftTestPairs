#!/usr/bin/env python3
"""Phase 1b v2 - compile harness, validated against HUMAN tests.

v1 put ONE source file in the package and 88% failed with "cannot find type X
in scope" - the focal file references siblings in its own module. v2 packages
the repo's whole source set (import-allowlisted, capped) alongside the test.

If a human's real shipped test will not compile here, that is a harness bug,
not a generation problem.
"""
import duckdb, subprocess, tempfile, pathlib, re, sys, os, json, collections
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT  = ROOT / "data" / "interim"
DB   = OUT / "slice.duckdb"
MOD  = "PairModule"
DEV  = "/Applications/Xcode.app/Contents/Developer"
ENV  = {**os.environ, "DEVELOPER_DIR": DEV}

N        = int(sys.argv[1]) if len(sys.argv) > 1 else 300
MAX_FILES = 300
MAX_BYTES = 3_000_000
ALLOW = ['Foundation','Swift','Dispatch','Darwin','os','CoreGraphics','Combine','ObjectiveC']

PKG = f'''// swift-tools-version:5.9
import PackageDescription
let package = Package(
    name: "{MOD}", platforms: [.macOS(.v13)],
    targets: [
        .target(name: "{MOD}", path: "Sources/{MOD}"),
        .testTarget(name: "{MOD}Tests", dependencies: ["{MOD}"], path: "Tests/{MOD}Tests"),
    ]
)
'''

def safe_name(path, i):
    stem = re.sub(r'[^A-Za-z0-9_]', '_', path.rsplit('/', 1)[-1].removesuffix('.swift'))
    return f"{i:03d}_{stem}.swift"

def build_one(job):
    idx, repo, spath, tpath, test_code, files = job
    with tempfile.TemporaryDirectory(prefix="pair_") as d:
        d = pathlib.Path(d)
        (d / f"Sources/{MOD}").mkdir(parents=True)
        (d / f"Tests/{MOD}Tests").mkdir(parents=True)
        (d / "Package.swift").write_text(PKG)
        for i, (p, c) in enumerate(files):
            (d / f"Sources/{MOD}" / safe_name(p, i)).write_text(c)
        test = re.sub(r'@testable\s+import\s+[A-Za-z_][A-Za-z0-9_]*', f'@testable import {MOD}', test_code)
        (d / f"Tests/{MOD}Tests/Tests.swift").write_text(test)
        try:
            p = subprocess.run(["swift", "build", "--build-tests"], cwd=d, env=ENV,
                               capture_output=True, text=True, timeout=300)
            ok  = p.returncode == 0
            out = "" if ok else ((p.stdout or "") + "\n" + (p.stderr or ""))[-6000:]
        except subprocess.TimeoutExpired:
            ok, out = False, "TIMEOUT"
        return {"idx": idx, "repo": repo, "source_path": spath, "test_path": tpath,
                "n_files": len(files), "ok": ok, "err": out}

def categorise(e):
    if e == "TIMEOUT": return "timeout"
    pats = [(r"cannot find type '?\w+'? in scope", "unresolved_type"),
            (r"cannot find '?\w+'? in scope",       "unresolved_symbol"),
            (r"no such module",                     "missing_module"),
            (r"invalid redeclaration|already exists|duplicate",  "duplicate_symbol"),
            (r"is inaccessible due to|not accessible",           "access_control"),
            (r"has no member",                      "no_member"),
            (r"extra argument|missing argument|argument passed", "signature_mismatch"),
            (r"value of type|type '.*' cannot",     "type_error"),
            (r"only available in macOS|unavailable","availability")]
    for p, n in pats:
        if re.search(p, e, re.I): return n
    return "other"

def main():
    con = duckdb.connect(str(DB), read_only=True)
    allow_sql = "[" + ",".join(f"'{a}'" for a in ALLOW) + "]"

    pairs = con.sql(f"""
      SELECT idx, repo_name, source_path, test_path, test_code FROM (
        SELECT row_number() OVER () AS idx, * FROM pairs_sc
        WHERE NOT contains(source_code,'import UIKit')
          AND NOT contains(source_code,'import SwiftUI')
      ) ORDER BY random() LIMIT {N}""").fetchall()
    print(f"sampled {len(pairs)} Foundation-only pairs")

    jobs = []
    for idx, repo, spath, tpath, tcode in pairs:
        files = con.execute(f"""
          SELECT path, content FROM labelled
          WHERE repo_name = ? AND kind='SOURCE'
            AND len(list_filter(regexp_extract_all(content,'import\\s+([A-Za-z_][A-Za-z0-9_]*)',1),
                                x -> NOT list_contains({allow_sql}, x))) = 0
          ORDER BY len(content) LIMIT {MAX_FILES}""", [repo]).fetchall()
        tot, keep = 0, []
        for p, c in files:
            if tot + len(c) > MAX_BYTES: break
            keep.append((p, c)); tot += len(c)
        if keep: jobs.append((idx, repo, spath, tpath, tcode, keep))

    print(f"{len(jobs)} packages to build; median module size "
          f"{sorted(len(j[5]) for j in jobs)[len(jobs)//2]} files\n")

    res = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for i, r in enumerate(ex.map(build_one, jobs), 1):
            res.append(r)
            if i % 25 == 0:
                print(f"  {i:>4}/{len(jobs)}  compile rate so far "
                      f"{sum(x['ok'] for x in res)/len(res):.1%}")

    ok = sum(r["ok"] for r in res)
    print(f"\n{'='*60}\n  COMPILE RATE: {ok}/{len(res)} = {ok/len(res):.1%}\n{'='*60}")
    fails = collections.Counter(categorise(r["err"]) for r in res if not r["ok"])
    for k, v in fails.most_common():
        print(f"    {k:20} {v:>4}  ({v/len(res):.1%})")
    print("\n  by module size:")
    for lo, hi in [(1,1),(2,5),(6,20),(21,100),(101,10**6)]:
        sub=[r for r in res if lo<=r["n_files"]<=hi]
        if sub: print(f"    {lo:>3}-{hi if hi<10**6 else '+':<4} files  n={len(sub):>4}  {sum(r['ok'] for r in sub)/len(sub):.1%}")
    (OUT / "compile_1b_v2.json").write_text(json.dumps(res, indent=1))
    print(f"\nwrote {OUT}/compile_1b_v2.json")

if __name__ == "__main__":
    main()

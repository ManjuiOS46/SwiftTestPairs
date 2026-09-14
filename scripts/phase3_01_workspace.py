#!/usr/bin/env python3
"""Phase 3 step 1 - build benchmark workspaces from tier-2 repos.

Each workspace = the repo reconstructed verbatim, with its Tests/ removed and
the human tests stashed separately as ground truth.
"""
import duckdb, pathlib, json, shutil, sys
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT, BENCH = ROOT/"data"/"interim", ROOT/"bench"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
con = duckdb.connect(str(OUT/"slice.duckdb"), read_only=True)

repos = con.sql(f"""SELECT repo_name, count(*) AS n_pairs
  FROM read_parquet('{ROOT}/data/release/swifttestpairs.parquet')
  WHERE tier=2 GROUP BY 1 ORDER BY n_pairs DESC {'LIMIT '+str(N) if N else ''}""").fetchall()
print(f"tier-2 repos: {len(repos)}")

man = []
for repo, npairs in repos:
    slug = repo.replace("/","__")
    ws = BENCH/slug
    # Never destroy a workspace: generated tests live here and are the benchmark's
    # primary evidence. Rebuild into a fresh suffixed directory instead.
    if ws.exists():
        if any((ws/"repo").rglob("*.swift.disabled")) or (ws/"generated").exists():
            print(f"  SKIP {slug}: holds generated output"); continue
        shutil.rmtree(ws)
    (ws/"repo").mkdir(parents=True); (ws/"human").mkdir()
    files = con.execute("SELECT path, content FROM corpus_mat WHERE repo_name=?", [repo]).fetchall()
    pairs = con.execute(f"""SELECT pair_id, source_path, test_path, target_type, n_assertions, n_test_methods
        FROM read_parquet('{ROOT}/data/release/swifttestpairs.parquet')
        WHERE tier=2 AND repo_name=?""", [repo]).fetchall()
    tests = {p[2] for p in pairs}
    nsrc = ntest = 0
    for p, c in files:
        if not p or c is None or ".." in p: continue
        rel = p.lstrip("/")
        is_test = rel in tests or "/Tests/" in "/"+rel or rel.startswith("Tests/")
        dest = (ws/"human"/rel) if is_test else (ws/"repo"/rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.write_text(c); ntest += is_test; nsrc += not is_test
        except Exception: pass
    # SwiftPM errors if a declared test target's directory is missing. Keep the
    # directories, drop only the files: that is the real "package with a test target
    # and nothing in it" case, which is exactly what TestForge is for.
    for t in tests:
        (ws/"repo"/t).parent.mkdir(parents=True, exist_ok=True)
    for d in (ws/"human").rglob("*"):
        if d.is_dir():
            (ws/"repo"/d.relative_to(ws/"human")).mkdir(parents=True, exist_ok=True)

    (ws/"manifest.json").write_text(json.dumps({
        "repo": repo, "slug": slug, "n_pairs": npairs,
        "source_files": nsrc, "human_test_files": ntest,
        "pairs": [{"pair_id":a,"source_path":b,"test_path":c2,"target_type":d,
                   "human_assertions":e,"human_test_methods":f} for a,b,c2,d,e,f in pairs]}, indent=1))
    man.append({"slug":slug,"repo":repo,"pairs":npairs,"src":nsrc,"tests":ntest})

(BENCH/"index.json").write_text(json.dumps(man, indent=1))
print(f"built {len(man)} workspaces")
print(f"  total pairs      : {sum(m['pairs'] for m in man):,}")
print(f"  median src files : {sorted(m['src'] for m in man)[len(man)//2]}")

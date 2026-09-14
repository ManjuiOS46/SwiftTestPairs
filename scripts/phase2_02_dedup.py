#!/usr/bin/env python3
"""Phase 2 step 2 - dedup (exact + near, within AND across sources) then repo splits.

1c measured 62.6% pair-level overlap between sources. Without this step those
duplicates straddle the train/test boundary and the benchmark measures memorisation.
Repo-level splitting alone does NOT catch them: the two crawls spell repo_name
differently for the same project.
"""
import duckdb, pathlib, time, hashlib, collections
from datasketch import MinHash, MinHashLSH
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "interim"
con = duckdb.connect(str(OUT/"slice.duckdb")); con.execute("PRAGMA threads=8")
con.execute("SET preserve_insertion_order=false"); con.execute("SET max_temp_directory_size='30GiB'")
t0=time.time()
def rule(t): print(f"\n{'='*66}\n{t}\n{'='*66}")

rule("ATTACH CONTENT HASHES")
con.execute("""CREATE OR REPLACE TABLE pairs3 AS
SELECT p.*,
  md5(s.content) AS src_h, md5(t.content) AS tst_h,
  md5(regexp_replace(trim(s.content),'\\s+',' ','g')) AS src_hn,
  md5(regexp_replace(trim(t.content),'\\s+',' ','g')) AS tst_hn,
  len(s.content) AS source_bytes, len(t.content) AS test_bytes
FROM pairs2 p
JOIN labelled2 s ON s.src=p.src AND s.repo_name=p.repo_name AND s.path=p.source_path
JOIN labelled2 t ON t.src=p.src AND t.repo_name=p.repo_name AND t.path=p.test_path""")
n0 = con.sql("SELECT count(*) FROM pairs3").fetchone()[0]
print(f"  pairs with hashes: {n0:,}")

rule("EXACT DEDUP (normalised content, cross-source)")
con.execute("""CREATE OR REPLACE TABLE pairs4 AS
SELECT * FROM pairs3 QUALIFY row_number() OVER (
  PARTITION BY src_hn, tst_hn
  ORDER BY (src='stackedu') DESC, n_assert DESC, source_bytes DESC) = 1""")
n1 = con.sql("SELECT count(*) FROM pairs4").fetchone()[0]
print(f"  {n0:,} -> {n1:,}   removed {n0-n1:,} ({(n0-n1)/n0:.1%})")
print("  (tie-break prefers stack_edu: it carries the quality score)")
print(con.sql("SELECT src, count(*) n FROM pairs4 GROUP BY 1 ORDER BY 1").df().to_string(index=False))

rule("NEAR-DUP (MinHash/LSH on test code, Jaccard 0.8)")
rows = con.sql("""SELECT p.rowid, t.content FROM pairs4 p
  JOIN labelled2 t ON t.src=p.src AND t.repo_name=p.repo_name AND t.path=p.test_path""").fetchall()
lsh = MinHashLSH(threshold=0.8, num_perm=64); keep=set(); drop=set()
for rid, c in rows:
    toks = c.split()
    sh = {" ".join(toks[i:i+5]) for i in range(max(len(toks)-4,1))}
    m = MinHash(num_perm=64)
    for s in sh: m.update(s.encode('utf8','ignore'))
    if lsh.query(m): drop.add(rid)
    else: lsh.insert(str(rid), m); keep.add(rid)
print(f"  {len(rows):,} -> {len(keep):,}   removed {len(drop):,} ({len(drop)/max(len(rows),1):.1%})")
con.execute("CREATE OR REPLACE TABLE keep_ids AS SELECT unnest(?::BIGINT[]) AS rid", [sorted(keep)])
con.execute("CREATE OR REPLACE TABLE pairs5 AS SELECT p.* FROM pairs4 p JOIN keep_ids k ON p.rowid=k.rid")
n2 = con.sql("SELECT count(*) FROM pairs5").fetchone()[0]

rule("REPO-LEVEL SPLIT (80/10/10)")
con.execute("""CREATE OR REPLACE TABLE repo_split AS
SELECT repo_name, CASE WHEN hash(repo_name)%10 < 8 THEN 'train'
                       WHEN hash(repo_name)%10 = 8 THEN 'valid' ELSE 'test' END AS split
FROM (SELECT DISTINCT repo_name FROM pairs5)""")
con.execute("CREATE OR REPLACE TABLE pairs6 AS SELECT p.*, r.split FROM pairs5 p JOIN repo_split r USING(repo_name)")
print(con.sql("""SELECT split, count(*) pairs, count(DISTINCT repo_name) repos
                 FROM pairs6 GROUP BY 1 ORDER BY 1""").df().to_string(index=False))
leak = con.sql("""SELECT count(*) FROM (
  SELECT src_hn, tst_hn FROM pairs6 GROUP BY 1,2 HAVING count(DISTINCT split)>1)""").fetchone()[0]
print(f"\n  LEAK CHECK - identical pairs across splits: {leak}  {'OK' if leak==0 else 'FAIL'}")

print(f"\n  FINAL: {n0:,} raw -> {n2:,} deduped pairs   ({time.time()-t0:.0f}s)")

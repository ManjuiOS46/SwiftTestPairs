#!/usr/bin/env python3
"""Phase 1c - cross-source overlap.

NOTE ON BIAS: only stack_edu shard 0 (20%) is local. So the only unbiased
direction is "what fraction of stack_edu files also appear in IVA" - a shard is
a random sample of stack_edu, and all of IVA is present. The reverse direction
would be understated 5x and is NOT reported as a rate.
"""
import duckdb, pathlib
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "interim"
con = duckdb.connect(str(OUT/"slice.duckdb")); con.execute("PRAGMA threads=8")

print("materialising content hashes (exact + whitespace-normalised)...")
con.execute("""CREATE OR REPLACE TABLE hashes AS
SELECT src, repo_name, path,
       md5(content) AS h_exact,
       md5(regexp_replace(trim(content), '\\s+', ' ', 'g')) AS h_norm,
       (contains(content,'import XCTest') OR contains(content,'import Quick'))
         AND regexp_matches(content,'func\\s+test[A-Z_0-9]') AS is_test
FROM classified""")
print(con.sql("SELECT src, count(*) files FROM hashes GROUP BY 1 ORDER BY 1").df().to_string(index=False))

def overlap(where, label):
    r = con.sql(f"""
      WITH a AS (SELECT DISTINCT h_exact, h_norm FROM hashes WHERE src='stackedu' {where}),
           b AS (SELECT DISTINCT h_exact FROM hashes WHERE src='iva' {where}),
           bn AS (SELECT DISTINCT h_norm FROM hashes WHERE src='iva' {where})
      SELECT (SELECT count(*) FROM a) AS stackedu_distinct,
             (SELECT count(*) FROM a JOIN b USING(h_exact)) AS exact_hit,
             (SELECT count(*) FROM a JOIN bn USING(h_norm))  AS norm_hit""").fetchone()
    n, e, w = r
    print(f"\n{label}")
    print(f"  stack_edu distinct files : {n:,}")
    print(f"  also in IVA (exact hash) : {e:,}  = {e/max(n,1):.1%}")
    print(f"  also in IVA (normalised) : {w:,}  = {w/max(n,1):.1%}")
    return w / max(n, 1)

print("\n" + "="*64)
all_r  = overlap("", "ALL permissive, non-vendored files")
test_r = overlap("AND is_test", "TEST files only")

print("\n" + "="*64)
print("REPO-level overlap")
print(con.sql("""
WITH a AS (SELECT DISTINCT repo_name FROM hashes WHERE src='stackedu'),
     b AS (SELECT DISTINCT repo_name FROM hashes WHERE src='iva')
SELECT (SELECT count(*) FROM a) AS stackedu_repos,
       (SELECT count(*) FROM b) AS iva_repos,
       (SELECT count(*) FROM a JOIN b USING(repo_name)) AS shared_repos,
       round(100.0*(SELECT count(*) FROM a JOIN b USING(repo_name))/(SELECT count(*) FROM a),1) AS pct_of_stackedu
""").df().to_string(index=False))

print("\n" + "="*64)
print("PAIR-level overlap (the number that actually matters)")
print(con.sql("""
WITH sp AS (SELECT DISTINCT md5(source_code)||':'||md5(test_code) AS k FROM pairs WHERE src='stackedu'),
     ip AS (SELECT DISTINCT md5(source_code)||':'||md5(test_code) AS k FROM pairs WHERE src='iva')
SELECT (SELECT count(*) FROM sp) AS stackedu_pairs,
       (SELECT count(*) FROM ip) AS iva_pairs,
       (SELECT count(*) FROM sp JOIN ip USING(k)) AS duplicate_pairs,
       round(100.0*(SELECT count(*) FROM sp JOIN ip USING(k))/(SELECT count(*) FROM sp),1) AS pct_stackedu_redundant
""").df().to_string(index=False))

print("\n" + "="*64)
r = test_r
verdict = ("UNION - keep both, cross-source dedup non-negotiable" if r < .50 else
           "JUDGEMENT CALL - likely IVA-only" if r < .70 else
           "DROP stack_edu as a source; keep only for its score column")
print(f"  TEST-file overlap = {r:.1%}  ->  {verdict}")

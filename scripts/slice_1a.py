#!/usr/bin/env python3
"""Phase 1a - join yield. Normalises both corpora, classifies files, joins pairs.

Outputs counts per source and a parquet of candidate pairs.
"""
import duckdb, sys, pathlib, textwrap

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW  = ROOT / "data" / "raw"
OUT  = ROOT / "data" / "interim"
OUT.mkdir(parents=True, exist_ok=True)

PERMISSIVE = ('mit','apache-2.0','bsd-2-clause','bsd-3-clause',
              'isc','cc0-1.0','unlicense','artistic-2.0')

con = duckdb.connect(str(OUT / "slice.duckdb"))
con.execute("PRAGMA threads=8")

def rule(title): print(f"\n{'='*68}\n{title}\n{'='*68}")

# ---------------------------------------------------------------- normalise
rule("LOADING")

iva_glob = str(RAW / "rawdump_swift*.json.gz")
se_glob  = str(RAW / "stackedu-*.parquet")

con.execute(f"""
CREATE OR REPLACE VIEW iva AS
SELECT
  'iva'                                        AS src,
  repo_name,
  regexp_replace(path, '^/', '')               AS path,
  content,
  license                                      AS license_raw,
  license IN {PERMISSIVE}                      AS permissive,
  CAST(NULL AS DOUBLE)                         AS score
FROM read_json_auto('{iva_glob}', format='newline_delimited', ignore_errors=true)
""")

con.execute(f"""
CREATE OR REPLACE VIEW stackedu AS
SELECT
  'stackedu'                                   AS src,
  repo_name,
  regexp_replace(path, '^/', '')               AS path,
  text                                         AS content,
  COALESCE(NULLIF(array_to_string(detected_licenses, ','), ''), license_type) AS license_raw,
  license_type = 'permissive'                  AS permissive,
  score
FROM read_parquet('{se_glob}')
WHERE download_success
""")

con.execute("CREATE OR REPLACE VIEW corpus AS SELECT * FROM iva UNION ALL SELECT * FROM stackedu")

for s in ("iva", "stackedu"):
    n = con.sql(f"SELECT count(*) FROM {s}").fetchone()[0]
    p = con.sql(f"SELECT count(*) FROM {s} WHERE permissive").fetchone()[0]
    print(f"  {s:9} rows={n:>9,}  permissive={p:>9,} ({p/max(n,1):.1%})")

# ---------------------------------------------------------------- classify
rule("CLASSIFY")

con.execute("""
CREATE OR REPLACE TABLE classified AS
SELECT *,
  regexp_extract(path, '([^/]+)\\.swift$', 1)                AS basename,
  contains(content, 'import XCTest')                         AS has_xctest,
  contains(content, 'import Quick')                          AS has_quick,
  contains(content, 'import Testing')                        AS has_swifttesting,
  regexp_matches(content, 'func\\s+test[A-Z_0-9]')            AS has_test_method,
  len(regexp_extract_all(content, 'XCTAssert|XCTUnwrap|XCTFail|#expect|#require')) AS n_assert,
  len(regexp_extract_all(content, 'func\\s+test[A-Z_0-9]'))   AS n_test_methods,
  contains(content, 'testPerformanceExample')                AS stub_marker,
  regexp_matches(path, '(^|/)(Tests?|Specs?)/')              AS in_test_dir
FROM corpus
WHERE permissive AND content IS NOT NULL
  -- vendored third-party trees: not the repo's own code, and they wreck the join
  AND NOT regexp_matches(path,
      '(^|/)(Pods|Carthage|Externals?|ThirdParty|third_party|vendor|node_modules|\\.build|Checkouts)/')
""")

con.execute("""
CREATE OR REPLACE TABLE labelled AS
SELECT *,
  CASE
    WHEN (has_xctest OR has_quick OR has_swifttesting) AND has_test_method THEN 'TEST'
    WHEN in_test_dir THEN 'TEST_SUPPORT'
    ELSE 'SOURCE'
  END AS kind
FROM classified
""")

print(con.sql("""
SELECT src, kind, count(*) AS n
FROM labelled GROUP BY 1,2 ORDER BY 1, 3 DESC
""").df().to_string(index=False))

rule("TEST-FILE QUALITY (permissive only)")
print(con.sql("""
SELECT src,
  count(*)                                      AS test_files,
  sum(stub_marker::INT)                         AS stub_marker,
  sum((n_assert = 0)::INT)                      AS zero_assert,
  sum((stub_marker OR n_assert < 3)::INT)       AS excluded,
  sum((NOT stub_marker AND n_assert >= 3)::INT) AS usable,
  round(median(n_assert),1)                     AS med_assert,
  sum(has_swifttesting::INT)                    AS swift_testing
FROM labelled WHERE kind='TEST' GROUP BY 1 ORDER BY 1
""").df().to_string(index=False))

# ---------------------------------------------------------------- join
rule("JOIN  (cheap basename convention)")

con.execute("""
CREATE OR REPLACE TABLE tests AS
SELECT *, regexp_replace(basename, '(Tests?|Specs?)$', '') AS target_type
FROM labelled
WHERE kind='TEST' AND NOT stub_marker AND n_assert >= 3
  AND regexp_matches(basename, '(Tests?|Specs?)$')
""")

con.execute("""
CREATE OR REPLACE TABLE pairs AS
SELECT
  t.src                AS src,
  t.repo_name          AS repo_name,
  t.target_type        AS target_type,
  s.path               AS source_path,
  t.path               AS test_path,
  s.content            AS source_code,
  t.content            AS test_code,
  t.n_assert           AS n_assert,
  t.n_test_methods     AS n_test_methods,
  s.score              AS source_score,
  t.score              AS test_score,
  t.license_raw        AS license_raw,
  len(s.content)       AS source_bytes,
  t.has_swifttesting   AS test_is_swifttesting
FROM tests t
JOIN labelled s
  ON s.repo_name = t.repo_name
 AND s.kind      = 'SOURCE'
 AND s.basename  = t.target_type
""")

print(con.sql("""
SELECT src,
  count(*)                        AS raw_pairs,
  count(DISTINCT repo_name)       AS repos,
  count(DISTINCT md5(test_code))  AS distinct_tests
FROM pairs GROUP BY 1 ORDER BY 1
""").df().to_string(index=False))

n_tests = con.sql("SELECT count(*) FROM tests").fetchone()[0]
n_pairs = con.sql("SELECT count(*) FROM pairs").fetchone()[0]
print(f"\n  joinable test files : {n_tests:,}")
print(f"  raw pairs           : {n_pairs:,}   (join rate {n_pairs/max(n_tests,1):.1%})")

rule("SELF-CONTAINED SUBSET (compile candidates)")
con.execute("""
CREATE OR REPLACE TABLE pairs_sc AS
SELECT * FROM pairs
WHERE source_bytes BETWEEN 200 AND 51200
  AND len(list_filter(
        regexp_extract_all(source_code, 'import\\s+([A-Za-z_][A-Za-z0-9_]*)', 1),
        x -> NOT list_contains(
          ['Foundation','UIKit','SwiftUI','Combine','CoreGraphics','CoreData',
           'Dispatch','Darwin','os','XCTest','Swift','ObjectiveC'], x))) = 0
""")
print(con.sql("""
SELECT src, count(*) AS self_contained, count(DISTINCT repo_name) AS repos
FROM pairs_sc GROUP BY 1 ORDER BY 1
""").df().to_string(index=False))
print(f"  total self-contained: {con.sql('SELECT count(*) FROM pairs_sc').fetchone()[0]:,}")

con.execute(f"COPY pairs TO '{OUT}/pairs_raw.parquet' (FORMAT parquet)")
con.execute(f"COPY pairs_sc TO '{OUT}/pairs_selfcontained.parquet' (FORMAT parquet)")
print(f"\nwrote {OUT}/pairs_raw.parquet and pairs_selfcontained.parquet")

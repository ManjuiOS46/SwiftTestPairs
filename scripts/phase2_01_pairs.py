#!/usr/bin/env python3
"""Phase 2 step 1 - full-corpus rebuild + declaration-index join.

Phase 1 joined on filename convention only (FooTests.swift -> Foo.swift), which
misses every type declared inside a differently-named file (Foo inside Models.swift).
This adds a per-repo index of DECLARED TYPES and joins on that too.
"""
import duckdb, pathlib, time
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "interim"
con = duckdb.connect(str(OUT/"slice.duckdb")); con.execute("PRAGMA threads=8"); con.execute("SET preserve_insertion_order=false")
con.execute("SET max_temp_directory_size='30GiB'")
t0 = time.time()

def rule(t): print(f"\n{'='*66}\n{t}\n{'='*66}")

PERM = ('mit','apache-2.0','bsd-2-clause','bsd-3-clause','isc','cc0-1.0','unlicense','artistic-2.0')
VENDOR = r'(^|/)(Pods|Carthage|Externals?|ThirdParty|third_party|vendor|node_modules|\.build|Checkouts)/'

rule("CLASSIFY (full corpus)")
con.execute(f"""CREATE OR REPLACE TABLE labelled2 AS
WITH base AS (
  SELECT src, repo_name, regexp_replace(path,'^/','') AS path, content, license_raw, score,
         CASE WHEN src='iva' THEN license_raw IN {PERM} ELSE permissive END AS permissive
  FROM corpus_mat
  WHERE content IS NOT NULL AND NOT regexp_matches(regexp_replace(path,'^/',''), '{VENDOR}')
), c AS (
  SELECT *, regexp_extract(path,'([^/]+)\\.swift$',1) AS basename,
    contains(content,'import XCTest') OR contains(content,'import Quick')
      OR contains(content,'import Testing') AS has_tfw,
    contains(content,'import Testing')                     AS has_swifttesting,
    len(regexp_extract_all(content,'func\\s+test[A-Z_0-9]')) AS n_test_methods,
    len(regexp_extract_all(content,'XCTAssert|XCTUnwrap|XCTFail|#expect|#require')) AS n_assert,
    contains(content,'testPerformanceExample')             AS stub_marker,
    regexp_matches(path,'(^|/)(Tests?|Specs?)/')           AS in_test_dir
  FROM base WHERE permissive
)
SELECT *, CASE WHEN has_tfw AND n_test_methods > 0 THEN 'TEST'
               WHEN in_test_dir THEN 'TEST_SUPPORT' ELSE 'SOURCE' END AS kind
FROM c""")
con.execute("""CREATE OR REPLACE TABLE labelled2 AS SELECT * FROM labelled2
  QUALIFY row_number() OVER (PARTITION BY src, repo_name, path ORDER BY length(content) DESC)=1""")
print(con.sql("SELECT src, kind, count(*) n FROM labelled2 GROUP BY 1,2 ORDER BY 1,3 DESC").df().to_string(index=False))

rule("DECLARATION INDEX  (repo -> declared type -> file)")
con.execute("""CREATE OR REPLACE TABLE decls AS
SELECT src, repo_name, path, basename,
       unnest(regexp_extract_all(content,
         '(?:^|\\n)\\s*(?:public\\s+|internal\\s+|final\\s+|open\\s+)*(?:class|struct|enum|protocol|actor)\\s+([A-Z][A-Za-z0-9_]*)', 1)) AS type_name
FROM labelled2 WHERE kind='SOURCE'""")
con.execute("""CREATE OR REPLACE TABLE decls AS
SELECT * FROM decls QUALIFY row_number() OVER
  (PARTITION BY repo_name, type_name ORDER BY (basename = type_name) DESC, length(path)) = 1""")
con.execute("CREATE INDEX IF NOT EXISTS idx_decls ON decls(repo_name, type_name)")
print(con.sql("SELECT count(*) declarations, count(DISTINCT repo_name) repos, count(DISTINCT type_name) AS n_types FROM decls").df().to_string(index=False))

rule("TESTS")
con.execute("""CREATE OR REPLACE TABLE tests2 AS
SELECT *, regexp_replace(basename,'(Tests?|Specs?)$','') AS target_type
FROM labelled2
WHERE kind='TEST' AND NOT stub_marker AND n_assert >= 3
  AND regexp_matches(basename,'(Tests?|Specs?)$')""")
print(con.sql("SELECT src, count(*) joinable_tests FROM tests2 GROUP BY 1 ORDER BY 1").df().to_string(index=False))

rule("JOIN  A) filename convention   B) declaration index")
con.execute("""CREATE OR REPLACE TABLE pairs2 AS
WITH by_name AS (
  SELECT t.src, t.repo_name, t.target_type, s.path AS source_path, t.path AS test_path,
         t.n_assert, t.n_test_methods, s.score AS source_score, t.score AS test_score,
         t.license_raw, t.has_swifttesting, 'filename' AS join_method
  FROM tests2 t JOIN labelled2 s
    ON s.src=t.src AND s.repo_name=t.repo_name AND s.kind='SOURCE' AND s.basename=t.target_type
), by_decl AS (
  SELECT t.src, t.repo_name, t.target_type, d.path AS source_path, t.path AS test_path,
         t.n_assert, t.n_test_methods, NULL::DOUBLE AS source_score, t.score AS test_score,
         t.license_raw, t.has_swifttesting, 'declaration' AS join_method
  FROM tests2 t JOIN decls d
    ON d.repo_name=t.repo_name AND d.type_name=t.target_type AND d.src=t.src
  WHERE d.basename <> t.target_type
), u AS (SELECT * FROM by_name UNION ALL SELECT * FROM by_decl)
SELECT * FROM u QUALIFY row_number() OVER
  (PARTITION BY src, repo_name, source_path, test_path ORDER BY join_method) = 1""")

print(con.sql("""SELECT join_method, src, count(*) pairs FROM pairs2
                 GROUP BY 1,2 ORDER BY 1,2""").df().to_string(index=False))
tot = con.sql("SELECT count(*) FROM pairs2").fetchone()[0]
p1  = con.sql("SELECT count(*) FROM pairs2 WHERE join_method='filename'").fetchone()[0]
print(f"\n  Phase 1 (filename only, 1 shard) : 16,133")
print(f"  Phase 2 filename join (full)     : {p1:,}")
print(f"  + declaration-index join         : {tot-p1:,}")
print(f"  TOTAL raw pairs                  : {tot:,}")
print(f"\n({time.time()-t0:.0f}s)")

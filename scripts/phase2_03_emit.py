#!/usr/bin/env python3
"""Phase 2 step 3 - tier assignment + emit references (NOT file contents).

Published rows carry identifiers, paths, content hashes and derived metadata.
Anyone reconstructs contents from the two public upstream HF datasets; we
redistribute no code. The novel contribution is the PAIRING, not the source.
"""
import duckdb, pathlib, json
ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT, REL = ROOT/"data"/"interim", ROOT/"data"/"release"
REL.mkdir(parents=True, exist_ok=True)
con = duckdb.connect(str(OUT/"slice.duckdb")); con.execute("PRAGMA threads=8")
con.execute("SET preserve_insertion_order=false")
def rule(t): print(f"\n{'='*66}\n{t}\n{'='*66}")

LEG = r"(\bGeneratorType\b|\bSequenceType\b|\bCollectionType\b|\bErrorType\b|\.characters\b|appendNewline|\bprintln\s*\(|dispatch_async\s*\(|NSURLSession\b)"

rule("TIER ASSIGNMENT (tier 2 = VERIFIED build, not merely eligible)")
con.execute(f"""CREATE OR REPLACE TABLE final AS
SELECT p.*,
  regexp_matches(s.content,'{LEG}') OR regexp_matches(t.content,'{LEG}') AS has_legacy_swift,
  (sp.repo_name IS NOT NULL) AS spm_buildable  -- VERIFIED: repo actually builds
FROM pairs6 p
JOIN labelled2 s ON s.src=p.src AND s.repo_name=p.repo_name AND s.path=p.source_path
JOIN labelled2 t ON t.src=p.src AND t.repo_name=p.repo_name AND t.path=p.test_path
LEFT JOIN verified_repos sp ON sp.repo_name=p.repo_name""")
con.execute("""CREATE OR REPLACE TABLE final AS
SELECT *, CASE WHEN spm_buildable AND NOT has_legacy_swift THEN 2 ELSE 1 END AS tier FROM final""")
print(con.sql("""SELECT tier, count(*) pairs, count(DISTINCT repo_name) repos,
  sum(has_legacy_swift::INT) legacy, round(median(n_assert),1) med_assert
  FROM final GROUP BY 1 ORDER BY 1""").df().to_string(index=False))
print(con.sql("SELECT tier, split, count(*) n FROM final GROUP BY 1,2 ORDER BY 1,2").df().to_string(index=False))

rule("EMIT (references + metadata; no file contents)")
con.execute(f"""COPY (
SELECT
  md5(src||':'||repo_name||':'||source_path||':'||test_path) AS pair_id,
  src AS source_corpus, repo_name, source_path, test_path, target_type,
  src_h AS source_content_md5, tst_h AS test_content_md5,
  source_bytes, test_bytes, n_assert AS n_assertions, n_test_methods,
  source_score, test_score,
  CASE lower(license_raw)
    WHEN 'mit' THEN 'MIT' WHEN 'apache-2.0' THEN 'Apache-2.0'
    WHEN 'bsd-3-clause' THEN 'BSD-3-Clause' WHEN 'bsd-2-clause' THEN 'BSD-2-Clause'
    WHEN 'isc' THEN 'ISC' WHEN 'cc0-1.0' THEN 'CC0-1.0'
    WHEN 'unlicense' THEN 'Unlicense' WHEN 'artistic-2.0' THEN 'Artistic-2.0'
    ELSE license_raw END AS license,
  has_swifttesting AS test_uses_swift_testing, has_legacy_swift, join_method,
  tier, split
FROM final ORDER BY tier, split, repo_name
) TO '{REL}/swifttestpairs.parquet' (FORMAT parquet)""")
con.execute(f"""COPY (SELECT * FROM read_parquet('{REL}/swifttestpairs.parquet'))
             TO '{REL}/swifttestpairs.jsonl' (FORMAT json)""")
n = con.sql(f"SELECT count(*) FROM read_parquet('{REL}/swifttestpairs.parquet')").fetchone()[0]
print(f"  wrote {n:,} rows")
for f in sorted(REL.iterdir()):
    print(f"    {f.name:34} {f.stat().st_size/1e6:.1f} MB")

stats = {
 "pairs": n,
 "tier1": con.sql("SELECT count(*) FROM final WHERE tier=1").fetchone()[0],
 "tier2": con.sql("SELECT count(*) FROM final WHERE tier=2").fetchone()[0],
 "repos": con.sql("SELECT count(DISTINCT repo_name) FROM final").fetchone()[0],
 "by_split": dict(con.sql("SELECT split, count(*) FROM final GROUP BY 1").fetchall()),
 "by_source": dict(con.sql("SELECT src, count(*) FROM final GROUP BY 1").fetchall()),
 "swift_testing": con.sql("SELECT sum(has_swifttesting::INT) FROM final").fetchone()[0],
 "legacy": con.sql("SELECT sum(has_legacy_swift::INT) FROM final").fetchone()[0],
}
(REL/"stats.json").write_text(json.dumps(stats, indent=2))
print("\n" + json.dumps(stats, indent=2))

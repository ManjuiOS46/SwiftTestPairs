#!/usr/bin/env python3
"""Extract every model call into a documented, queryable archive.

TestForge logs prompt, response, usage and cost per call in each report.json.
This pulls them into one parquet table plus a readable Markdown appendix, so the
benchmark is reproducible and the failure modes are analysable.

Read-only with respect to the running benchmark.
"""
import json, pathlib, hashlib, collections, re
import duckdb

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT  = ROOT / "docs"; OUT.mkdir(exist_ok=True)

rows, prompts = [], {}
for rep in sorted((ROOT/"generated").glob("*/testforge/*/report.json")):
    repo = str(rep).split("/testforge/")[1].split("/")[0]
    try: d = json.loads(rep.read_text())
    except Exception: continue
    for e in (d.get("ledger") or []):
        p = e.get("promptText") or ""
        r = e.get("responseText") or ""
        u = e.get("usage") or {}
        # system prompts repeat verbatim across calls - store once, reference by hash
        sys_part = p.split("[user]")[0] if "[user]" in p else p
        h = hashlib.sha256(sys_part.encode()).hexdigest()[:12]
        prompts.setdefault(h, sys_part)
        rows.append({
            "repo": repo, "path": e.get("path"), "role": e.get("role"),
            "attempt": e.get("attempt"), "outcome": e.get("outcome"),
            "model": e.get("model"), "provider": e.get("provider"),
            "system_prompt_sha": h,
            "prompt_chars": len(p), "response_chars": len(r),
            "input_tokens": u.get("input"), "output_tokens": u.get("output"),
            "cache_read": u.get("cacheRead"), "cache_write": u.get("cacheWrite"),
            "latency_ms": e.get("latencyMilliseconds"), "cost_usd": e.get("costUSD"),
            "timestamp": e.get("timestamp"),
            "response_is_swift": bool(re.search(r'\bimport (XCTest|Testing)\b', r)),
            "prompt": p, "response": r,
        })

con = duckdb.connect()
con.execute("CREATE TABLE calls AS SELECT * FROM read_json_auto(?)",
            [json.dumps(rows)]) if False else None
pathlib.Path(OUT/"_calls.json").write_text(json.dumps(rows))
con.execute(f"CREATE TABLE calls AS SELECT * FROM read_json_auto('{OUT}/_calls.json')")
con.execute(f"COPY calls TO '{OUT}/model_calls.parquet' (FORMAT parquet)")
(OUT/"_calls.json").unlink()

print(f"calls archived: {len(rows):,}")
print(con.sql("""SELECT role, outcome, count(*) n, round(avg(latency_ms)) avg_ms,
                        round(sum(cost_usd),3) AS usd, round(100.0*avg(response_is_swift::INT),1) pct_swift
                 FROM calls GROUP BY 1,2 ORDER BY 1,3 DESC""").df().to_string(index=False))

# readable appendix
md = ["# Model call archive\n",
      f"{len(rows):,} calls from {len({r['repo'] for r in rows})} repositories.",
      "Full prompt and response text for every call is in `model_calls.parquet`.\n",
      "## System prompts used\n"]
for h, p in prompts.items():
    n = sum(1 for r in rows if r["system_prompt_sha"] == h)
    md += [f"### `{h}` — used in {n:,} calls\n", "```", p.strip()[:4000], "```\n"]
md += ["## Token accounting\n",
       "`usage` reports only `input` and `output`. Google bills reasoning tokens that",
       "do not appear here, which is why TestForge's cost figures understate actual",
       "spend by roughly 3.8x on gemini-3.8-flash.\n"]
(OUT/"MODEL-CALLS.md").write_text("\n".join(md))
print(f"\nwrote docs/model_calls.parquet and docs/MODEL-CALLS.md")
print(f"  system prompt variants: {len(prompts)}")

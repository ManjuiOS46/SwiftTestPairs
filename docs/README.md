# Results and evidence

| File | What it is |
|---|---|
| `benchmark_results.json` | Per-repo results for all 104 benchmarked repositories, with contamination and budget-truncation flags |
| `human_coverage.json` | Coverage achieved by the repositories' own test suites |
| `collective_baseline.json` / `collective_testforge.json` | Files surviving when each arm's whole output is built together |
| `qwen_results.json` | The on-device arm, 19 repositories |
| `case_counts.json` | Human vs generated test-case counts per repository |
| `final_comparison.json` | The matched subset behind the headline table |
| `model_calls.parquet` | **1,528 model calls with full prompt and response text**, tokens, latency and cost |
| `MODEL-CALLS.md` | Readable appendix: the 67 system-prompt variants used |
| `site/` | Two explainer pages (open `index.html` and `dataset.html` in a browser) |

`model_calls.parquet` is the methodology record. Every prompt sent and every
response received during the benchmark is in it, so any figure here can be traced
back to the exact exchange that produced it.

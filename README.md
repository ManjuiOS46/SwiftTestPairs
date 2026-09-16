# SwiftTestPairs

**The first public dataset of Swift source↔unit-test pairs — and a benchmark of an
AI test generator against the engineers who wrote the code.**

📦 **Dataset:** [huggingface.co/datasets/Manju46/swift-test-pairs](https://huggingface.co/datasets/Manju46/swift-test-pairs)  
🐦 **Sibling:** [KotlinTestPairs](https://github.com/ManjuiOS46/KotlinTestPairs) — same methodology, 9,856 Kotlin pairs, and why Kotlin can have no verified tier

---

## What this is

To measure whether a machine writes good unit tests, you need an answer key: real
tests, written by real engineers, for real code, matched up so you know which test
belongs to which file. Java has had one since 2022 — Microsoft's
[methods2test](https://arxiv.org/abs/2203.12776), 780k pairs. Swift had nothing.

This repository builds that answer key for Swift, then uses it.

| | |
|---|---|
| Pairs published | **20,801** from 3.2M source files |
| Verified to compile on Swift 6.4 | **569** |
| Repositories benchmarked | **104** |
| Model calls archived, with prompts and responses | **1,528** |

## The headline result

**An agentic test generator reached the same coverage as the humans who wrote the code.**

| 25 repositories | Human | Plain prompt | TestForge (cloud) | TestForge (on-device) |
|---|---|---|---|---|
| Test files produced | 156 | 132 | 237 | 91 |
| Files compiling together | — | 123 | 216 | — |
| Repos with a green build | 18/25 | 22/25 | 21/25 | — |
| **Mean line coverage** | **79.4%** | not measured | **79.3%** | — |

Four arms, same repositories, marked identically. Median coverage actually favoured
the tool: 88.4% against 86.6%.

**What it does not show:** the scaffolding doesn't make the model write *better*
Swift — a plain prompt's output survives at 93.2%, the tool's at 91.1%, and that gap
is noise. What the verify-and-repair loop buys is scale and a build that cannot
break. And in 27% of repositories the tool produced nothing usable at all.

## The finding we went looking for by accident

Public Swift code is far more out of date than anyone assumes. Each of these was
confirmed across **two independently collected corpora**:

| | |
|---|---|
| Pairs that still compile on Swift 6.4 | **2.7%** |
| Using Swift Testing (Apple's current framework, 2024) | **0.6%** |
| Using async/await (shipped 2021) | **0.4%** of source files |
| Containing Swift 2/3 syntax no compiler accepts | **7.2%** |

Models learn Swift from this material. They will confidently write the dialect it
contains.

## How to reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install duckdb pandas datasketch
bash scripts/00_fetch.sh                       # ~3.3 GB from Hugging Face
.venv/bin/python scripts/phase2_01_pairs.py    # classify + join
.venv/bin/python scripts/phase2_02_dedup.py    # dedup + repo-level splits
.venv/bin/python scripts/phase2_03_emit.py     # emit the dataset
```

Benchmark reproduction additionally needs [TestForge](#testforge) and a provider key:

```bash
export TESTFORGE_BIN=/path/to/testforge/.build/debug/testforge
.venv/bin/python scripts/phase3_01_workspace.py   # build benchmark workspaces
.venv/bin/python scripts/phase3_02_benchmark.py   # run it
.venv/bin/python scripts/phase3_04_analyse.py     # recount from disk
```

## Layout

```
scripts/     the pipeline, in the order it runs
docs/        results, the model-call archive, two explainer pages
PLAN.md      the full working record, including every gate and dead end
```

`docs/site/index.html` and `docs/site/dataset.html` are written for a reader who
knows nothing about the project. Open them in a browser.

## Design decisions worth knowing

**References, not code.** The dataset ships repository names, file paths, content
fingerprints and measurements — no source. `resolve.py` rebuilds the real files from
the two public corpora and verifies each against its fingerprint. That keeps the
artifact at 3.2 MB, avoids redistributing anyone's work, and means a file withdrawn
upstream simply stops resolving.

**Permissive licences only.** MIT, Apache-2.0, BSD and similar. Unlicensed code is
all-rights-reserved by default, whatever people assume.

**Split by repository, never by file.** Files from one project share conventions and
helpers; splitting by file leaks a project's style across the boundary. Verified:
zero pairs straddle.

**Deduplicated twice.** The two corpora overlap 62.6% at pair level. Left in, the
same test lands on both sides of a split and any model trained on it is scored on
work it has already seen.

## Eleven bugs that produced plausible wrong answers

Not one of them crashed. Every one returned a number that looked like a finding —
`swift build` writing errors to stdout, a DuckDB connection shared across threads,
a join missing an equality check, coverage counting the test runner itself so an
empty package read as 99.73% covered.

The tell was almost always a suspiciously round number: `$0.0000`, zero rows,
exactly 100%. A tool that genuinely tried and failed still costs money and still
returns rows. **Perfectly clean output usually means nothing ran.**

The full list, with cause and consequence, is in [PLAN.md](PLAN.md) §14. It is the
most useful thing in this repository.

## TestForge

The benchmark drives **TestForge**, an agentic test generator
that indexes a project, writes tests, compiles them, repairs what fails and
quarantines what it cannot fix. It is a separate project, not published here — the scripts invoke it as an
external binary via `--draft-provider` / `--repair-provider`.

## Sources

- [`mvasiliniuc/iva-swift-codeint`](https://huggingface.co/datasets/mvasiliniuc/iva-swift-codeint) — Google BigQuery's public GitHub dataset
- [`HuggingFaceTB/stack-edu`](https://huggingface.co/datasets/HuggingFaceTB/stack-edu) — Software Heritage → The Stack v2 → quality filtered

Per-row licences are in the dataset's `license` column. Methodology follows
methods2test (MSR 2022), applied to a language that had no equivalent.

## Licence

The pipeline code in this repository is MIT licensed — see [LICENSE](LICENSE).

That covers the code only. The **dataset** it produces carries the licences of the
repositories it references: each row records its own in the `license` column, and
only permissively licensed code (MIT, Apache-2.0, BSD and similar) was included. No
source code is redistributed here or in the dataset.

## Citation

```bibtex
@misc{swamymanju2026swifttestpairs,
  title  = {SwiftTestPairs: Swift source-to-test pairs for test generation research},
  author = {Swamy Manju},
  year   = {2026},
  url    = {https://huggingface.co/datasets/Manju46/swift-test-pairs}
}
```

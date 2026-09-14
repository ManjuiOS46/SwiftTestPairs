# SwiftTestPairs — Plan & Fact Log

**Status:** PHASES 1-3 COMPLETE. Dataset built and benchmark run. Nothing published yet.
**Last updated:** 2026-09-14 (v7 — Phase 3 complete)

---

## 1. Goal

Two deliverables from one pipeline:

1. **SwiftTestPairs** — a dataset of Swift source↔unit-test pairs ("focal method"
   pairs), reconstructed from public permissively-licensed GitHub code and published
   to Hugging Face as *references + metadata*, not file contents.
2. **A benchmark** of TestForge against those pairs: does an agentic test generator
   match the tests real engineers wrote?

**Why it's worth doing:** no Swift source↔test pair dataset exists publicly (verified,
see §4). The methodology is established for Java; Swift is the gap.

**One-line framing (use this, not "I built the first ever"):**
> Swift had no equivalent of methods2test, so I ported the methodology and published it.

---

## 2. Measured facts

All verified 2026-09-13 against the HF API / dataset viewer. Do not re-derive.

### 2A. Source A — `hongliu9903/stack_edu_swift`

| Fact | Value |
|---|---|
| Total rows | ~2,454,309 Swift files |
| Storage | 5 parquet shards, 554 MB each (~2.7 GB) |
| Published | 2025-07-31 (never updated) |
| **Content vintage** | **~2023** |
| **License declared on the repackaging** | **NONE** — no `license:*` tag; README is auto-generated schema only |
| Columns | `blob_id`, `language`, `repo_name`, `path`, `src_encoding`, `length_bytes`, `score`, `int_score`, `detected_licenses`, `license_type`, `text`, `download_success` |

**Lineage:** Software Heritage crawl → The Stack v2 → StarCoder2Data →
Stack-Edu (2025-03) → this repackaging (2025-07).
StarCoder2 paper is arXiv 2402.19173 (Feb 2024), so content necessarily predates it.

⚠️ Upstream Stack-Edu ships **only SWHIDs**, explicitly "to ensure data compliance."
This repackaging resolved them to file contents — materialising what upstream chose
not to distribute. **Cite Stack-Edu / The Stack v2 as provenance, not this mirror.**

**Licenses:** permissive 509,041 (26%) · no_license 1,454,407 (74%).
`no_license` = none detected = **all rights reserved**, NOT public domain.

**Quality (`score`)** — pre-filtered upstream at threshold 3/5.
Min 2.52 / median 2.78 / max 5.63.

| Band | Count |
|---|---|
| 2.5–2.8 | 1,080,683 |
| 2.8–3.1 | 563,907 |
| 3.1–3.4 | 188,495 |
| 3.4–3.8 | 66,714 |
| 3.8–4.1 | 34,519 |
| 4.1+ | 29,130 |

Permissive ∩ score≥4 ≈ **~16K files**.

### 2B. Source B — `mvasiliniuc/iva-swift-codeint`

| Fact | Value |
|---|---|
| Total rows | 753,693 Swift files |
| Storage | 7 × `json.gz`, **~700 MB total** (cheaper than ONE stack_edu shard) |
| Published | 2023-04-04, last modified 2023-06-16 |
| Content vintage | ~2023 |
| Dataset license | `other`, with **per-file SPDX names** in the `license` column |
| DOI | 10.57967/hf/0778 |
| Columns | `repo_name`, `path`, `copies`, `size`, `content`, `license` |

**Lineage:** Google BigQuery `bigquery-public-data.github_repos`. The extraction SQL
`JOIN`s the **licenses** table, so **every row has a declared license by construction**
— unlicensed repos are excluded. Also deduplicated at extraction
(`row_number() ... seqnum=1`); the `copies` column records how many copies existed.

**Licenses — 90.4% permissive:**

| Class | Count | Share |
|---|---|---|
| **Permissive** (mit 476,518 · apache-2.0 180,178 · bsd-3 11,429 · bsd-2 5,342 · unlicense 3,277 · cc0 2,718 · isc 1,647 · artistic-2.0 314) | **681,423** | **90.4%** |
| Weak copyleft (mpl-2.0) | 11,799 | 1.6% |
| Strong copyleft (gpl-3.0 33,074 · gpl-2.0 15,751 · lgpl-3.0 6,150 · agpl-3.0 2,775 · lgpl-2.1 1,741 · epl-1.0 980) | 60,471 | 8.0% |

**Minor card inconsistency:** creation notes say 464,215 rows extracted; the dataset
has 753,693. Note it, don't rely on the card's narrative numbers.

**No quality score.** Uncurated — no educational filter applied.

### 2C. Test-code content — both sources

| Query | Source A (stack_edu) | Source B (IVA) |
|---|---|---|
| `import XCTest` | 57,258 | **75,009** |
| `XCTAssert*` | 51,487 | not measured |
| `Spec` in path (Quick/Nimble) | 6,485 | not measured |
| Files under `Tests/` path | 68,045 | not measured |
| **`import Testing` (Swift Testing)** | **118** | **243** |
| Template stubs (`testPerformanceExample`) | 3,922 (**6.9%**) | 17,537 (**23.4%**) |
| Non-stub test files | ~53,300 | ~57,500 |
| Permissive ∩ XCTest | 27,941 (48.8%) | ~67,800 *(est.)* |
| **Permissive non-stub (working pool)** | **~26,000** | **~52,000** *(est.)* |

IVA's permissive figures are **estimates** (90.4% × 75,009, minus the stub rate).
The remote query failed twice — HF rate-limit, and `NOT LIKE` unsupported.
**Compute exactly in Phase 1.** Likely *conservative*: stack_edu showed test-bearing
files skew more licensed than the corpus (48.8% vs 26%), so the same skew should
favour IVA too.

**Three findings worth publishing:**
- **Swift Testing is absent from both corpora** (118 and 243) — verified through **two
  independent crawl routes** (Software Heritage and BigQuery). Not a filtering artifact;
  a property of public Swift as of 2023. Apple shipped Swift Testing Sept 2024.
- **74% of public Swift code (stack_edu) carries no detected license.**
- **Repos that write tests are ~2× more likely to be licensed** (48.8% vs 26%).

### 2D. Source comparison

| | IVA (B) | stack_edu (A) |
|---|---|---|
| Permissive pool | **681,423 (90.4%)** | 509,041 (26%) |
| License labels | **named SPDX** | bucketed, unverifiable |
| Unlicensed rows | **0** | 1,454,407 |
| Quality score | none | **yes** |
| Stub rate | 23.4% | **6.9%** |
| Self-deduplicated | **yes** | partially (upstream) |
| Download size | **~700 MB** | 2.7 GB |
| Documentation | **full card, SQL, DOI** | none |

**Strategy: use BOTH as a union, IVA as the primary permissive source.**
Prefer IVA rows on license questions (named SPDX beats an unverifiable bucket);
prefer stack_edu rows where the quality score is needed.

### 2E. Yield expectation

| Stage | Count |
|---|---|
| Combined permissive non-stub test files (est.) | ~78,000 |
| **minus unknown cross-source overlap** | **← the deciding number** |
| after join + dedup, single-source baseline | **8,000–15,000 pairs** |

⚠️ Test-file counts are NOT pair counts. Every test file must still find its source.


### 2G. PHASE 1 RESULTS (measured 2026-09-13, local run)

Corpora on disk: IVA all 7 shards + stack_edu shard 0 (1.2 GB). DuckDB 1.5.5.

**1a — JOIN YIELD: PASS**

| | IVA | stack_edu (shard 0 = 20%) |
|---|---|---|
| Rows | 753,693 | 490,862 |
| Permissive | 681,423 (90.4%) | 127,060 (25.9%) |
| TEST / TEST_SUPPORT / SOURCE | 60,367 / 11,593 / 576,960 | 6,359 / 1,376 / 118,746 |
| Usable (non-stub, >=3 asserts) | 29,121 | 4,841 |
| **Raw pairs** | **15,319** | **814** |
| Self-contained | 10,487 | 663 |
| Median assertions/test file | **2.0** | **8.0** |
| Stub rate | 26.4% | 4.0% |

**16,133 raw pairs · join rate 52.2% · 11,150 self-contained · 9,810 legacy-free.**
Projected full-corpus (stack_edu x5): **~19,400 pairs** before cross-source dedup.

- IVA yields ~4x more pairs; stack_edu yields far BETTER ones (median 8 vs 2
  assertions). Quality-vs-quantity split — keep both regardless of 1c.
- Import profile of self-contained: 9,313 Foundation-only / 1,837 UIKit-SwiftUI.
- Vendored trees (`Pods/`, `Carthage/`...) had to be excluded before the join — an
  MIT repo routinely contains third-party source it did not write.

**1b — COMPILE HARNESS: WEAK.** Four designs:

| Design | Rate | Verdict |
|---|---|---|
| v1 one file per package | 11.8% | INVALID — captured stderr; `swift build` logs to **stdout** |
| v2 whole repo flattened into one module | 5.3% | rate FELL as module grew |
| strict — clean repos, all-Apple imports | 0/136 | — |
| SPM v1 — repo's own Package.swift | 11.5% | INVALID — see thread-safety bug below |
| **SPM v2 — same, bugs fixed** | **50.5%** | 101/200, manifest found 200/200 |

**THREAD-SAFETY BUG (important, will recur).** SPM v1 called `con.execute()` from
5 ThreadPoolExecutor workers on ONE DuckDB connection. DuckDB connections are not
safe for concurrent use: queries returned empty results at random, producing 82
phantom `NO_MANIFEST` failures. No exception, no warning — just silently wrong data.
Fix: pre-fetch serially, build in parallel on plain Python data.
Same failure shape as the dedup risk 1c caught: wrong results that look like findings.

**PERFORMANCE.** `corpus` is a VIEW over 3.3 GB parquet + 850 MB json.gz — it rescans
everything per query. Materialise once: `corpus_mat` = 3,208,002 rows (753,693 IVA +
2,454,309 stack_edu), 33s, indexed on `repo_name`. Never query the view in a loop.

Root causes (diagnosed, not guessed — 116 unresolved-type failures traced):
- **49.8% of missing types are NOT in the repo at all** (external SPM/Pods deps).
  Unrecoverable from a file-level corpus at any effort.
- **Real repos are multi-target.** Rejected imports were the repos' own sibling
  targets (`KsApi`, `Prelude`, `Library`, `RSCore`, `Account`). Flattening breaks it
  both ways: duplicate symbols + unresolved sibling modules.
- **Swift 4.x manifests**: 49% of found-manifest failures. Unsupported by Swift 6.4.

**MEASURED Tier 2 (post-fix): 50.5% build rate → ~1,012 verified pairs of 2,004
eligible** (tools-version >= 5, no external deps, no legacy markers).
Eligible fell 4,251 → 2,004 from the tools-version filter; Tier 2 doubled because
the RATE quadrupled, not because the pool grew.
Still computed against single-shard `pairs`; the Phase 2 full 1a re-run should lift
eligible ~20% → **Tier 2 ≈ 1,200**. Credible benchmark size: SWE-bench Lite is 300,
TestGenEval-lite ~160.

Residual failures: `missing_module` 21.5% (targets lost to the permissive/vendored
filters), `other` 13.0%. Recoverable in principle; diminishing returns.

Gate 1b on the plan's scale: **WEAK** (PASS needs >=60%) but near the top of the band.

**NEW FINDING — corpus staleness has THREE independent legs, all measured:**
1. **Swift Testing absent** — 118 (stack_edu) / 243 (IVA), two separate crawl routes
2. **11.4% of pairs contain Swift 2/3 syntax** no current toolchain accepts —
   `.characters` 1,582 · `SequenceType` 931 · `ErrorType` 806 ·
   `dispatch_async(` 627 · `NSURLSession` 589 · `println(` 556
3. **~26% of SPM manifests are tools-version 4.x** (378 + 144 of 4,205), unsupported
   by Swift 6

This is now the strongest research contribution — stronger than the dataset itself.

**1c — CROSS-SOURCE OVERLAP: DONE.** Only stack_edu shard 0 is local, so the sole
unbiased direction is "fraction of stack_edu also present in IVA".

| Level | overlap |
|---|---|
| All permissive files | 17.8% |
| Test files | 24.0% |
| Repos (7,173 of 54,103 shared) | 13.3% |
| **Pairs** | **62.6%** |

File-level and pair-level diverge sharply: the crawls cover different repos, but
pairs are *selected* for well-tested convention-following code — i.e. the popular
projects both crawls caught. **Use the pair-level number for decisions.**

stack_edu contributes 754 pairs, 472 already in IVA → **282 unique (≈1,410 across
5 shards)** vs IVA's 14,629. A ~10% quantity gain.

**DECISION: keep both.** Not for volume — for (a) quality: stack_edu median 8
assertions vs IVA 2; (b) the `score` column, without which the Phase 3 stratified
analysis cannot exist; (c) cost is ~2.1 GB.

⚠️ **1c validated the dedup rule.** Without cross-source dedup, 472 of 754
stack_edu pairs would straddle the train/test split — and repo-level splitting
would NOT catch them, since the two crawls can spell `repo_name` differently for
the same project. The benchmark would have silently measured memorisation.

### 2F. Unverified / open

- **Cross-source overlap.** Both crawl public GitHub Swift from ~2023. Only measurable
  locally by content hashing. **→ Phase 1c.**
- Exact permissive ∩ XCTest ∩ non-stub for IVA. → Phase 1.
- License composition *inside* stack_edu's `permissive` bucket. HF viewer index is
  permanently cold for it (5 attempts failed). → local groupby in Phase 1.
  Largely moot: IVA's named licenses sidestep the question for its half.

---

## 3. Related dataset worth pulling

`Razvan27/swift_test` — 127 shards, undocumented, same Stack v2 lineage, richer metadata:
`is_generated`, `is_vendor`, `star_events_count`, `fork_events_count`, `duplicates`,
`revision_date`, `gha_license_id`.

`is_generated` + `is_vendor` solve generated-code filtering for free. `duplicates`
assists dedup. Join on `blob_id`.

---

## 4. Prior art (verified)

| Dataset | Language | Who | Venue / date |
|---|---|---|---|
| **methods2test** — 780K pairs, 91K repos | Java | **Microsoft** | **MSR 2022, Data & Tool track** (arXiv 2203.12776) |
| TestGenEval | Python | kjain14 | 2024-10 |
| gitbug-java-unit-test-generation | Java | arksap | — |
| Code-TREAT/unit_test_generation | Python | — | 2025-09 (no Swift config) |
| julia-focal-method | Julia | dongg18 | 2025-06 |
| livecodebench/test_generation | Python | — | — |

**No Swift equivalent exists.** False alarms ruled out:
- `Kikor/testgenevallite_coder7b_swift` — "swift" = Alibaba's `ms-swift` framework;
  prompts inside are Python.
- `orcn/swifttest` — folders of JPEGs.

**Read arXiv 2203.12776 before writing join code.** It defines the focal-method /
focal-class mapping heuristics — the hard part of Phase 2. Use their vocabulary:
**"focal method"**, **"focal class"**.

---

## 5. Phases and gates

Gates, not steps. A failed gate stops the project having cost hours, not weeks.

### Phase 1 — THE SLICE ⟨GATE⟩ · ~1 afternoon + 1 hour

**1a — Join yield.** One stack_edu shard (554 MB, 20% sample) + IVA whole (~700 MB).
Filter permissive. Classify TEST / TEST_SUPPORT / SOURCE. Join by cheap basename
convention (no SwiftSyntax yet). **Measure each source separately before merging.**
Also run: exact IVA permissive∩XCTest∩non-stub, and the stack_edu license groupby (§2F).

- PASS: extrapolated ≥ 8K pairs
- WEAK: 3–8K → proceed, add SwiftSyntax type index in Phase 2
- KILL: < 3K → convention doesn't hold in Swift; stop and rethink

**1b — Compile harness, validated against humans.** 500 pairs. Minimal SPM package
per pair: source + **the human's own test**. `swift build`.

> **Key trick: the human test is the harness's unit test.** If a real shipped test
> won't compile in your harness, that's a harness bug — not a generation problem.
> Isolate harness defects before TestForge is involved.

- PASS: ≥ 60% of human tests compile
- WEAK: 30–60% → tighten self-contained filter (imports ⊆ Foundation/UIKit/SwiftUI/Combine), re-measure
- KILL: < 30% after filtering → drop coverage metrics, keep assertion-density only

**1c — Cross-source overlap.** Content-hash the test-file subset of both sources.
Report the intersection. ~1 hour.

- Overlap **< 50%** → adopt the union; cross-dataset dedup becomes non-negotiable
- Overlap **50–70%** → judgement call; likely IVA-only (better licenses, smaller, documented)
- Overlap **> 70%** → drop stack_edu as a source, keep it only for the `score` column

**All gates pass → Phase 2. Any kill → stop and write up what you learned.**

### Phase 2 — Full dataset · ~2–3 days

**TIERED, per Phase 1 results.** Do not chase compile rate — SELECT for it.
- **Tier 1 (~19K pairs)** — all pairs. Retrieval, idiom mining, assertion-density.
  Compilation irrelevant. This carries the "first for Swift" claim.
- **Tier 2 (~1,000–1,200, MEASURED)** — verified-compiling subset: SPM repos, own
  manifest, tools-version >= 5.0, no external deps, no legacy markers. 50.5% of
  eligible repos build clean. Benchmark runs here and nowhere else.

- All shards from whichever sources survived 1c
- SwiftSyntax classification + per-repo declared-type index (yield upgrade: catches
  `Foo` declared inside `Models.swift`, which basename matching misses)
- Filters: stubs, size bounds (drop >50 KB and <200 B), ≥3 assertions, ≥1 test method
- **MinHash/LSH dedup** — NON-NEGOTIABLE
- **Cross-source dedup on content hash** — NON-NEGOTIABLE if union adopted (no shared
  ID: IVA has no `blob_id`)
- **Split by repo, not by file** — NON-NEGOTIABLE
- Emit references + metadata, NOT file contents (see §7)

**Done when:** reproducible artifact + written dataset card.

### Phase 3 — Benchmark · ~2 days

Three arms, always: **human** / **raw local model** / **TestForge**.
Without the middle arm you cannot prove the agentic scaffolding earns its complexity.

Metrics by cost:
1. Assertion density (SwiftSyntax, no build) — Tier 1, always obtainable
2. Compile rate — **Tier 2 only** (~1,000–1,200 pairs)
3. Coverage delta (`swift test --enable-code-coverage` → `llvm-cov`) — Tier 2 only
4. *Stretch:* mutation score via `muter` — Tier 2 only

⚠️ Phase 1 proved compile-based metrics do NOT generalise to the full corpus.
Scope every compile/coverage claim to Tier 2 explicitly, in the paper and the card.

Plus the stratified chart: does generation quality degrade on low-`score` code?
(Only possible on the stack_edu half — IVA has no score. Scope the claim accordingly.)

### Phase 4 — Publish · ~half day

Card documents: provenance chain, ~2023 vintage, XCTest-only dialect, exact filters,
per-row license inheritance, repo-level-license caveat. Publish references + resolver.

### Phase 5 — Paper *(optional, decide only after Phase 3 numbers exist)*

Target: **MSR Data & Tool Showcase** (same track as methods2test). ~4 pages.
Fallbacks: LLM4Code / NLBSE workshops, ICSE-SEIP, arXiv preprint.
NOT ICSE/FSE/ASE main track — a methodology port reads as incremental there.

Strongest angle is NOT the dataset:
> *LLM test generation in low-resource languages: how far do public corpora lag
> language evolution, and does it matter?* — Swift as case study, the 118/243 finding
> as hook, strengthened by two independent crawl routes agreeing.

**Do not let paper ambition influence Phases 1–4.**

### Phase 6 — Dissemination · see §8

---

## 6. TestForge integration notes

From `TestAgent/One/README.md`:

- CLI: `.build/debug/testforge run /path/to/project` — operates on a **project**, not
  a single file. Our pairs are file-level, so the harness synthesizes a minimal SPM
  project per pair. **This aligns exactly with the Phase 1b compile harness — build it
  once, use it for both.**
- TestForge already verifies compile + pass, repairs failures, quarantines the
  unfixable, and reports coverage with a JSON/HTML report. **Its own report supplies
  metrics 2 and 3** for that arm — don't rebuild them.
- It already propagates `DEVELOPER_DIR` to every Apple subprocess. **Our own harness
  must set it too** (`xcode-select` is misconfigured on this machine).
- Default free path: Ollama + `qwen2.5-coder:14b`.
- Other commands: `scan`, `index`, `providers`.

---

## 7. Legal position

**Ownership: resolved.** Personal time, personal hardware, independent of employment.

- Mining public GitHub for research datasets: established practice. Microsoft published
  methods2test (780K pairs) at MSR 2022.
- **Publish references + pair metadata, NOT file contents.** Mirrors what
  HuggingFaceTB does upstream. Sidesteps redistribution obligations, honours upstream
  opt-outs automatically (withdrawn files simply fail to resolve), keeps the artifact
  tiny. The novel contribution is the *pairing*, not the code.
- Permissive ≠ obligation-free: MIT/Apache-2.0/BSD require retaining copyright notice
  and license text. **Keep `repo_name`, `path`, license columns** — the attribution chain.
- **Repo-level licenses are not file-level truth.** IVA's `license` comes from
  BigQuery's repo-level table; a repo declared MIT can contain vendored third-party
  code. Describe it as a signal, not a guarantee, in the card.
- **Cite Stack-Edu / The Stack v2 as provenance**, not the undocumented mirror (§2A).
- IVA's card warns of secrets/usernames in the corpus. Scan any code excerpt before it
  reaches a card, post, or paper. Metadata-only output makes this near-zero by design.
- Not legal advice.

---

## 8. Dissemination

**Lead with the finding, not the dataset.** Nobody clicks "I published a dataset."

> Every public Swift code dataset predates Swift Testing. I checked all of them —
> 118 files out of 2.45 million use it. Every model trained on public Swift writes a
> dialect Apple is moving away from.

Three shareable findings, all already measured: the 118/243 staleness result; 74% of
public Swift is unlicensed; test-writing repos are ~2× more likely to be licensed.

**Deliverables, ranked by what hiring managers actually open:**
1. **GitHub repo with the pipeline** — the code IS the evidence. Clean README, reproducible.
2. **HF dataset** — the credential behind the "first" claim.
3. **Writeup** — blog/LinkedIn article with charts. The forwardable artifact.
4. **Benchmark results** — what makes it engineering, not a scrape.

**Channels:**
- **iOS Dev Weekly** — accepts submissions, large readership, highest leverage
- **Swift Forums** (swift.org)
- r/iOSProgramming, r/swift
- Hacker News — only if the writeup is strong
- **A local iOS meetup talk** — converts to job leads more often than online posts

**Announcement rule: ONE post, after everything is live and links work.**
No "excited to start…" posts. Finding → numbers → links.

**LinkedIn:** HF + GitHub links in **Featured**; headline along the lines of
*iOS Engineer · Developer Tooling & On-Device AI*; reply to every comment for 48 hours.

**Calibration:** this won't flood the inbox with recruiters. It gives a concrete story
for *every interview* that no other iOS candidate has, and separates the CV from a
stack that all say "built iOS apps, used SwiftUI." **Value compounds in interviews,
not impressions.**

---

## 9. Open decisions

| # | Question | Blocks | Note |
|---|---|---|---|
| 1 | ~~How to invoke TestForge~~ | — | **ANSWERED** — §6 |
| 2 | ~~Employer IP~~ | — | **RESOLVED** — personal time/hardware |
| 3 | ~~Use IVA as well?~~ | — | **DECIDED** — dual-source, pending 1c overlap |
| 4 | Target dialect: XCTest or Swift Testing? | Phase 3 | Lean **XCTest** — apples-to-apples with the human baseline; report the dialect gap as a finding |
| 5 | Which Ollama model for generator + raw baseline? | Phase 3 | Default `qwen2.5-coder:14b` |
| 6 | Time budget (evenings/week? month?) | **Phase 1 scoping** | Decides whether Phase 2 gets the SwiftSyntax upgrade |
| 7 | `duckdb` or `pyarrow`? ~3.5 GB disk free? | **PHASE 1 BLOCKER** | Neither installed. Lean **DuckDB** — queries parquet without loading it, more useful skill, needed for the license groupby |

---

## 10. Keywords earned (for CV / interviews)

**Tier 1 (learn properly):** SwiftSyntax · DuckDB · RAG + embeddings/vector search ·
evaluation & benchmark design · MLX / MLX Swift

**Tier 2 (absorbed en route):** Parquet/Arrow · HF `datasets` + Hub · Ollama/GGUF ·
`xccov` + `llvm-cov` · Swift Testing · MinHash/LSH dedup · SPDX license classification

**Avoid claiming:** "fine-tuned an LLM" · "trained an LLM" · "big data" · MLOps/K8s ·
anything phrased as "explored" or "worked with"

**Resume bullet — fill brackets only with measured numbers:**
> Published SwiftTestPairs, the first open dataset of Swift source↔unit-test pairs
> (~[N] permissively-licensed pairs), applying the methods2test (MSR 2022) methodology
> to a language that had no equivalent. Used it to benchmark an on-device agentic test
> generator: [X]% compile rate, [Y] pp coverage delta vs. human-written baselines.

---

## 11. Rules to stay on track

1. **The gates are the plan.** Phase 1 passes or it doesn't. No "let me just also try…"
   before a gate clears.
2. **Measure before writing.** No number reaches a CV, post, or paper until a real run
   produces it. A real 45% survives an interview; an invented 80% does not.
3. **Log every measured number in §2** so context survives any conversation ending.
   Mark estimates as estimates.
4. **Dedup (within AND across sources) and repo-level splits are not optional.**
   Skipping them silently invalidates every downstream result.
5. **One announcement, after everything is live.**


---

## 12. PHASE 2 RESULTS (measured)

**Artifacts:** `data/release/` — `swifttestpairs.parquet` (3.3 MB), `.jsonl` (12.4 MB),
`README.md` (dataset card), `resolve.py`, `stats.json`.

### Final dataset

**20,801 pairs · 7,494 repos · references only, no file contents.**

| tier | pairs | repos | median assertions |
|---|---|---|---|
| 1 | 20,232 | ~7,400 | 11 |
| **2 (VERIFIED build)** | **569** | **157** | 14 |

Splits (repo-level): train 16,654 · valid 1,997 · test 2,150. **Leak check: 0.**
Sources: IVA 12,435 · stack_edu 8,366. Swift Testing: 126 (0.6%). Legacy: 1,499 (7.2%).

### Funnel

| stage | pairs |
|---|---|
| filename join (full corpus) | 22,912 |
| + declaration index | +1,045 (**only +4.4%** — Swift follows one-type-per-file closely; the SwiftSyntax upgrade is NOT worth it) |
| − exact dedup, cross-source | −1,868 (7.8%) |
| − MinHash near-dup (Jaccard 0.8) | −1,288 (5.8%) |
| **FINAL** | **20,801** |

### Tier 2 verification

Every eligible repo built with `swift build --build-tests` using its own manifest.
**157/334 repos = 47.0%**, but only **569/1,798 pairs = 31.5%**.

⚠️ **Projection error to remember:** I earlier projected ~900–1,200 by applying a
REPO-level build rate to PAIR counts. Larger repos hold more pairs and fail more
often, so pair-level survival is far worse than repo-level. Never project across
grain boundaries without checking the correlation.

⚠️ Tier 2 `test` split = 30 pairs, too small to benchmark on. Evaluating a generator
needs no train split — **use all 569**.

### Bugs found and fixed in Phase 2

1. **Filename join omitted `s.src = t.src`** → 1,070 cross-corpus pairs (IVA test +
   stack_edu source). Dropped later by the hash join, so the dataset was never
   corrupted, but the reported "25,028 raw pairs" was inflated. True figure 23,957.
2. **35 duplicate `(src, repo, path)` groups** in `labelled2` inflated joins by 3 rows.
3. **OOM** — carried `source_code`/`test_code` through the join. Keys-only fixed it;
   we publish references anyway.
4. **DuckDB reserved word** `types`.
5. **Write-lock contention** — `phase2_04_verify.py` holds a writer for the whole
   build run, locking out parallel inspection. Use a read-only conn for reads.

### Standing lesson

Four of the six bugs this project produced yielded **plausible wrong numbers, not
crashes** (thread-safety, view-in-a-loop, missing src equality, grain-crossing
projection). Every headline number needs a sanity check against an independent
derivation before it reaches a card or a paper.


---

## 13. PHASE 3 RESULTS (measured 2026-09-14)

### The headline

**TestForge reaches the same coverage as the engineers who wrote the code.**

| | HUMAN | PLAIN PROMPT | TESTFORGE |
|---|---|---|---|
| test files produced | 156 | 132 | **237** |
| compiling together | — | 123 | 216 |
| survival rate | — | 93.2% | 91.1% |
| repos with a green build | 18/25 | 22/25 | 21/25 |
| **MEAN COVERAGE** | **79.4%** | not measured | **79.3%** |
| median coverage | 86.6% | — | **88.4%** |

25 repos · `gemini-3.8-flash` for both generated arms · coverage measured on 17.

### What it does and does not show

- **Coverage parity with humans** is the defensible claim. Unattended, ~Rs45/repo.
- **80% more test files than a plain prompt** (237 vs 132) — it indexes the whole
  project rather than one pasted file.
- **Raw output quality is the SAME.** 91.1% vs 93.2% survival is noise. The
  scaffolding does not make the model write better Swift; it makes the output
  usable at scale and guarantees a green build via quarantine.
- 7 of 25 repos' own human tests fail to run in a reconstructed workspace
  (missing fixtures the Swift-only corpus could not carry). A benchmark
  limitation, not a finding about those projects.

### Full-corpus benchmark (104 repos, before the 25-repo three-arm subset)

| | Raw (104) | Clean (88) |
|---|---|---|
| files on disk | 548 | 424 |
| valid Swift | 523 | **399** |
| junk (prose/truncated) | 25 (4.6%) | 25 (5.9%) |
| keep rate | 54.0% | **64.0%** |
| repos yielding nothing | 31% | **27%** |
| mean coverage delta | +68.2 | **+70.1 pts** |

Excluded: 9 contaminated (human tests leaked), 7 budget-truncated.
**TestForge over-reports kept files by ~17%** — `filesGenerated` counts files
WRITTEN, not files that survived. Always recount from disk.

### Cost

~Rs5,300 total, $12.05 + $0.86 in TestForge's own ledger.
**TestForge under-reports cost ~3.8x**: `usage` carries only `input`/`output`;
Google bills reasoning tokens that never appear there. Confirmed, not inferred.

### Artifacts

- `docs/model_calls.parquet` — 1,528 calls, full prompt + response text
- `docs/MODEL-CALLS.md` — readable appendix, 67 system-prompt variants
- `docs/benchmark_results.json`, `collective_baseline.json`,
  `collective_testforge.json`, `human_coverage.json`, `final_comparison.json`
- `generated/` — every generated test preserved, including quarantined and
  contaminated output. NEVER DELETE.

### TestForge changes (branch `spm-toolchain`, commit fd68657, LOCAL ONLY)

SwiftPM toolchain + `--draft-provider`. Four defects fixed, three of which would
hit real users. 256 tests pass, `gate.sh` passes including engine purity — which
independently confirms ADR-001's claim that a stack plugs in without engine changes.

---

## 14. THE STANDING LESSON — eleven silent wrong numbers

Every one produced plausible output instead of an error. In order:

1. `swift build` writes diagnostics to **stdout**; capturing only stderr gave 375 blank failures
2. DuckDB applies `USING SAMPLE` **before** `WHERE` — wrong sample sizes
3. DuckDB connections are **not thread-safe**; concurrent use returned empty results (82 phantom "missing manifests")
4. A view over 4 GB of parquet/json rescans per query — minutes became hours
5. Filename join omitted `s.src = t.src` → 1,070 cross-corpus pairs
6. A repo-level build rate projected onto **pair** counts (grain mismatch) — Tier 2 over-estimated 2x
7. Killed runs left **truncated files** that broke every later run at zero cost
8. Coverage counted SwiftPM's generated runner → empty packages read as 99.73% covered
9. `ledger` is a **list**, totals are in `summary`; a bare `except` swallowed the AttributeError and silently disabled the budget cap
10. HTTP 429 means rate-limit **or** exhausted credit — retrying the second is useless
11. Both collective runs wrote to one filename; the second silently clobbered the first

**The tell was almost always a suspiciously round number** — `$0.0000`, 0 rows,
100%. Assert against those rather than reading past them. Sanity-check every
headline figure against an independent derivation before it reaches a card,
a post, or a paper.

---

## 15. REMAINING

1. **Publish the dataset** — needs the HF username (fills `<user>` in the card
   and citation). `data/release/` is ready: parquet, card, `resolve.py`.
2. **GitHub repo** for the pipeline — the code is the evidence.
3. **Write-up / LinkedIn** — lead with the finding, not the dataset. Numbers are
   now safe to quote; cost figures are NOT (the 3.8x gap).
4. *Optional:* Qwen arm (free, ~2h) for the on-device story; Swift Testing
   ablation; Kotlin/Gradle toolchain for Android.
5. `build/` is tracked by git in TestForge — belongs in `.gitignore`.

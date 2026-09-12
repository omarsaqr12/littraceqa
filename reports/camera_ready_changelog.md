# Camera-ready changelog

Every change below traces to an artifact. Nothing was altered to make arithmetic
look right. Audit that produced this list: `reports/camera_ready_audit.md`.

## Numbers and tables

| # | change | evidence |
|---|---|---|
| 1 | **Table 3, `v19` cell accuracy `0.0952` removed**, cell left empty | The value was never transcribed from the evaluator; it was assumed equal to `v9`. That assumption is invalid because `table_metrics` gates cell accuracy on row-key matching and `v19` changed row keys on 3 questions. The row was inconsistent at 9.1x its rounding tolerance. The true value is not recoverable, so nothing replaces it. |
| 2 | **`v48` added to Table 3**; the `+ batched cell rewrites` line corrected to `v48`'s values | The line carried `v49`'s numbers (row 0.4675, overall 0.7518) under a label describing `v48`'s change. `v48` is row 0.453401, overall 0.7502 (`results/official_scores.csv`, evaluator JSON). `v49` now has its own line. |
| 3 | **`v6` added to Table 3** | `v6` set a new best (0.4787) and was missing, which made the stated selection rule false. |
| 4 | **"sixteen scored submissions" corrected to 23** in the Figure 2 caption and in §2 | 23 submissions were scored. Table 3 now states its selection rule (17 record-setters plus the one regression) and says five are omitted. |
| 5 | **Figure 2 redrawn with all 23 submissions**, labelled by run | The old figure showed a curated 16 while its caption claimed completeness. |
| 6 | **Table 2 row 1: `43/55` -> `45/55`**, wording changed to "Distinct evidence keys $=$ gold paper count" | `results/count_conventions.py`: the cardinality reading gives 45/55 and matches the paper's own histogram (24+19+1+1); the strict bijective reading gives 37/55. `43/55` matches neither and appears to have been transcribed from `reports/paper_selection.md:73`, where it is an unrelated paper-selection accuracy. Both readings are now reported. |
| 7 | **Table 2 row 7 relabelled** "same-page `table`" | The count 1/64 is correct but 64 is the number of gold *table* items. Over all object types it is 5/95. |
| 8 | **Table 2 row 8: `10/38` -> `17/84`**, definition stated | The original triple (10/22/6) came from a script that was not preserved and no extraction rule reproduces it. Replaced with a figure the shipped script regenerates. The conclusion is unchanged: gold is the earliest occurrence in a minority of cases under every rule tested. |
| 9 | **Figure 1: `0.7322` no longer labelled "evidence types" alone** | `equation_algorithm` evidence gave 0.7287 (`v43`); 0.7322 (`v44`) also carries the figure-counting MC fixes. Now reads "evidence types, MC". |
| 10 | **Figure 1: retrieval annotation marked `dev`** | `0.410 -> 0.490` is a development-set reranker ablation (`reports/scoring_and_fixes.md:97-98`); every other annotation is an official test score. The caption now says so. |
| 11 | **Table 2 caption: "produced our two largest jumps" removed** | Not supported by Table 3. The two largest jumps are `v9` (+0.0956) and `v41` (+0.0729), neither attributable to rows 2-3. Replaced with "the conventions we acted on directly in test submissions". The same claim was removed from Contribution 2. |
| 12 | **Table 3 column relabelled `cell acc. (macro)`** | The evaluator reports macro *and* micro and they differ (`v57`: 0.297619 vs 0.356322). The caption now gives both. |
| 13 | **"Our largest single regression" replaced with the figures** ($0.7647 \to 0.7619$) | `v55` is not our largest regression; `v14` fell 0.0451. It is the only regression on the best-score path. |
| 14 | **Caption count "other six" -> "other five"** | 23 minus the 18 listed. Caught by `check_manuscript.py` after the table was rewritten. |

## Compliance

| # | change | requirement |
|---|---|---|
| 15 | Added the three required citations, using the organisers' entries verbatim | camera-ready.html: cite LitTraceQA, GoldenViewVQA and the findings paper. Only change: protective braces around `GroundLM`, `LitTraceQA`, `MLLMs` so `acl_natbib.bst` does not lowercase them. No field altered. |
| 16 | Bibliography converted from hand-written `\bibitem`s to `paper/littraceqa_system.bib` + BibTeX | camera-ready.html: "include the benchmark references in your own .bib file". The old list had **no `\cite` commands at all**. |
| 17 | Added `paper/saqr-2026-oded.bib` | Required `.bib` upload and the new required OpenReview field `paper_bibtex`; key format `<first-author-lastname>-2026-<method-acronym>`. |
| 18 | Second author's surname corrected **Gafaar -> Gaafar** everywhere | OpenReview profile `~Mostafa_Gaafar1` on the accepted submission. Author order unchanged. |
| 19 | `paper/README.md`: "Moustafa" -> "Mostafa"; stale note about a non-`aucegypt.edu` contact address removed | Both addresses are on `aucegypt.edu`. |
| 20 | `progress.pdf` regenerated with `pdf.fonttype = 42` | The PDF embedded `BMQQDV+DejaVuSans` as **Type 3** with no ToUnicode map. Now CID TrueType, text searchable. No Type 3 font remains. |
| 21 | Figure 2 recoloured to the Okabe-Ito palette, each series given its own marker and dash pattern | Colour-blind and grayscale legibility. |
| 22 | Setup section rewritten with exact model identifiers | camera-ready.html: disclose external data, models, tools, APIs. See below. |
| 23 | Reproducibility claim rewritten to match what the repository actually contains | The old text claimed "the five automated verifiers"; the crowded-page check was ad hoc and is now stated as such. |

### Model identifiers recovered

| disclosed | recovered from |
|---|---|
| `gemini-flash-lite-latest`, `gemini-3.5-flash`, `gemini-flash-latest` (rotation order), `gemini-3.7-flash` in one experiment | `littraceqa/reason/client.py:92-95`, `exp/19_gemini37_subset.py:30` |
| `gemini-flash-latest` resolves to `gemini-3.6-flash`, 20 requests/day free tier | `littraceqa/reason/client.py:85-87` |
| `Qwen3.6-27B-UD-Q4_K_XL` GGUF, with the exact `llama-server` flags | `reports/local_reader.md:114`, `exp/17_local_selector.py:27` |
| `Qwen/Qwen3-8B` transformers default | `littraceqa/reason/local_llm.py:48` |
| `BAAI/bge-large-en-v1.5`, `BAAI/bge-reranker-base` | `littraceqa/retrieval/dense.py:26`, `rerank.py:33` |
| greedy decoding for hosted; temperature 0.7 / top_p 0.9 / 3 samples locally | `client.py:113`, `local_llm.py:186,293` |

**Not recovered, and now stated as not recovered:** which weights the floating
Gemini aliases resolved to during our runs; the `llama.cpp` build; the dated
Claude version. These are disclosed as unknown rather than guessed.

## Prose

See `reports/camera_ready_style_changelog.md`.

## New scripts (all in `results/`)

* `count_conventions.py` — regenerates all eight Table 2 counts from the 55 dev examples.
* `validate_table3.py` — recomputes `overall` for all 23 submissions against a derived tolerance.
* `check_manuscript.py` — 153 checks of the manuscript against those artifacts.
* `official_scores.csv` — every scored submission with its provenance.

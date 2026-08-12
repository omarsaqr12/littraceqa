# Retrieval results on validation (55 questions)

All numbers are `paper_f1_macro` from the official `evaluate.prf`, produced by the
scripts named in each section. Everything here is local and free — no API calls.

## Headline

| policy | paper F1 | single-paper | multi-paper |
|---|---|---|---|
| fused list, n=1 | **0.400** | **0.692** | 0.138 |
| `predict_set_size` (surface cues) | 0.403 | 0.692 | 0.143 |
| fused list, n=4 | 0.298 | 0.338 | 0.262 |
| adaptive expansion, sim ≥ 0.86 | 0.285 | 0.471 | 0.119 |
| mention-anchored, cap 6 | 0.381 | 0.628 | 0.159 |
| mention-anchored, cap 2 | 0.356 | 0.603 | 0.135 |
| **oracle: best fixed n per question** | 0.555 | — | — |
| **oracle: all retrieved gold, no false positives** | **0.756** | — | — |

Candidate recall (`exp/03`): recall@40 = 68.5% overall — 96.2% on
`hidden_source_single_paper`, 43.7% on `multi_paper`.

## What this says

**Selection, not set size, is the binding constraint.** Every policy lands near
0.40 while the oracle that keeps exactly the gold papers already present in the
top-40 reaches 0.756. The gold papers are in the candidate list; we are not
picking them out. A better ranker is worth up to ~0.35 F1; better set-size
prediction is worth at most ~0.15.

**Single-paper retrieval is effectively solved and multi-paper is not.**
0.692 vs 0.138. Everything below is about the second number.

## Negative result: dense expansion cannot recover the gold clusters

plan.md §2.2 established that `multi_paper` gold sets are topical clusters — 6 of
29 questions have all their evidence in one paper while gold lists four, and one
4-paper cluster is shared by 12 questions. That framed expansion as worth ~0.6 F1
on those questions, *if* the cluster could be recovered.

`exp/06_expansion_diagnostic.py` seeds kNN with a **gold** paper and asks how much
of the rest of the cluster comes back:

| k | sibling recall |
|---|---|
| 3 | 20.0% |
| 5 | 28.0% |
| 10 | 29.2% |
| 20 | 41.5% |
| 50 | 54.3% |
| 200 | 69.7% |

Siblings reachable anywhere in the top 200: 71.4%, median rank 13.

So the failure is not seed quality — it is that **the clusters are not
embedding neighbourhoods**. q_020 makes the reason concrete: its gold set is
"NAACL 2025 papers that mention MCTS in their primary method figure", whose
members are a preference-learning study, an ensembling method, an in-context
learning planner, and a RAG system. Nothing at the abstract level unites them.
kNN from one of them returns eight other preference-learning papers, none gold.

The property that defines these clusters lives in the **full text** (a figure
caption, a baseline row in a results table), which title+abstract retrieval
cannot see at any k. Embedding-based expansion is closed as an avenue; it is
disabled by default in `PipelineConfig`.

The remaining route for content-defined sets is a venue-scoped full-text index:
"which NAACL 2025 papers…" restricts to 1,193 papers, which is a tractable
download-and-index job on this hardware. That is the only mechanism measured or
proposed that can answer these questions, and it is the main open lever.

## Caveat that matters more than any number above

**Validation and test may not share gold-set structure.** Validation's
`multi_paper` gold sets are 4-paper annotator-built clusters. Test questions read
as "the **two** ICCV 2025 papers", "these two ICCV 2025 papers" — 24 of 71 state
a count, overwhelmingly two. If test gold is the two *named* papers rather than a
cluster, then mention-anchored selection (which returns one paper per named
artefact, predicting sizes `{1:8, 2:23, 3:16, 4:8, 5:8, 6:8}` on test) transfers
better than the n=1 policy that wins on validation, despite scoring 0.02 lower
here.

55 questions is a small sample and the two splits were plainly constructed
differently. Do not over-fit the selection policy to validation; the first test
submission is also the first real measurement of which regime applies.

## Reproduce

```bash
.venv/bin/python exp/03_hybrid_recall.py         # candidate recall
.venv/bin/python exp/04_set_size_sweep.py        # set-size policies + oracles
.venv/bin/python exp/06_expansion_diagnostic.py  # gold-seeded expansion
.venv/bin/python exp/07_mention_anchored.py      # one paper per named artefact
.venv/bin/python exp/run_ablation.py --stage retrieval
```

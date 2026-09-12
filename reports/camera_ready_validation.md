# Validation report

Run on the final PDF, `paper/littraceqa_system.pdf`.

## PDF

| check | tool | result |
|---|---|---|
| ACL PubCheck | `aclpubcheck --paper_type long` | **All Clear!** |
| Page size | `pdfinfo` | 595.276 x 841.89 pts = **A4** |
| Pages | `pdfinfo` | 9 (main content ends within 8; Limitations, Ethics, Conclusion, Acknowledgements and References follow, which ACL excludes from the limit — PubCheck confirms) |
| Type 3 fonts | `pdffonts` | **none** (18 Type 1 + 1 CID TrueType) |
| Font embedding | `pdffonts` | all embedded |
| Structure | `pikepdf` | opens, not encrypted, all 9 content streams resolve (`qpdf` is not installed on this machine; `pikepdf` wraps the same library) |
| Compile | `pdflatex` x2 + `bibtex` | 0 errors, 0 overfull boxes, 0 unresolved references or citations |
| Visual | `pdftoppm -r 150` on every page | inspected; figures, tables, captions, citations and the reference list all render |

Note on the earlier Type 3 font: `progress.pdf` previously embedded
`BMQQDV+DejaVuSans` as Type 3 with `uni no`, meaning that text was neither
searchable nor extractable. `paper/make_fig.py` now sets
`matplotlib.rcParams["pdf.fonttype"] = 42`.

## Consistency

`results/check_manuscript.py` — **153 checks, 0 failed**. It verifies every
Table 3 cell against `results/official_scores.csv`, recomputes `overall` for
every row with complete components, checks Table 3's stated selection rule and
its three stated counts, checks all eight Table 2 counts against
`results/convention_counts.json`, and checks that Figure 2 is still generated
from the CSV with Type 42 fonts.

`results/validate_table3.py` — **23 scored submissions, 22 fully checkable, 0
inconsistent.** `v19` is reported as not checkable because one component was
never retained. Before this audit the same script reported one inconsistency, at
9.1x its rounding tolerance.

`results/count_conventions.py` — regenerates all eight Table 2 counts. Six
reproduce the previously reported values exactly (8/8, 10/10, 3/3, 4/7, 52/68,
1/64), as do 149 evidence items, 65 on pages 6--7, 5 on page 1, and 9/11 over all
table questions.

## Claims that could not be independently verified

1. **`v19`'s official cell accuracy.** Never transcribed from the evaluator; the
   Space exposes no per-submission history. Its *overall* is sourced (commit
   `83a78b7`), its paper F1, evidence F1 and MC are **proven** identical to `v9`
   by a field-by-field diff of the two prediction files, and its row F1 is
   recorded independently at `reports/table_stage.md:560`. Only the cell
   accuracy is unavailable, and the paper now leaves it empty. A value of
   ~0.1032 would reproduce the reported overall, but that is an inference from
   the overall rather than an evaluator output, so it is not printed.
2. **The original `10/22/6` page-position triple.** The generating script was not
   preserved and no extraction rule tested reproduces it: item value plus
   evidence value gives (17, 61, 6) over 84; the item's own numeric value gives
   (15, 32, 5) over 52; verbatim matching gives (6, 11, 5) over 22. The paper now
   reports the first, with the definition stated and the script shipped. The
   qualitative conclusion holds under all three.
3. **Which weights the Gemini aliases resolved to.** `gemini-flash-lite-latest`
   and `gemini-flash-latest` are floating aliases by construction. Our runs fall
   between 16 and 19 August 2026; no response metadata pinning a dated version
   was retained. Disclosed as unknown.
4. **The `llama.cpp` build** used for the local selector experiments. Flags were
   recorded, the build was not.
5. **The dated Anthropic Claude version** used by the audit agent. Not recorded.
6. **Four evidence items' page checks** in `count_conventions.py` are skipped
   because three PDFs (`iclr2025_02715`, `neurips2025_02748`,
   `neurips2025_04876`) were never successfully fetched. The 52/68 and 1/64
   counts are computed over what is available, which is what the original
   measurements also used.
7. **Anything about the current state of the online evaluator.** All scores were
   produced against the Space as it stood in August 2026. No old score has been
   reinterpreted under a later version, and we did not re-submit to check.

## Decision letter

OpenReview submission #9 (`BMH2uTgrew`), venue
`EMNLP/2026/Workshop/GroundLM_Shared_Tasks`. The only reply on the forum is the
decision note from the Program Chairs: `decision: Accept`, `title: Paper
Decision`. There are no reviews and no comments, so there is no reviewer feedback
to address. This satisfies the camera-ready checklist item "Address the decision
letter".

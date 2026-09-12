# Camera-ready forensic audit — LitTraceQA system paper (OdeD)

Audit run 12 September 2026. This report records the state **before** any edit;
every finding was reproduced from artifacts first. Resolutions are appended at
the end, and the edits themselves are listed in
`reports/camera_ready_changelog.md`.
Every number below was recovered from an artifact; none was inferred from what
looked plausible. Source-of-truth order used: evaluator output → submitted JSONL
→ evaluator code → dev gold + audit scripts → generated reports → manuscript.

Scripts written for this audit, both committed to the reproducibility package:

* `results/validate_table3.py` — recomputes `overall` from official components
  for every scored submission, with a derived (not guessed) rounding tolerance.
  Outputs `results/table3_validation.{csv,json}`.
* `results/count_conventions.py` — recomputes all eight Table 2 support counts
  from the 55 dev examples and the cached PDFs, importing the evaluator's own key
  functions. Outputs `results/convention_counts.json`.

---

## 0. Deadline and status

The camera-ready is **due 2026-09-13 12:00 UTC** (OpenReview invitation
`…/Submission9/-/Camera_Ready_Submission`, `duedate` 1789300800000; hard
`expdate` 2026-09-13 23:59 UTC). This is "September 12, AoE" as advertised. The
audit was run with roughly 23 hours remaining.

---

## 1. Confirmed errors

### A1. Table 3, row 3 (`+ hand-authored table row keys`) — cell accuracy is wrong

`validate_table3.py` over all 23 submissions known at audit time: **22 consistent, 1 not.**

| | shown | recomputed from shown components | diff | tolerance |
|---|---|---|---|---|
| v19 | 0.5602 | 0.559344 | **−0.000856** | 9.44e-5 |

That is **9.1× the rounding tolerance**, so display rounding cannot explain it.

Root cause, established rather than assumed. `results/official_scores.csv`
records v19's provenance as: *overall from commit `83a78b7` + `paper_selection.md`
prose; components **assumed** equal to v9 except row F1, never transcribed from
evaluator output.* A field-by-field diff of `preds/test_v9.jsonl` against
`preds/test_v19.jsonl` shows:

```
identical gold_papers : 71/71
identical evidence    : 71/71
identical MC answer   : 71/71
table rows differ in  : 3 questions
  ltqa_62588bf6eaca46d0, ltqa_7d7e93465a7c030d, ltqa_a805cd7e63c6a6a3
```

So paper F1, evidence F1 and MC **provably cannot** differ between v9 and v19 —
those four displayed values are safe. But `table_metrics` builds `gold_by_key`
and `pred_by_key` from the row-key tuples and then iterates over **gold** rows
only, looking up `pred_by_key.get(key)`. Cell accuracy is therefore gated on
row-key matching, and v19 changed row keys on three questions. Carrying v9's
cell accuracy (0.0952) across was invalid.

**The wrong cell is `cell acc = 0.0952` in row 3.** The overall (0.5602) is
sourced and stands; the row-F1 change is real.

The original evaluator output for v19 was never saved and the Space does not
expose submission history, so the true cell accuracy is **not recoverable**.
Algebraically, cell ≈ 0.1032 reproduces 0.5602, which corresponds to a cell sum
of 2.1667/21 = one additional 1/6 step over v9. That is an *inference from the
reported overall*, not a transcription, and must not be printed as if it were an
evaluator value. Recommended repair is in §5.

### A2. Table 3, row `+ batched cell rewrites` carries v49's numbers under v48's label

Official values (`results/official_scores.csv`, full precision, evaluator JSON):

| run | row F1 | cell acc | overall |
|---|---|---|---|
| v48 | 0.453401 | 0.250000 | 0.7502 |
| v49 | 0.467460 | 0.250000 | 0.7518 |

Table 3 prints `0.4675 / 0.2500 / 0.7518` — **v49** — on the line whose label
describes v48's change (the batched cell rewrites). **v48 is absent from the
table entirely**, and v48 is the submission that actually moved cell accuracy
0.2262 → 0.2500. The row F1 shown (0.4675) is unchanged from the line above
(v46, 0.467460), which makes the printed line look like it moved no rows.

### A3. "sixteen scored submissions" is false

There are **23** scored submissions (v2, v5, v6, v9, v10, v11, v14, v16, v19,
v26, v32, v41, v43, v44, v45, v46, v48, v49, v51, v52, v53, v55, v57). Table 3
and Figure 2 show a curated 16. Both captions assert completeness:

* line 146: "Official evaluator score for each of our **sixteen scored
  submissions**"
* line 174: "sixteen of our submissions"

The runs omitted from the figure (v5, v6, v10, v11, v14, v16, v48) include
**four that scored below the line above them** — the paper currently shows only
one regression while claiming to show every submission.

### A4. Table 2, row 1: `43/55` matches neither definition

`count_conventions.py`, on the 55 dev examples:

| reading | count |
|---|---|
| bijective — every gold paper carries exactly one key, none orphaned | **37/55** |
| cardinality — number of distinct evidence keys equals number of gold papers | **45/55** |

`43/55` is neither. The paper's own prose supports 45: the (papers, keys)
histogram is `(1,1)×24, (4,4)×19, (3,3)×1, (9,9)×1` = 45, and the script
reproduces that histogram exactly. The two readings differ on exactly 8
questions, all of the same shape: 4 gold papers, 4 keys, one paper carrying two
keys and one gold paper cited by none.

Likely origin: `reports/paper_selection.md:73` reports `selection then picked a
gold paper: 43/55` — an unrelated **paper-selection accuracy**. The value appears
to have been transcribed into the conventions table.

Note the table row's wording ("Exactly one evidence key per gold paper") states
the *bijective* reading (37) while the prose states the *cardinality* reading
(45). Wording and number must be made to agree.

### A5. Figure 1 pairs 0.7322 with "evidence types"

Figure 1 annotates `→ 0.7322 / evidence types`. Table 3 and the official scores
say:

* `+ equation_algorithm evidence` (v43) → **0.7287** ← this is the evidence-type change
* `+ figure-counting answers` (v44) → **0.7322** ← MC 0.96→0.98, row F1 0.3405→0.3516

So 0.7322 is not the evidence-type result. Either the score or the label is
wrong; if the annotation is meant to span both submissions, it must say so.

### A6. Figure 1 mixes development and test numbers without labelling

`paper F1 0.410 → 0.490` under the retrieval stage is a **development** figure —
the cross-encoder rerank ablation in `reports/scoring_and_fixes.md:97-98` (no
rerank 0.410, + rerank 0.490). Every other annotation in the figure (0.4563,
0.5519, 0.7095, 0.7322, 0.7649) is an **official test** score. Nothing in the
figure distinguishes them.

### A7. Table 2 caption: "Rows 2–3 … produced our two largest jumps"

Rows 2–3 are *gold table rows = gold paper count* (8/8) and *question names a
figure ⇒ gold has `figure`* (10/10). The two largest jumps in Table 3 are
0.4563→0.5519 (+0.0956, LLM selector and visual table reading) and
0.6366→0.7095 (+0.0729, seven paper-set corrections). Neither is attributable to
rows 2–3. The claim is not supported by the results table and names no comparison
set.

### A8. Author surname disagrees with OpenReview

The PDF and `.tex` read **"Mostafa Gafaar"**. The accepted OpenReview record for
submission #9 lists author **"Mostafa Gaafar"**, profile `~Mostafa_Gaafar1`.
The OpenReview profile is self-registered by the author, so `Gaafar` is
authoritative and the PDF carries a transposition. (First author: OpenReview has
the full legal "Omar Mokhtar Gaber Saqr"; the paper's "Omar Saqr" is a
short form, which is normal and needs no change. Author order is unchanged.)

### A9. Embedded Type 3 font

`pdffonts paper/littraceqa_system.pdf`:

```
BMQQDV+DejaVuSans   Type 3   Custom   emb yes  sub yes  uni no
```

Every other font is Type 1. The Type 3 face comes from `progress.pdf`
(matplotlib's default `pdf.fonttype: 3`). ACL PubCheck flags Type 3 fonts, and
`uni no` means that text is not searchable or copyable.

### A10. Table 3's cell-accuracy column is unlabelled as to macro/micro

The evaluator reports **both** `table_cell_accuracy_macro` and
`table_cell_accuracy_micro`, and they differ materially. For v57
(`submission/README.txt`, archived evaluator output):

```
table_cell_accuracy_macro  0.297619    <- this is what Table 3 prints
table_cell_accuracy_micro  0.356322    = 31/87 exactly
```

The column header is just "cell acc". The paper elsewhere discusses micro counts
(23/87, 31/87) without flagging that these are a different metric from the one in
the table.

---

## 2. Camera-ready requirements not yet satisfied

Checked against the live pages, fetched today.

| requirement | source | status |
|---|---|---|
| Cite LitTraceQA **and** GoldenViewVQA (both, even when entering one task) | camera-ready.html | **missing** |
| Cite the shared-task findings paper | camera-ready.html | **missing** |
| Use the organizers' exact BibTeX entries for the three above | camera-ready.html | **missing** |
| Upload a separate `.bib` with our own entry, key `<first-author-lastname>-2026-<method-acronym>`, GroundLM booktitle | camera-ready.html + OpenReview `paper_bibtex` field (required, new since submission) | **missing** |
| Run ACL PubCheck on the final PDF | camera-ready.html | pending (A9 to fix first) |
| Address the decision letter | camera-ready.html | **satisfied — nothing to address** (decision note is `decision: Accept`, `title: Paper Decision`, no reviews, no comments) |
| De-anonymize: authors, affiliations, acknowledgements | camera-ready.html | satisfied |
| ACL style, unmodified margins/fonts/page size | both | satisfied (A4 595×842 pt, `acl.sty` `[final]`) |
| 4–8 pages main content + references | shared-tasks.html | satisfied (8 pages: 7 main + references) |
| Report official evaluator results under the same team name | camera-ready.html | satisfied (OdeD in title, results, OpenReview `team_name`) |
| Disclose external data, models, tools, APIs | both | partially — see §4 |

### Title conflict — resolved, no change

The two live pages disagree:

* `shared-tasks.html`: "The paper title **should** use the team name from the
  shared-task submission, for example: `<Team Name> at GroundLM 2026 Shared
  Tasks: <Paper Title>`", and "Use exactly the same team name on the evaluator,
  in the system paper **title**/results, and in the OpenReview teamname field."
* `camera-ready.html`: "do not include the team name in the title… The title
  does not need to include a team name. A useful pattern is `<Method Name>:
  <Contribution> for <Task Name>`."

Resolution order applied: (1) decision letter — silent; (2) OpenReview
camera-ready form — `title` is free text with no constraint; (3) camera-ready
instructions — permissive ("does not need to"), stated under "**Suggested** Paper
Titles"; (4) shared-task instructions — "should", plus a hard same-team-name
rule that names the title. Ambiguous, so per the standing rule the **accepted
title is preserved**: *OdeD at GroundLM 2026 Shared Tasks: Reading the Scorer for
Literature-Grounded QA*. It also satisfies the only mandatory rule of the four.

---

## 3. Verified correct

Reproduced from artifacts; no change needed.

**Metric description vs `scripts/evaluate.py`.** All of the paper's Section 2
claims check out against the implementation:

* `answer = (mc + row_f1 + cell_accuracy)/3`, `overall = (paper_f1 + evidence_f1
  + answer)/3`; weights 1/3, 1/3, 1/9, 1/9, 1/9. *(Caveat: `evaluate()` itself
  returns 11 metrics and no `overall` — the combination is the Space's. The
  formula is confirmed by the archived v57 output, where it reproduces 0.7649.)*
* `coarse_evidence_key` = `(paper_id, source_type, page-or-section, object_id)`,
  `object_id` empty for `text_span`, `normalize_visible_id` for table/figure/
  equation/citation ids.
* `F1 = 2C/(G+N)` via `prf`.
* Row F1 is set F1 over row-key tuples; duplicate keys collapse, last wins
  (dict comprehension).
* `cell_accuracy` iterates **gold** rows only → bounded by row *recall*,
  indifferent to row *precision*; `cell_total` is a property of gold alone.
  **Verified independent of row precision.**
* One undocumented edge case: `cell_accuracy = cell_correct/cell_total if
  cell_total else row_f1` — with no non-key columns, cell accuracy silently
  becomes row F1. Does not affect our runs (cell_total = 87) but the paper
  should not claim the two are always independent.

**Numbers reproduced exactly** (`count_conventions.py` unless noted):

| claim | status |
|---|---|
| 149 gold evidence items | ✓ |
| 65/149 items on pages 6–7; 5/149 on page 1 | ✓ |
| gold table rows = gold papers, 8/8 multi-paper | ✓ (9/11 over all table questions, matching `table_stage.md`) |
| question names a figure ⇒ `figure`, 10/10 | ✓ |
| question names a table ⇒ `table`, 3/3 | ✓ |
| equation/loss ⇒ `equation_algorithm`, 4/7 | ✓ |
| table caption on cited page ⇒ `table`, 52/68 | ✓ |
| gold pairs `text_span` with same-page object, 1/64 | ✓ **but see §4** |
| (1,1)×24, (4,4)×19, (3,3), (9,9) | ✓ |
| shortlist recall 0.846@1, 0.962@20, flat to 200 | ✓ `free_selectors_and_evidence.md:238` |
| 27,487 papers | ✓ |
| 55 dev / 71 test | ✓ |
| 112 test papers, 0 unreadable | ✓ `e4_e6_measurements.md:118` |
| 48 of 49 object ids confirmed | ✓ `scoring_and_fixes.md:176` |
| 0 for 13 on invented strings | ✓ decomposition sums: 3+4+2+2+2 = 13 |
| −0.2952 three-candidate row miss | ✓ `scoring_and_fixes.md:260` |
| −0.25 long→short | ✓ `scoring_and_fixes.md:356` |
| 0.129 ungated loss | ✓ `table_stage.md:201` |
| break-even ~26% (not ~60%) once the cell term is counted | ✓ `table_stage.md:576` |
| every submission arithmetically consistent except v19 | ✓ this audit; after the log arrived, 29 of 29 |
| paper F1 rose 0.338 (0.6324→0.970423), evidence F1 0.373 (0.3587→0.731858) | ✓ (0.33802, 0.37316) |
| test cell micro 31/87 for v57 | ✓ archived evaluator output |
| A4, 8 pages | ✓ `pdfinfo` |

---

## 4. Suspected, needing a decision (not yet errors)

* **Table 2 row 7 denominator.** `1/64` is correct, but 64 is the count of gold
  **table** evidence items. The row reads "Gold pairs a `text_span` with a
  same-page **object**", and over all objects the count is **5/95**. The number
  is right and the label is too broad; one of the two must change.
* **Table 2 row 8, `10/38`, is not reproducible.** The source report
  (`e4_e6_measurements.md:145-152`) defines it as gold items whose *answer value*
  appears on more than one page (earliest 10, middle 22, latest 6). The script
  that produced it was not preserved, and no value-extraction rule I tested
  reproduces the triple: `(17, 61, 6)` over 84 items using answer + evidence
  values, `(15, 32, 5)` over 52 using the item's own numeric value, `(6, 11, 5)`
  over 22 matching the value verbatim. The qualitative claim is robust — gold is
  the earliest occurrence in only 20–29% of cases under **every** rule tested —
  but the exact triple cannot be re-derived. Decision required: keep the reported
  triple and cite the report, or replace it with a freshly scripted figure under
  a stated definition. Recommend the latter, since the script then ships.
* **`freeform_exact_match` is `null`** on the test split — there are no freeform
  questions. The paper does not say so, which leaves a reader unsure why only
  three answer metrics appear.

---

## 5. Recommended repairs

1. **v19 row.** Replace the fabricated `0.0952` with a non-numeric marker (e.g.
   `---`) and state in the caption that v19's per-component output was not
   retained, only its overall. This is the only option that neither prints an
   unverified evaluator value nor silently drops a real submission. Alternatively
   drop the row and fold its content into the v26 line. **Do not print 0.1032.**
2. **Add v48** as its own line with its official values, and correct the
   `+ batched cell rewrites` line to v48's numbers, moving 0.4675/0.7518 to a
   v49 line.
3. **Replace "sixteen" with the true count** and state plainly that the table and
   figure show a selected subset of 23, with the selection rule given.
4. **Table 2 row 1**: use `45/55` with the cardinality wording, and report `37/55`
   for the strict reading in the prose.
5. **Figure 1**: correct the 0.7322/"evidence types" pairing, and label the
   0.410→0.490 annotation `dev`.
6. **Table 2 caption**: drop "two largest jumps" or replace with the specific,
   checkable attribution.
7. **Table 3 header**: `cell acc. (macro)`; note micro separately.
8. **Regenerate `progress.pdf`** with `pdf.fonttype = 42`, then re-check
   `pdffonts`.
9. **Fix the surname** to `Gaafar` in the `.tex` and every submission sheet.
10. **Add the three required citations** verbatim from `camera-ready.html`, and
    write `paper/oded-2026-littraceqa.bib` for the `paper_bibtex` field.

---

## 6. Cannot be verified from available artifacts

* **v19's official per-component output.** Never saved; the evaluator Space keeps
  no per-submission history we can read. Only its overall (0.5602) is sourced.
* **The exact `10/22/6` extraction rule** (§4).
* **Whether `gemini-flash-lite-latest` was a mutable alias, and what it resolved
  to during our runs.** The name is an alias by construction; no response
  metadata pinning a dated version was retained. Pending a log sweep in the next
  phase.
* **Any claim about the current online evaluator's behaviour.** Scores were
  produced between August and 19 August 2026 against the Space as it stood then.
  Old scores have not been reinterpreted under any later version.


---

## 7. Resolution status (appended after editing)

| finding | status |
|---|---|
| A1 `v19` cell accuracy | **Resolved with the real value.** The evaluator submission log later became available and gives `table_cell_accuracy_macro: 0.103175`. Table 3 prints 0.1032. `validate_table3.py` now reports **29 submissions, 29 fully checkable, 0 inconsistent**. |
| A2 `v48`/`v49` mislabel | **Fixed.** Both rows present with their own official values. |
| A3 "sixteen scored submissions" | **Fixed, then corrected again.** 23 was also wrong: the evaluator log documents at least 29. The paper now states a lower bound and claims no total (see section 8). |
| A4 Table 2 `43/55` | **Fixed.** 45/55 with the cardinality wording; 37/55 reported for the strict reading. |
| A5 Figure 1 `0.7322` label | **Fixed.** Reads "evidence types, MC". |
| A6 Figure 1 dev/test mixing | **Fixed.** Annotation marked *dev*; caption states the distinction. |
| A7 "two largest jumps" | **Fixed.** Removed from the Table 2 caption and from Contribution 2. |
| A8 surname | **Fixed.** `Gaafar` everywhere, matching `~Mostafa_Gaafar1`. Author order unchanged. |
| A9 Type 3 font | **Fixed.** `pdf.fonttype = 42`; no Type 3 font remains. |
| A10 macro/micro label | **Fixed.** Column reads `cell acc. (macro)`; caption gives the micro value. |
| Three required citations | **Fixed.** Organisers' entries, in a `.bib`, cited in the introduction. |
| Own-paper `.bib` | **Fixed.** `paper/saqr-2026-oded.bib`. |
| Decision letter | **Nothing to address** — `decision: Accept`, no reviews, no comments. |
| PubCheck | **All Clear** on the final PDF. |
| Table 2 row 7 denominator | **Fixed.** Relabelled "same-page `table`". |
| Table 2 row 8 `10/38` | **Replaced** with a scripted, reproducible `17/84` and its definition. Listed as unverifiable in the validation report. |
| `freeform_exact_match` null | **Not addressed.** The test split has no freeform questions, so the evaluator returns null; the paper reports the three answer metrics that exist. Left as is rather than adding a sentence about a metric that never applies. |

Two findings from the edit pass itself, both caught by `check_manuscript.py`
rather than by reading: a stale "other six" after the table was rewritten, and a
caption check broken by line re-wrapping. The checker is now whitespace-tolerant.

---

## 8. The evaluator submission log (received after the audit)

The evaluator's own submission log was recovered after this audit was written and
supersedes every lower-tier source. It is stored at `results/evaluator_log.csv`,
and `results/official_scores.csv` is now derived from it.

### What it settles

* **`v19`'s cell accuracy is `0.103175`.** The audit inferred ~0.1032
  algebraically from the reported overall and declined to print it, on the
  grounds that an inference is not a transcription. The log confirms that
  inference exactly. The paper now prints 0.1032 with the evaluator as its
  source; the empty cell and its caption disclosure are gone.
* **The metric formula is confirmed against 28 official outputs**, not one.
  Every row in the log reproduces its own reported `overall` from its components
  under `overall = (paper_f1 + evidence_f1 + (mc + row_f1 + cell_acc)/3)/3` to
  within 1e-6. This is far stronger evidence for the claims in section 2 than the
  single archived `v57` output the audit originally relied on. It doubles as a
  check on the transcription: a typo in any component would break its own row.
* **Every submission now carries full precision**, so the rounding tolerance for
  each row drops to 5e-5 and `validate_table3.py` reports 29 of 29 checkable,
  **0 inconsistent**.

### What it unsettles

* **The submission count.** The export is partial. It lists 28 distinct
  submissions and omits `v55`, for which we hold an evaluator output, so at least
  29 exist. The paper's "23" was wrong, and so was this audit's.
* **The "17 that set a new best" selection rule** can no longer be asserted: a
  submission missing from the export could have set a record between two visible
  ones. Table 3's caption now describes its rows as the submissions marking each
  distinct stage, plus the regression, and claims no completeness.
* **Seven log entries have no counterpart in our own records**: four re-uploads
  scoring 0.446198, one at 0.478734, one at 0.551929, and one genuine run at
  `2026-08-18T04:17:17` (`12a3f0dbf380`, overall 0.541256, paper F1 0.777934,
  MC 0.76) for which no local prediction file survives. The re-uploads are
  identical by score; the last is a submission we had not recorded at all.

### Still open

Whether the export is complete enough to state an exact total. If the full log
becomes available, the lower bound can become a count and the record-setter rule
can be restored. Nothing else in the paper depends on it.

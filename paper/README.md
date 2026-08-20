# OdeD --- GroundLM 2026 Shared Task 2 (LitTraceQA) system paper

`littraceqa_system.tex` -> `littraceqa_system.pdf`

    pdflatex littraceqa_system.tex && pdflatex littraceqa_system.tex

Built and verified: **7 pages = 6 of main content + references**, A4, official ACL
two-column style with no modification to margins, spacing, fonts or page size.
Compiles with exit 0 and zero LaTeX errors.

## Compliance with the organisers' rules

| rule | status |
|---|---|
| 4--8 pages main content, references extra | 6 + refs |
| Official ACL style, unmodified | `acl.sty` as shipped |
| Title `<Team Name> at GroundLM 2026 Shared Tasks: <Title>` | "OdeD at GroundLM 2026 Shared Tasks: Reading the Scorer ..." |
| Team name identical on evaluator / paper / OpenReview `teamname` | **OdeD** |
| Author names, affiliations, contact info | Omar Saqr, Moustafa Gafaar --- both with affiliation and email |
| Report official evaluator results | Table 2, all 16 scored submissions |
| Disclose external data, models, tools, APIs, synthetic data | Section 9 |
| Report dev-set results, run comparisons, ablations | Tables 1 and 2, Sections 5--6, 8 |
| Error analysis | Section 7 |
| Conclusion, limitations, ethics | Sections 10--12 |

**Affiliations were inferred from the email domains** (`aucegypt.edu`,
`auto-pulse.co`). Correct them in the `\author` block if either is wrong ---
that is the one thing in the file that was not verified against a source.

## Before submitting

- [ ] Confirm both affiliations
- [ ] Run ACL PubCheck on the PDF
- [ ] Upload the JSONL that produced the reported score to `littraceqa-test`
- [ ] Attach code / reproducibility materials
- [ ] Submit via OpenReview: https://openreview.net/group?id=EMNLP/2026/Workshop/GroundLM

Due **19 August 2026, AoE** --- the same clock as the prediction deadline.

## If a later submission scores higher

The paper reports **0.7649** as the official best. To update, edit these four
places together so the file stays internally consistent:

1. abstract, first sentence (`0.7649`)
2. introduction, "Every subsequent gain, to $0.7649$"
3. Table 2 --- append a row, and move the bold to it
4. Section 6 "Where the score came from" (paper/evidence deltas, and the row F1 /
   cell accuracy figures), Section 11 first paragraph, and the conclusion

`0.5519` is the best **fully automated** run and should not change.

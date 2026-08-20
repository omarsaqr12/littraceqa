# System description paper --- GroundLM 2026 Shared Task 2 (LitTraceQA)

`littraceqa_system.tex` -> `littraceqa_system.pdf`. Official ACL two-column
style, unmodified. 6 pages of main content plus references (limit is 4--8 + refs).

    pdflatex littraceqa_system.tex && pdflatex littraceqa_system.tex

## Two things must be filled in before submitting

1. **Team name.** Line 6: `\newcommand{\teamname}{TEAMNAME}`. It must match, character
   for character, the immutable name registered on the evaluator Space and the
   `teamname` field in OpenReview. The organisers require the title to read
   `<Team Name> at GroundLM 2026 Shared Tasks: <Paper Title>`.
2. **Author block.** Name, affiliation, contact email. The final system paper is
   **not** anonymous --- author details are required.

## Submission checklist (from the organisers' page)

- [ ] Paper PDF, 4--8 pages main content + references, ACL style unmodified
- [ ] Team name identical on evaluator / paper title / OpenReview `teamname`
- [ ] Official evaluator scores reported (not locally computed) --- done, Table 1
- [ ] JSONL test outputs uploaded to `littraceqa-test` --- the file that produced
      the reported score
- [ ] Code / reproducibility materials
- [ ] External datasets, pretrained models, tools, APIs and synthetic data
      disclosed --- done, Section 8
- [ ] Run ACL PubCheck on the PDF
- [ ] Submit via OpenReview: https://openreview.net/group?id=EMNLP/2026/Workshop/GroundLM

Due **19 August 2026, AoE** --- the same clock as the prediction deadline.

## Note on the reported number

Table 1 reports the official evaluator output for every scored submission. The
headline is 0.7634, but the paper states plainly in the abstract and in
Section 9 that the best *fully automated* run is 0.5519 and that the difference
is per-question auditing plus leaderboard-feedback attribution. If a later
submission scores higher, update Table 1, the abstract, and Section 6 together.

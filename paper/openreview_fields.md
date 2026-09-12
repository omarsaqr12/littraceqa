# OpenReview camera-ready form — exact values

Invitation `EMNLP/2026/Workshop/GroundLM_Shared_Tasks/Submission9/-/Camera_Ready_Submission`.
**Due 2026-09-13 12:00 UTC** (hard expiry 2026-09-13 23:59 UTC).
All eleven fields are required. `paper_bibtex` is new since the original submission.

---

## 1. title

    OdeD at GroundLM 2026 Shared Tasks: Reading the Scorer for Literature-Grounded QA

Unchanged from the accepted submission. The shared-tasks page says the title
"should use the team name"; the camera-ready page says it "does not need to".
Both are satisfied by keeping the accepted title, and the shared-tasks page also
requires the same team name in the paper title/results.

## 2. team_name

    OdeD

## 3. participating_subtasks

    LitTraceQA

## 4. abstract

    We describe team OdeD's submission to LitTraceQA, the literature-grounded question answering task at GroundLM 2026. The task scores three coupled outputs: paper identifiers, coarse evidence locators, and answers in multiple-choice or table form. Our best official score on the 71-question held-out test split is 0.7649, against 0.4563 for our first submission and 0.5519 for our best fully automated one. Little of that improvement came from the retrieval-and-reading pipeline we began with; most of it came from two other sources. Reading the released evaluator showed the metric to be more asymmetric than it appears: paper F1 and evidence F1 carry weight $1/3$ each while each of the three answer metrics carries $1/9$. The evidence key is also a coarse tuple, so a correct value on a correct page scores zero when the source type or the visible object id is wrong. The 55-example development split then served to recover the dataset's annotation conventions rather than as a tuning set, and our own submission history became a measuring instrument. Each macro metric is a mean of a small number of rational per-question values, so a controlled change to one prediction file often admits a single arithmetic explanation. Two predicted deltas returned exact to four decimals. We report the conventions this recovered, six heuristics it refuted, four bugs it exposed in our own verifiers, and the limitation that much of our final score reflects per-question auditing and leaderboard feedback rather than a system that would generalise.
(Matches the PDF abstract exactly.)

## 5. pdf  (upload)

    paper/littraceqa_system.pdf

## 6. test_output_files  (upload)

    submission/OdeD_littraceqa_test_outputs.zip

Contains `littraceqa-test_OdeD.jsonl` (71 predictions, the exact run reported as
`v57` in Table 3) and `README.txt` with that run's full evaluator output.
We entered only the required `littraceqa-test` track.

## 7. code_or_repository_url

    https://github.com/omarsaqr12/littraceqa

## 8. model_checkpoints

    We trained and fine-tuned no models, so there are no checkpoints of our own to
    release. Every component is a hosted API or public pre-trained weights used as-is.

    - Google Gemini, hosted API, no downloadable checkpoint. Rotated over
      gemini-flash-lite-latest, gemini-3.5-flash and gemini-flash-latest, with
      gemini-3.7-flash in one selection experiment. gemini-flash-latest resolved to
      gemini-3.6-flash at a measured 20 requests/day on the free tier. Two of these
      names are floating aliases and we did not record which weights they resolved
      to; our runs fall between 16 and 19 August 2026.
      https://ai.google.dev/gemini-api/docs/models
    - Anthropic Claude, hosted API, the agent performing the per-question evidence
      audit. No downloadable checkpoint; we did not record the dated version.
      https://docs.anthropic.com/en/docs/about-claude/models
    - Qwen3-8B, public weights, transformers path:
      https://huggingface.co/Qwen/Qwen3-8B
    - Qwen3.6-27B-UD-Q4_K_XL GGUF, served locally by llama.cpp's llama-server for
      text-only selection experiments. We did not record the llama.cpp build.
    - Reranker BAAI/bge-reranker-base, public weights, used as-is:
      https://huggingface.co/BAAI/bge-reranker-base
    - Embeddings BAAI/bge-large-en-v1.5, public weights, used as-is:
      https://huggingface.co/BAAI/bge-large-en-v1.5

## 9. contact_email

    omar_saqr@aucegypt.edu

## 10. confirmation

    I confirm that this submission includes the system paper, final test outputs, and required information about external resources.

## 11. paper_bibtex

Paste the contents of `paper/saqr-2026-oded.bib`:

    @inproceedings{saqr-2026-oded,
      title     = {OdeD at GroundLM 2026 Shared Tasks: Reading the Scorer for Literature-Grounded QA},
      author    = {Saqr, Omar and Gaafar, Mostafa},
      booktitle = {Proceedings of the 1st Workshop on Grounding Language Models: Learning Faithfully and Efficiently (GroundLM 2026)},
      year      = {2026}
    }

---

## Authors on the submission

Leave the author list as it stands. Order is unchanged.

| # | name | affiliation | email |
|---|---|---|---|
| 1 | Omar Saqr (OpenReview: Omar Mokhtar Gaber Saqr, `~Omar_Mokhtar_Gaber_Saqr1`) | The American University in Cairo | omar_saqr@aucegypt.edu |
| 2 | Mostafa Gaafar (`~Mostafa_Gaafar1`) | The American University in Cairo | mostafa21314@aucegypt.edu |

The PDF previously read "Gafaar"; the OpenReview profile is the authority and the
PDF now matches it.

## Also upload separately

`paper/saqr-2026-oded.bib` — the camera-ready page asks for the `.bib` file
itself, in addition to the `paper_bibtex` field.

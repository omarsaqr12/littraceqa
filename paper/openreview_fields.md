# OpenReview form --- exact values for the four required fields

---

## Abstract*  (TeX inline math is supported; paste as-is)

We describe team OdeD's submission to LitTraceQA, the literature-grounded question answering task at GroundLM 2026. The task scores three coupled outputs -- paper identifiers, coarse evidence locators, and answers in multiple-choice or table form -- and our best official score on the 71-question held-out test split is $0.7649$, against $0.4563$ for our first submission and $0.5519$ for our best fully automated one. Almost none of the improvement came from the retrieval-and-reading pipeline we began with. It came from two other places. First, we read the released evaluator and found the metric is far more asymmetric than it looks: paper F1 and evidence F1 carry weight $1/3$ each while each of the three answer metrics carries only $1/9$, and the evidence key is the coarse tuple $(\textit{paper\_id}, \textit{source\_type}, \textit{page}, \textit{object\_id})$, in which a correct value on a correct page still scores zero if the source type or the visible object id is wrong. Second, we treated the 55-example development split as a corpus for recovering the dataset's annotation conventions rather than as a validation set for tuning, and we treated our own submission history as a measuring instrument: because each macro metric is a mean of a small number of rational per-question values, and $F_1 = 2C/(G+N)$ for $C$ correct items against $G$ gold and $N$ predicted, a controlled change to one prediction file often admits exactly one arithmetic explanation. Two of our predicted deltas came back exact to four decimals. We report the conventions this recovered, six heuristics it refuted, four bugs it exposed in our own verifiers, and the limitation that a large share of our final score reflects per-question auditing and leaderboard-feedback attribution rather than a system that would generalise.

---

## Test Output Files*  (upload)

    submission/OdeD_littraceqa_test_outputs.zip

Contains `littraceqa-test_OdeD.jsonl` (71 predictions, the exact run reported in
the paper) and a `README.txt` giving that run's full evaluator output. We entered
only the required `littraceqa-test` track, not the optional
`littraceqa-test-extra` diagnostic track.

---

## Code Or Repository Url*

    https://github.com/omarsaqr12/littraceqa

Make it public, or invite the organisers, before submitting. It contains the
pipeline, the five automated verifiers, the prompts, the experiment scripts, and
`reports/` recording every measurement including the negative ones.

---

## Model Checkpoints*

Paste this. It is a required field and the honest answer is that we released no
checkpoints, because we trained nothing:

> We trained and fine-tuned no models, so there are no checkpoints of our own to
> release. All components are either hosted APIs or public pre-trained weights
> used as-is:
>
> - Google Gemini, hosted API, `gemini-flash-lite-latest` and sibling flash
>   models -- no downloadable checkpoint:
>   https://ai.google.dev/gemini-api/docs/models
> - Anthropic Claude, hosted API, used as the agent performing the per-question
>   evidence audit -- no downloadable checkpoint:
>   https://docs.anthropic.com/en/docs/about-claude/models
> - Qwen3 (`Qwen/Qwen3-8B`), public weights, served locally through an
>   OpenAI-compatible llama.cpp endpoint: https://huggingface.co/Qwen/Qwen3-8B
> - Reranker `BAAI/bge-reranker-base`, public weights, used as-is:
>   https://huggingface.co/BAAI/bge-reranker-base
> - Embeddings `BAAI/bge-large-en-v1.5`, public weights, used as-is:
>   https://huggingface.co/BAAI/bge-large-en-v1.5
>
> No additional training data and no synthetic data were used.

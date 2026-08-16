# Benchmarking the local reader against the hosted one

> **CORRECTION (16 Aug 2026): the conclusion below did not survive contact with
> the test set.** Two independent problems:
>
> 1. The "weighted score" column uses the superseded weight vector. Under the
>    real weights the local reader's validation win shrinks from a claimed
>    +0.0033 to +0.0035 -- still nominally a win, but inside the noise of a
>    55-question split.
> 2. **On test it lost outright: 0.4462 against 0.4563 for the hosted reader.**
>    Evidence F1 fell 0.3587 -> 0.3324 despite emitting 93 items against 52.
>
> The methodological error: the local arm was run here, but the hosted arm was
> quoted from `scoring_and_fixes.md §5` rather than re-run on the same pipeline.
> Paper F1 matching exactly (0.4901) made that look safe; the reader-stage
> numbers were not comparable. **Run both arms yourself.** The table regression,
> which *was* measured on both arms here, replicated on test exactly as predicted
> (0.528 -> 0.437 on validation; 0.322 -> 0.269 on test).

Measured 16 Aug 2026 on validation (55 questions, official evaluator). Weighted
score throughout is the fitted leaderboard formula from `scoring_and_fixes.md`:
`0.364*paper + 0.337*evidence + 0.177*table + 0.108*MC`.

## Result: the local reader wins, and it wins where the test split lives

| config | paper | evidence | table | MC | **score** |
|---|---|---|---|---|---|
| `gemini-flash-lite` (report §5) | 0.4901 | 0.2770 | 0.5280 | 0.3900 | 0.4073 |
| local, 1 sample, 2 papers | 0.4901 | 0.2894 | 0.4371 | 0.4878 | 0.4060 |
| **local, 3 samples, 3 papers** | 0.4901 | **0.2953** | 0.4371 | **0.5122** | **0.4106** |

Paper F1 is identical by construction -- the reader runs after paper selection
and cannot change it.

On the `hidden_source_single_paper` family, which is the regime the test split
uses:

| config | evidence F1 | MC given a correct paper |
|---|---|---|
| `gemini-flash-lite` | 0.5380 | 0.6000 |
| local, 1 sample | 0.5641 | 0.8000 |
| **local, 3 samples** | **0.5769** | **0.8000** |

MC-given-a-correct-paper going 0.600 -> 0.800 is the largest single movement
measured on this project so far. The leaders sit at 1.000, so this closes half
the remaining gap on a component we had no other lever for.

Questions with no evidence at all fell from 16/55 to **10/55** with three
samples: the extra samples mostly recover locators the greedy pass missed.

## Why it is better despite being a smaller model

It is not better at reading. It is better at *locating*, and locating is what
the score pays for -- evidence is 33.7% of the weight against MC's 10.8%.

The hosted reader is handed a PDF and asked to name a page. The local reader is
handed `pdf/objects.py`'s enumerated candidate list and asked to pick an index,
so the page number comes from the PyMuPDF page index rather than from the
model's guess. That trade also explains the losses: on q_004 the local reader
picked `figure | Figure 4 | page 7` exactly right and still answered "4
subfigures" where gold is 8, because counting panels needs the image.

Being free is what made the win reachable. Three samples over three papers is
639 calls for a 71-question run; the hosted path is capped near 120.

## Two negative results

**Rewriting `TABLE_PROMPT` did nothing.** Table row F1 drops 0.528 -> 0.437 under
the local reader, so the prompt was rewritten to say the question decides the
rows, not the evidence, with an explicit "never collapse to one row". Output was
**byte-identical on all 11 table questions**. Reverted.

The real cause is upstream. Three of the four failures need more rows than we
read papers:

| question | gold rows | papers selected | papers read |
|---|---|---|---|
| q_022 | 3 | 2 | 2 |
| q_025 | 4 | 1 | 1 |
| q_054 | 2 | 1 | 1 |

q_025 wants one row per method and each method is a different paper, so the row
count is bounded by paper selection -- the cluster regime, already shown
unrecoverable in `exp/06`. q_030 scores **1.00 with zero readings**, which is the
same fact from the other side: when the question names its rows, the reader is
irrelevant.

**The justification for keeping that prompt was also wrong.** The change looked
worth keeping for the test split on the theory that test table questions
enumerate their rows ("on SciFact, HotpotQA, NFCorpus and Climate-FEVER"). Only
**1 of 21** test table questions contains such a list. The theory did not
survive being checked.

## Setup notes that cost real time

* **Usable context is `--ctx-size / --parallel`.** `serve.sh` ran 4096 across 2
  slots = 2048 tokens per request against a ~8k-token prompt, and llama-server
  *rejects* an oversized request rather than truncating it. One slot at 12288
  fits, and `_fit_pages()` now sizes page text to the declared budget instead of
  assuming it fits.
* **Constrain the output or lose it.** Unconstrained, Qwen3.6 narrates before
  answering and exhausts `max_tokens` mid-sentence: 2 of the first 3 questions
  returned nothing parseable. Grammar-constraining to `READ_SCHEMA` made that
  impossible *and* cut latency from ~93s to 6-19s per read, because the preamble
  is gone.
* **There is no usable HF-format Qwen on this box** -- only a 0.5B instruct, a 3B
  *base* model, and a 2B VL. The capable local model is the 27B GGUF, reachable
  only through llama-server, which is why `LocalReader` now takes a `base_url`.

## Reproduce

```bash
# server: one slot, context large enough for the prompt
./llama-server --model Qwen3.6-27B-UD-Q4_K_XL.gguf --host 127.0.0.1 --port 8080 \
  --n-gpu-layers 42 --ctx-size 12288 --parallel 1 --cont-batching --jinja \
  --cache-type-k q8_0 --cache-type-v q8_0

.venv/bin/python run.py --split validation --reader local \
  --local-model /home/mohab/models/Qwen3.6-27B-UD-Q4_K_XL.gguf \
  --local-base-url http://127.0.0.1:8080 --local-ctx 12288 \
  --local-samples 3 --max-papers 3 --question-timeout 1800 \
  --out preds/val_local_s3.jsonl
```

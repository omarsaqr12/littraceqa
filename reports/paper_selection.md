# Paper selection: recall fails, recognition works

Validation, 55 questions, official evaluator. Both arms of the final comparison
were run in this session with identical flags, after a previous local-vs-hosted
call was confounded by quoting one arm from an older report.

## Result

| component | control | + LLM selection | delta |
|---|---|---|---|
| paper F1 | 0.4901 | **0.5837** | **+0.0936** |
| evidence F1 | 0.2724 | **0.3127** | +0.0403 |
| MC accuracy | 0.4878 | **0.5854** | +0.0976 |
| table row F1 | 0.5280 | 0.5338 | +0.0059 |
| table cell accuracy | 0.2098 | 0.1929 | −0.0169 |
| **overall** | 0.3904 | **0.4446** | **+0.0542** |

Paper precision moves 0.6136 → 0.7582 and recall 0.4586 → 0.5364. Evidence and
MC follow paper selection without any change of their own, which is the
already-established pattern: MC is 0.600 with a correct paper and 0.062 without.

## E1 as specified: killed, and the mechanism measured

The endgame plan's C1 asks a model that knows the 2025 literature which paper the
question is about, takes the returned **title**, and matches it into the pool.

| config | paper F1 | test-like family |
|---|---|---|
| retrieval baseline | 0.4901 | 0.8462 |
| identify only | 0.2170 | 0.3462 |
| identify + retrieval fallback | 0.4998 | 0.8462 |

Identify returned a title on 47 of 55 questions but only 18 matched the pool. The
question is whether the matcher was too strict or the model was wrong, and it is
answerable directly — compare each returned title against the *gold* paper's
title:

```
unmatched but >=80 similar to gold:   0     <- matching too strict
unmatched and <80 (wrong title):     29     <- model does not know the title
median similarity of returned title to gold:  56
```

**Zero near-misses.** The model reliably recovers the artefact name and invents a
plausible title around it:

| question | model returned | actual title |
|---|---|---|
| q_053 | DetAny3D: Towards General Category 3D Object Detection | Detect Anything 3D in the Wild |
| q_041 | Simplified Consistency Models | Truncated Consistency Models |
| q_048 | MoD: Mixture of Depths for Hallucination Mitigation | Mixture of Decoding: An Attention-Inspired... |
| q_055 | MAGBIG: A Benchmark for Evaluating Multilingual... | Multilingual Text-to-Image Generation Magnifies... |

`MAGBIG` is the benchmark that paper *introduces*; the model turned the artefact
into a title. Exact-title reproduction is a recall task and flash-lite cannot do
it. Improving the matcher cannot help when the target is 56% similar.

One matcher improvement was made and kept regardless, because it is right in
principle: match the **head** of the title (the text before the first colon)
through the same n-gram index the nickname retriever uses, rather than fuzzing
the whole string. That took DynaPipe and FedRACE from unmatched to exact. It is
not enough to save the approach.

## The successor: recognition instead of recall

The kill criterion prescribed using the model as a reranker over the existing
candidates rather than as a generator, and that is what works. Hand it the 20
retrieved candidates with titles and abstracts and ask which the question is
about — a recognition task, where the answer is on the page.

```
gold present in the 20-candidate shortlist:  50/55
selection then picked a gold paper:          43/55
recognition accuracy where possible:         43/50 = 86.0%
```

The remaining headroom splits cleanly: 5 questions where gold is not in the
shortlist at all (a retrieval problem), and 7 where it is and the model chose
wrongly (a selection problem).

## A correction to my own experiment design

The E1 kill criterion gated on `hidden_source_single_paper` family F1. That
family was already at 0.846 with almost no headroom, so the criterion fired
"KILL" on the successor run too — while overall paper F1 rose 0.0936, entirely
within `multi_paper`. The criterion measured the wrong population.

Kill criteria should be stated on the metric the change is expected to move, not
on the sub-population that happens to be most familiar. Recorded because the
number was nearly discarded on the strength of a label the experiment printed
about itself.

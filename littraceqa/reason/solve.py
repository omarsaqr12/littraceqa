"""Answer synthesis: turn per-paper readings into the requested answer shape.

Three shapes, three very different metrics (plan.md §1):

* multiple_choice -- exact label match, 50 of 71 test questions. Always emit a
  label; a blind guess is worth 0.25 and abstention is worth 0.
* table -- row F1 over row-key columns plus cell accuracy on the rest. A missed
  row key zeroes every cell in that row, so row keys are found first and cells
  filled second.
* freeform -- exact string match after lowercasing. Absent from the test set;
  supported so validation numbers stay comparable.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from ..corpus import Paper, Question
from ..textnorm import clean
from .client import GeminiClient
from .localize import Reading

MC_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "reasoning": {"type": "string"},
        "confidence": {"type": "number"},
    },
    "required": ["label"],
}

MC_PROMPT = """Answer this multiple-choice question about scientific papers.

QUESTION
{question}

OPTIONS
{options}

EVIDENCE EXTRACTED FROM THE PAPERS
{evidence}

Pick the single option best supported by the evidence. The evidence was read
directly from the PDFs; prefer it over your own recollection of these papers.
If the evidence is incomplete, reason from what is there and still commit to one
option -- there is no credit for abstaining.

Reply with the option letter alone in `label`."""

TABLE_SCHEMA_OUT = {
    "type": "object",
    "properties": {
        "rows": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["rows"],
}

TABLE_PROMPT = """Build the answer table for this question about scientific papers.

QUESTION
{question}

REQUIRED COLUMNS (use exactly these names, every row must have every column)
{columns}

EVIDENCE EXTRACTED FROM THE PAPERS
{evidence}

Rules:
- Row-key columns are marked ROW KEY. They identify the row and are graded by
  exact string match, so use the exact surface form the question uses for them
  (a dataset name, a method name, a metric name). Where the row key is a paper
  title, use the full official title.
- Emit one row per item the question asks about -- no more. Extra rows cost
  precision.
- {types}
- Use null for a cell you genuinely cannot determine. Do not invent numbers."""

FREEFORM_PROMPT = """Give the final answer to this question about scientific papers.

QUESTION
{question}

EVIDENCE EXTRACTED FROM THE PAPERS
{evidence}

Reply with the answer value alone -- no explanation, no restatement of the
question, no units unless the question asks for them. It is scored by exact
string match against a short gold answer.

Examples of the expected form: "14.70"  "Freda Shi"  "8"
"a single NVIDIA RTX 4090 GPU\""""


def format_evidence(readings: list[Reading], pool_titles: dict[str, str]) -> str:
    """Compact digest of what each paper yielded, for the synthesis prompt."""
    if not readings:
        return "(no evidence was extracted)"
    lines = []
    for reading in readings:
        title = pool_titles.get(reading.paper_id, reading.paper_id)
        if not reading.found:
            lines.append(f"- {title} [{reading.paper_id}]: answer not found in this paper")
            continue
        where = ", ".join(
            f"{e.get('source_type')} {e.get('object_id') or ''} p.{e.get('page')}".strip()
            for e in reading.evidence
        ) or "unspecified location"
        lines.append(
            f"- {title} [{reading.paper_id}]: {reading.answer}"
            f"  (confidence {reading.confidence:.2f}; from {where})"
            + (f'\n    quote: "{reading.quote[:280]}"' if reading.quote else "")
        )
    return "\n".join(lines)


class AnswerSolver:
    def __init__(self, client: GeminiClient, *, mc_samples: int = 3):
        self.client = client
        self.mc_samples = mc_samples

    # -- multiple choice ------------------------------------------------------

    def solve_multiple_choice(
        self, question: Question, readings: list[Reading], titles: dict[str, str]
    ) -> str:
        options = question.multiple_choice_options or {}
        if not options:
            return "A"
        labels = sorted(options)
        prompt = MC_PROMPT.format(
            question=question.question,
            options="\n".join(f"  {label}. {options[label]}" for label in labels),
            evidence=format_evidence(readings, titles),
        )

        # Self-consistency: k samples, majority vote. The cheapest accuracy point
        # available on an exact-match metric (Wang et al., 2022).
        votes: Counter[str] = Counter()
        for sample in range(max(1, self.mc_samples)):
            payload = self.client.generate_json(
                prompt,
                schema=MC_SCHEMA,
                max_output_tokens=600,
                # Sample 0 is greedy and cached; later samples vary the seed via
                # a suffix so the cache key differs.
                default=None,
            ) if sample == 0 else self.client.generate_json(
                prompt + f"\n\n(independent attempt {sample + 1})",
                schema=MC_SCHEMA,
                max_output_tokens=600,
                default=None,
            )
            label = _clean_label(payload.get("label") if isinstance(payload, dict) else None)
            if label in options:
                votes[label] += 1
        if votes:
            return votes.most_common(1)[0][0]
        return _fallback_label(question, readings, labels, options)

    # -- table ----------------------------------------------------------------

    def solve_table(
        self,
        question: Question,
        readings: list[Reading],
        titles: dict[str, str],
        papers: list[Paper],
    ) -> dict[str, Any]:
        schema = question.table_schema or []
        columns = [str(c.get("name", "")) for c in schema if isinstance(c, dict)]
        if not columns:
            return {"rows": []}

        row_keys = [
            str(c.get("name")) for c in schema if isinstance(c, dict) and c.get("is_row_key")
        ] or columns[:1]

        # Free win: when the row key is a paper-title column, gold row values are
        # the pool's `title` field verbatim (entities and all). Emit those rather
        # than letting the model paraphrase -- row F1 then tracks paper F1 exactly.
        if len(columns) == 1 and _is_title_column(columns[0]) and papers:
            return {"rows": [{columns[0]: p.title} for p in papers]}

        column_lines = "\n".join(
            f"  - {c.get('name')} ({c.get('type', 'string')})"
            + ("  [ROW KEY]" if c.get("is_row_key") else "")
            for c in schema if isinstance(c, dict)
        )
        numeric = [
            str(c.get("name")) for c in schema
            if isinstance(c, dict) and c.get("type") == "number"
        ]
        types_note = (
            f"Columns {numeric} must hold JSON numbers, not strings."
            if numeric else "All non-null cells are strings."
        )
        payload = self.client.generate_json(
            TABLE_PROMPT.format(
                question=question.question,
                columns=column_lines,
                evidence=format_evidence(readings, titles),
                types=types_note,
            ),
            schema=TABLE_SCHEMA_OUT,
            max_output_tokens=2400,
            default=None,
        )
        rows = payload.get("rows") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows:
            # A table answer must be a non-empty list of complete rows to validate.
            if _is_title_column(row_keys[0]) and papers:
                return {"rows": [_complete_row({row_keys[0]: p.title}, schema) for p in papers]}
            return {"rows": [_complete_row({}, schema)]}
        return {"rows": [_complete_row(r, schema) for r in rows if isinstance(r, dict)]}

    # -- freeform -------------------------------------------------------------

    def solve_freeform(
        self, question: Question, readings: list[Reading], titles: dict[str, str]
    ) -> str:
        confident = [r for r in readings if r.found and r.answer]
        if len(confident) == 1:
            return confident[0].answer
        text = self.client.generate(
            FREEFORM_PROMPT.format(
                question=question.question,
                evidence=format_evidence(readings, titles),
            ),
            max_output_tokens=400,
        ).strip()
        text = text.strip().strip('"').strip()
        return text or (confident[0].answer if confident else "unknown")


# --- helpers -----------------------------------------------------------------

_TITLE_COLUMN = re.compile(r"\b(paper|article|publication)?\s*title\b|^paper$", re.I)


def _is_title_column(name: str) -> bool:
    return bool(_TITLE_COLUMN.search(name or ""))


def _clean_label(value: Any) -> str:
    text = str(value or "").strip().upper()
    match = re.search(r"\b([A-Z])\b", text)
    return match.group(1) if match else text[:1]


def _complete_row(row: dict[str, Any], schema: list[dict[str, Any]]) -> dict[str, Any]:
    """Force a row to carry exactly the schema's columns with the right types.

    `validate_submission.py` rejects any row whose key set differs from the
    schema, and rejects a cell whose type does not match (or is not null).
    """
    out: dict[str, Any] = {}
    for column in schema:
        if not isinstance(column, dict):
            continue
        name = str(column.get("name", ""))
        expected = str(column.get("type", "string"))
        value = row.get(name)
        if value is None:
            out[name] = None
        elif expected == "number":
            out[name] = _to_number(value)
        elif expected == "boolean":
            out[name] = bool(value) if isinstance(value, bool) else _to_bool(value)
        else:
            out[name] = value if isinstance(value, str) else str(value)
    return out


def _to_number(value: Any) -> float | int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return None
    text = match.group(0)
    return int(text) if "." not in text else float(text)


def _to_bool(value: Any) -> bool | None:
    text = str(value).strip().lower()
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0"}:
        return False
    return None


def _fallback_label(
    question: Question, readings: list[Reading], labels: list[str], options: dict[str, str]
) -> str:
    """Last resort when every LLM sample failed: match extracted answers to options."""
    from rapidfuzz import fuzz

    extracted = " ".join(r.answer for r in readings if r.found and r.answer)
    if extracted:
        best = max(labels, key=lambda l: fuzz.partial_ratio(extracted.lower(),
                                                            str(options[l]).lower()))
        return best
    return labels[0]

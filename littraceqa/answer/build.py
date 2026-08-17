"""Schema-exact submission records, plus an in-process validator.

`validate_submission.py` is strict in ways that are easy to trip:

* top-level keys ⊆ {query_id, gold_papers, answer, evidence}
* ``gold_papers[i]`` must be exactly ``{"paper_id": ...}``
* ``evidence[i]`` must be exactly ``{"paper_id", "source_type", "locator"}`` with
  a **non-empty** locator drawn from a closed key set
* ``set(answer) == set(answer_types)`` -- every requested type present, nothing extra
* ``answer.multiple_choice`` holds **only** ``gold`` (not ``label``)
* ``answer.table`` holds **only** ``rows``, non-empty, each row's key set equal to
  the input's ``table_schema`` column set

Building records through here rather than by hand is what keeps a run from
failing validation at submission time.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from ..corpus import Question

ALLOWED_LOCATOR_KEYS = {
    "page", "table_id", "figure_id", "section", "equation_id", "algorithm_id", "citation_id",
}
SOURCE_TYPES = {"table", "figure", "text_span", "equation_algorithm", "citation_context"}


def deterministic_label(query_id: str, labels: list[str]) -> str:
    """A reproducible uniform pick among `labels`, for when solving failed.

    The previous fallback was `sorted(options)[0]`, i.e. always "A". That is the
    single worst constant available: validation gold labels run A=2, B=17, C=11,
    D=11, so "A" is the correct answer 4.9% of the time against 25% for a blind
    guess. `test_v2_rerank.jsonl` emitted A on 16 of 71 questions, most of them
    solver failures, so this was live and costing points.

    Uniform rather than "always B" on purpose: B wins on 41 validation samples,
    but that is a property of one small annotated split, and a constant that
    happens to fit it does not transfer. Uniform earns 25% against any gold
    distribution. Seeded on `query_id` so a rerun reproduces exactly.
    """
    if not labels:
        return "A"
    digest = hashlib.sha256(str(query_id).encode()).digest()
    return sorted(labels)[int.from_bytes(digest[:8], "big") % len(labels)]


def clean_locator(locator: dict[str, Any]) -> dict[str, Any]:
    """Drop keys the schema forbids and coerce `page` to a positive int."""
    out: dict[str, Any] = {}
    for key, value in (locator or {}).items():
        if key not in ALLOWED_LOCATOR_KEYS or value is None:
            continue
        if key == "page":
            try:
                page = int(value)
            except (TypeError, ValueError):
                continue
            if page >= 1:
                out["page"] = page
        else:
            text = str(value).strip()
            if text:
                out[key] = text
    return out


def build_record(
    question: Question,
    paper_ids: list[str],
    evidence: list[dict[str, Any]],
    answer_parts: dict[str, Any],
) -> dict[str, Any]:
    """Assemble one prediction line. Never raises -- always emits a valid shape."""
    seen: set[str] = set()
    gold_papers = []
    for paper_id in paper_ids:
        paper_id = str(paper_id or "").strip()
        if paper_id and paper_id not in seen:
            seen.add(paper_id)
            gold_papers.append({"paper_id": paper_id})

    evidence_out: list[dict[str, Any]] = []
    evidence_seen: set[tuple] = set()
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        paper_id = str(item.get("paper_id") or "").strip()
        source_type = str(item.get("source_type") or "").strip()
        locator = clean_locator(item.get("locator") or {})
        if not paper_id or source_type not in SOURCE_TYPES or not locator:
            continue
        key = (paper_id, source_type, tuple(sorted(locator.items())))
        if key in evidence_seen:
            continue
        evidence_seen.add(key)
        evidence_out.append(
            {"paper_id": paper_id, "source_type": source_type, "locator": locator}
        )

    answer: dict[str, Any] = {}
    types = set(question.answer_types)

    if "freeform" in types:
        text = str(answer_parts.get("freeform") or "").strip()
        # The validator rejects an empty string outright, so never emit one.
        answer["freeform"] = {"text": text or "unknown"}

    if "multiple_choice" in types:
        options = question.multiple_choice_options or {}
        label = str(answer_parts.get("multiple_choice") or "").strip().upper()
        if label not in options:
            label = deterministic_label(question.query_id, sorted(options))
        answer["multiple_choice"] = {"gold": label}

    if "table" in types:
        schema = question.table_schema or []
        rows = (answer_parts.get("table") or {}).get("rows") or []
        columns = {str(c.get("name")): str(c.get("type", "string")) for c in schema
                   if isinstance(c, dict)}
        fixed = [_conform_row(r, columns) for r in rows if isinstance(r, dict)]
        if not fixed:
            fixed = [{name: None for name in columns}]
        answer["table"] = {"rows": fixed}

    return {
        "query_id": question.query_id,
        "gold_papers": gold_papers,
        "evidence": evidence_out,
        "answer": answer,
    }


def _conform_row(row: dict[str, Any], columns: dict[str, str]) -> dict[str, Any]:
    """Coerce a row to the schema's columns and types, nulling as a last resort.

    `cell_equal` counts a cell correct only when gold and prediction are *both*
    null, and **0 of 27 graded gold cells on validation are null** (exp/11). So
    null is a guaranteed zero here, exactly as costly as a wrong guess and
    strictly worse than a plausible one.

    This used to null any type mismatch outright, which threw away real answers:
    a model returning the string ``"2.05"`` for a number column had it deleted
    rather than parsed. Recovery is attempted first now, and the prompt no
    longer invites nulls either -- both paths had to change, since fixing only
    the prompt leaves the coercion silently undoing it.
    """
    out: dict[str, Any] = {}
    for name, expected in columns.items():
        value = row.get(name)
        if value is None:
            out[name] = None
        elif expected == "number":
            number = _coerce_number(value)
            out[name] = number
        elif expected == "boolean":
            out[name] = value if isinstance(value, bool) else _coerce_bool(value)
        else:
            out[name] = value if isinstance(value, str) else str(value)
    return out


def _coerce_number(value: Any) -> float | int | None:
    """Best-effort number out of whatever the model produced.

    Handles the forms that actually show up in scientific tables: ``"2.05"``,
    ``"96.2%"``, ``"32.7±0.5"``, ``"1,204,000"``, ``"~4.1"``. Takes the first
    numeric token, which is the value rather than its error bar.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).replace(",", "").replace("−", "-")
    match = re.search(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text)
    if not match:
        return None
    token = match.group(0)
    try:
        return float(token) if any(c in token for c in ".eE") else int(token)
    except ValueError:
        return None


def _coerce_bool(value: Any) -> bool | None:
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1"}:
        return True
    if text in {"false", "no", "n", "0"}:
        return False
    return None


def validate_records(
    records: list[dict[str, Any]], questions: list[Question], paper_ids: set[str]
) -> list[str]:
    """Run the official validator in-process against the released inputs."""
    import sys
    from pathlib import Path

    scripts = Path(__file__).resolve().parent.parent.parent / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from validate_submission import validate_submission

    return validate_submission(
        [q.raw for q in questions], records, require_evidence=True, paper_ids=paper_ids
    )

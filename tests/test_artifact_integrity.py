"""Lightweight repository checks; NOT an end-to-end QA benchmark.

Run: python3 -m unittest discover -s tests -p 'test_*.py' -v
"""

import csv
from pathlib import Path
import re
import unittest
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
FRONT_DOOR_DOCS = (
    ROOT / "README.md",
    ROOT / "data" / "README.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "docs" / "EXPERIMENT_INDEX.md",
    ROOT / "docs" / "REPRODUCIBILITY.md",
    ROOT / "exp" / "README.md",
    ROOT / "reports" / "README.md",
    ROOT / "results" / "README.md",
    ROOT / "submission" / "README.md",
)
LINK = re.compile(r"\[[^\]\n]+\]\(([^)\n]+)\)")
SCORE_FIELDS = ("paper_f1", "evidence_f1", "mc", "row_f1", "cell_acc")


class ArtifactIntegrityTests(unittest.TestCase):
    def test_new_and_entrypoint_markdown_links_resolve_locally(self):
        for document in FRONT_DOOR_DOCS:
            with self.subTest(document=str(document.relative_to(ROOT))):
                self.assertTrue(document.is_file())
                contents = document.read_text(encoding="utf-8")
                for target in LINK.findall(contents):
                    target = target.split("#", 1)[0].split("?", 1)[0]
                    if not target or target.startswith(("https://", "http://", "mailto:")):
                        continue
                    resolved = (document.parent / unquote(target)).resolve()
                    with self.subTest(source=document.name, target=target):
                        self.assertTrue(resolved.is_relative_to(ROOT), "link escapes repository")
                        self.assertTrue(resolved.exists(), f"missing local link {target}")

    def test_retained_official_components_are_arithmetically_consistent(self):
        # Independent arithmetic check of recorded components only. We cannot
        # authenticate their provenance or recreate the hidden-test evaluator.
        with (ROOT / "results" / "official_scores.csv").open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertGreater(len(rows), 0)
        checked = 0
        for row in rows:
            missing = [name for name in SCORE_FIELDS if not row[name].strip()]
            if missing:
                continue
            p, e, mc, rf1, cell = (float(row[name]) for name in SCORE_FIELDS)
            computed = (p + e + (mc + rf1 + cell) / 3) / 3
            # Full-precision retained components are rounded in the CSV; the
            # displayed overall is also rounded, so allow 1e-5 in addition to
            # the official display's documented rounding interval.
            tolerance = 0.00010 if row["precision"] == "4dp" else 0.000051
            checked += 1
            with self.subTest(run=row["run"], submission_id=row["submission_id"]):
                self.assertLessEqual(abs(computed - float(row["overall_shown"])), tolerance)
        self.assertGreater(checked, 0)


if __name__ == "__main__":
    unittest.main()

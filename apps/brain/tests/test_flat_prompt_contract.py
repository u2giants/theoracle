"""Offline rubric contract checks; no database or model dependencies required.

Run directly with Python's unittest runner in restricted fixer environments.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

BRAIN_DIR = Path(__file__).resolve().parents[1] / "brain"
EXPECTED_LABELS = [{'name': 'process',
  'rubric': 'Describes how work moves: ordered steps, approvals, hand-offs, submissions, '
            'reviews or status changes, even when told conversationally.'},
 {'name': 'responsibility',
  'rubric': 'States who owns, performs, approves, or is the go-to person or team for '
            'something.'},
 {'name': 'rule',
  'rubric': 'States a requirement, policy, condition, prohibition, deadline, threshold, '
            'minimum, or an exception to the usual way.'},
 {'name': 'reference',
  'rubric': 'Lists or explains systems, files, codes, accounts, brands, products or '
            'definitions, including someone describing what a tool holds or is used for.'},
 {'name': 'problem',
  'rubric': 'Describes something going wrong: a delay, error, rework, missing information, '
            'workaround, frustration or pain point.'},
 {'name': 'decision',
  'rubric': 'Records a decision made or pending, an agreement on what to do, or a disagreement '
            'about it.'},
 {'name': 'chatter',
  'rubric': 'Only greetings, small talk, scheduling or jokes. NOT chatter if it names any '
            'system, document, brand, customer, team, rule or work step.'}]


class FlatPromptContractTests(unittest.TestCase):
    def test_classify_labels_preserve_validated_rubrics(self) -> None:
        # Read the literal without importing the database/model dependency tree.
        module = ast.parse((BRAIN_DIR / "extract/flat.py").read_text(encoding="utf-8"))
        labels = next(
            ast.literal_eval(node.value)
            for node in module.body
            if isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "CLASSIFY_LABELS"
        )
        self.assertEqual(labels, EXPECTED_LABELS)

    def test_frontier_prompt_uses_validated_classify_rubrics(self) -> None:
        prompt = (BRAIN_DIR / "prompts/flat_extract.md").read_text(encoding="utf-8")
        block = prompt.split("CLASSIFY LABELS", 1)[1].split("ENTITY TYPES", 1)[0]
        actual = [line for line in block.splitlines() if line.startswith("- ")]
        expected = [f"- {label['name']}: {label['rubric']}" for label in EXPECTED_LABELS]
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()

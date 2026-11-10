"""Offline replay contracts; run with unittest (no database or model required)."""

import ast
import json
import re
import unittest
from pathlib import Path
from typing import Any

TESTS = Path(__file__).resolve().parent
FIXTURES = TESTS / 'fixtures'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def replay_grader():
    # Exercise the actual replay grader without importing database test setup.
    tree = ast.parse((TESTS / 'test_eval_fixture.py').read_text(encoding='utf-8'))
    nodes = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef))
             and node.name in {'KeywordGrader', '_wrap'}]
    scope = {'Any': Any, 'json': json, 're': re, 'MARKER': re.compile(r'\[(\d+)\]'),
             'load_recorded': lambda name: read_json(FIXTURES / 'recorded' / name)}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<replay>', 'exec'), scope)
    return scope['KeywordGrader']()


class ReplayContractTests(unittest.TestCase):
    def test_fixture_sources_and_replay_coverage(self):
        questions = read_json(FIXTURES / 'eval.questions.json')['questions']
        answers = read_json(FIXTURES / 'recorded/frontier/eval_answers.json')['answers']
        titles = {'licensing-approval-procedure.pdf', 'teams-approval-2026-03-14.txt',
                  'licensing-approval-flowchart.png'}
        self.assertEqual(len(questions), 15)
        self.assertEqual(set(answers), {row['question'] for row in questions})
        grader = replay_grader()
        for row in questions:
            with self.subTest(question=row['question']):
                self.assertTrue(row['expected_source_titles'])
                self.assertLessEqual(set(row['expected_source_titles']), titles)
                points = '\n'.join(f'{i}. {point}' for i, point in enumerate(row['expected_points']))
                prefix = f'EXPECTED POINTS:\n{points}\n\nANSWER:\n'
                answer = answers[row['question']]
                grade = json.loads(grader([{'content': prefix + answer}], None)['choices'][0]['message']['content'])
                self.assertEqual(grade['missing'], [])
                uncited = re.sub(r'\[\d+\]', '', answer)
                grade = json.loads(grader([{'content': prefix + uncited}], None)['choices'][0]['message']['content'])
                self.assertEqual(grade['covered'], [])

    def test_zh_paraphrase_and_missing_point(self):
        grader = replay_grader()
        point = '签署确认记录在美术稿台账中'
        prefix = f'EXPECTED POINTS:\n0. {point}\n\nANSWER:\n'
        for text, expected in [('请查阅美术稿台账，里面保存了确认记录 [1]。', [0]),
                               ('相关同事负责保存记录 [1]。', [])]:
            grade = json.loads(grader([{'content': prefix + text}], None)['choices'][0]['message']['content'])
            self.assertEqual(grade['covered'], expected)

    def test_production_drafts_are_not_replayed_as_fixture_proof(self):
        drafts = read_json(TESTS.parent / 'eval/questions.seed.json')['questions'][5:]
        answers = read_json(FIXTURES / 'recorded/frontier/eval_answers.json')['answers']
        self.assertEqual(len(drafts), 10)
        for row in drafts:
            self.assertEqual(row['evidence_status'], 'unverified-production-draft')
            self.assertNotIn(row['question'], answers)
            self.assertNotIn('teams-approval-2026-03-14.txt', row['expected_source_titles'])

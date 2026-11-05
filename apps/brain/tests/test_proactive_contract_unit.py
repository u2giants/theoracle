"""Dependency-free checks of the proactive response contract."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load_function(relative, name, namespace):
    tree = ast.parse((ROOT / relative).read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    function.decorator_list = []
    exec(compile(ast.Module(body=[function], type_ignores=[]), relative, 'exec'), namespace)
    return namespace[name]


class ContractTests(unittest.TestCase):
    def test_only_explicit_unreachable_response_skips(self):
        class SendError(Exception):
            pass

        class Unreachable(SendError):
            pass

        settings = SimpleNamespace(brain_web_base_url='https://web', brain_shared_token='token')
        for status, body, expected in [
            (404, {'error': 'not_reachable'}, Unreachable),
            (404, {'error': 'unknown_employee'}, SendError),
            (404, {}, SendError),
            (502, {'error': 'not_reachable'}, SendError),
            (200, {}, None),
        ]:
            with self.subTest(status=status, body=body):
                response = SimpleNamespace(status_code=status, text='response', json=lambda: body)
                post = load_function('brain/interview/tick.py', '_post_proactive', {
                    'Settings': object, 'InterviewSendError': SendError,
                    'InterviewUnreachableError': Unreachable,
                    'httpx': SimpleNamespace(post=lambda *a, **kw: response),
                })
                if expected:
                    with self.assertRaises(expected) as caught:
                        post('e', 'question', settings)
                    self.assertIs(type(caught.exception), expected)
                else:
                    post('e', 'question', settings)

    def test_lookup_never_borrows_another_employee_endpoint(self):
        statements = []

        class Cursor:
            def __init__(self, value):
                self.value = value

            def fetchone(self):
                return self.value

            def fetchall(self):
                return self.value

        class Connection:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, sql, params):
                statements.append(sql)
                return Cursor(('Employee', 'a@b', None) if 'SELECT e.name' in sql else [])

        lookup = load_function('brain/api/interview.py', 'teams_conversation', {
            'Any': object, '_uuid': lambda value, _: value,
            'get_pool': lambda: SimpleNamespace(connection=Connection),
        })
        self.assertIsNone(lookup('e')['service_url'])
        self.assertEqual(len(statements), 2)


if __name__ == '__main__':
    unittest.main()

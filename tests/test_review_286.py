"""Offline regression checks for interview request isolation and transactions."""
import ast
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]


def load(relative, names, scope):
    tree = ast.parse((ROOT / relative).read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), relative, 'exec'), scope)
    return scope


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code


class InterviewRegression(unittest.TestCase):
    def test_service_rejects_employee_header(self):
        scope = load('apps/brain/brain/api/deps.py', {'require_service'}, {
            'Header': lambda default: default, 'HTTPException': HTTPException,
            'get_settings': lambda: SimpleNamespace(brain_shared_token='secret'),
        })
        service = scope['require_service']
        service('secret', None)
        for user in ('employee', ''):
            with self.assertRaises(HTTPException) as error:
                service('secret', user)
            self.assertEqual(error.exception.status_code, 403)
        with self.assertRaises(HTTPException) as error:
            service('wrong', None)
        self.assertEqual(error.exception.status_code, 401)

    def inbound(self, text, ingest=None):
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = ('question-id', 'Who approves?')
        pool = SimpleNamespace(connection=lambda: nullcontext(conn))
        ingest = ingest or Mock(return_value={'id': 'source-id'})
        from datetime import datetime
        from zoneinfo import ZoneInfo
        scope = load('apps/brain/brain/interview/inbound.py', {'handle_inbound'}, {
            'Any': object, 'get_pool': lambda: pool,
            '_find_employee': lambda conn, email: ('employee-id', 'Employee'),
            '_command': lambda text: text.strip().lower(),
            '_transcript_text': lambda *args: 'transcript',
            'datetime': datetime, 'EASTERN': ZoneInfo('America/New_York'),
            'ingest_bytes': ingest, 'ANSWER_WINDOW_DAYS': 7,
            'REPLY_ANSWERED': 'Thanks',
        })
        return scope['handle_inbound'], conn, ingest

    def test_blank_is_not_an_answer(self):
        handler, conn, ingest = self.inbound(' ')
        self.assertFalse(handler(email='e', conversation_ref=None, text=' \n')['handled'])
        ingest.assert_not_called()
        conn.execute.assert_not_called()

    def test_answer_holds_lock_and_uses_same_transaction(self):
        handler, conn, ingest = self.inbound('Answer')
        self.assertTrue(handler(email='e', conversation_ref=None, text='Answer')['handled'])
        self.assertIn('FOR UPDATE', conn.execute.call_args_list[0].args[0])
        self.assertIs(ingest.call_args.kwargs['conn'], conn)
        conn.commit.assert_called_once()

    def test_failed_ingestion_does_not_commit_answer(self):
        handler, conn, ingest = self.inbound('Answer', Mock(side_effect=RuntimeError('failed')))
        with self.assertRaises(RuntimeError):
            handler(email='e', conversation_ref=None, text='Answer')
        conn.commit.assert_not_called()
        self.assertEqual(conn.execute.call_count, 1)

    def test_source_and_job_use_supplied_transaction(self):
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = ('source',)
        enqueue = Mock()
        scope = load('apps/brain/brain/api/sources.py', {'_insert_source'}, {
            'Any': object, 'date': object, 'get_pool': Mock(), 'nullcontext': nullcontext,
            '_SOURCE_COLUMNS': 'id', '_row_to_dict': lambda row: {'id': row[0]},
            'enqueue_job': enqueue, 'Json': lambda value: value,
        })
        result = scope['_insert_source'](
            source_id='source', kind='transcript', title='Answer', original_filename='a.txt',
            storage_path='key', sha='sha', data_len=1, department_hint=None,
            effective_date=None, uploaded_by=None, conn=conn,
        )
        self.assertEqual(result['id'], 'source')
        self.assertIn('INSERT INTO cmap.job', conn.execute.call_args.args[0])
        conn.commit.assert_not_called()
        enqueue.assert_not_called()

    def test_join_is_checked_before_interview_handoff(self):
        route = (ROOT / 'apps/web/app/api/teams/bot/messages/route.ts').read_text()
        self.assertIn('if (!isJoinCommand(commandText) && await offerToInterviews(context, commandText)) return;', route)


if __name__ == '__main__':
    unittest.main()

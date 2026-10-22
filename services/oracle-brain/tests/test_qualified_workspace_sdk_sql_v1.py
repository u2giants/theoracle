"""Actual workspace SQL/SDK/TLS case, independently scheduled within W10."""
from test_connected_answer_sdk_sql_v1 import _exercise_owned_answer_graph_v1
from test_consolidation_sql_v1 import sql_qualified_serving_v3
from test_purpose_transport import bound_tls,certificates


def test_actual_workspace_same_SQL_ACK_SDK_TLS_closed_TS_and_revoked_recipient(admin_url,sql_qualified_serving_v3,tmp_path,bound_tls,certificates):
 # A fresh qualified fixture is appointed before original capture; prior cases
 # and their original deadlines are not changed or relabeled.
 return _exercise_owned_answer_graph_v1(admin_url,sql_qualified_serving_v3,tmp_path,bound_tls,certificates,proof_scope='workspace')

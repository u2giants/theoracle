"""Impact routing and evidence regressions without live services."""

import json
from contextlib import nullcontext
from unittest.mock import Mock

import pytest
from psycopg import OperationalError
from redis.exceptions import ConnectionError as GraphConnectionError

from brain.answer import answer, impact
from brain.config import Settings

SEED = "00000000-0000-4000-8000-000000000001"
TARGET = "00000000-0000-4000-8000-000000000002"
CHUNK = "00000000-0000-4000-8000-000000000003"
QUOTE = "Alice Chen performs the artwork approval."
QUESTION = "What breaks if Alice Chen is out?"
HISTORY = [{"role": "user", "content": "Tell me about artwork approvals."}]


@pytest.mark.parametrize(
    ("alias", "subject"),
    [("AL-CHEN", "Al Chen is out"), ("採購部門", "采购部门 is unavailable")],
)
def test_alias_uses_same_fold_as_subject(alias, subject):
    conn = Mock()
    conn.execute.return_value.fetchall.return_value = [(SEED, "Alice Chen", alias)]
    assert impact._named_subject(conn, subject) == (SEED, "Alice Chen")


def test_bad_graph_data_does_not_discard_valid_evidence(monkeypatch):
    def execute(sql, params):
        if "cmap.entity_alias" in sql:
            rows = [(SEED, "Alice Chen", None)]
        elif "cmap.process_flow" in sql:
            assert set(params["ids"]) <= {SEED, TARGET}
            rows = []
        else:
            assert params == ([CHUNK],)
            rows = [(CHUNK, SEED, "Approval guide", "page 1", QUOTE)]
        return Mock(fetchall=Mock(return_value=rows))

    pool = Mock(connection=Mock(return_value=nullcontext(Mock(execute=execute))))
    monkeypatch.setattr(impact, "get_pool", lambda: pool)
    refs = json.dumps(
        [
            None,
            {"chunk_id": "bad-uuid", "quote": QUOTE},
            {"chunk_id": CHUNK, "quote": QUOTE},
        ]
    )
    monkeypatch.setattr(
        impact,
        "impact_edges",
        lambda ids, _: (
            [
                (SEED, TARGET, "Bad JSON", "PERFORMS", "{"),
                (SEED, TARGET, "Wrong shape", "PERFORMS", "{}"),
                (SEED, "bad-target", "Bad target", "PERFORMS", refs),
                (SEED, TARGET, "Artwork approval", "PERFORMS", refs),
            ]
            if SEED in ids
            else []
        ),
    )
    result = impact.trace_impact("Alice Chen is out", Settings())
    assert result is not None
    markdown, citations = result
    assert "Alice Chen performs Artwork approval" in markdown
    assert "Bad" not in markdown
    assert [citation["chunk_id"] for citation in citations] == [CHUNK]


@pytest.mark.parametrize(
    "question",
    [
        "Who is affected if we launch X?",
        "What breaks if we follow process?",
        "Who waits if we follow process?",
    ],
)
def test_non_disruption_uses_regular_answer(monkeypatch, question):
    settings, usage = Settings(), {}
    route = Mock(return_value=[])
    trace = Mock()
    regular = Mock(return_value={"answer_md": "Regular answer"})
    monkeypatch.setattr(answer, "_route_functions", route)
    monkeypatch.setattr(answer, "_global_answer", regular)
    monkeypatch.setattr(answer, "trace_impact", trace)
    assert (
        answer.answer_question(question, "auto", HISTORY, settings, usage)["answer_md"]
        == "Regular answer"
    )
    route.assert_called_once_with(question, HISTORY, settings, usage)
    regular.assert_called_once_with(question, HISTORY, settings, usage)
    trace.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [
        None,
        OperationalError("database unavailable"),
        GraphConnectionError("graph unavailable"),
    ],
)
def test_unresolved_or_failed_trace_preserves_scoped_answer(monkeypatch, error):
    settings, usage = Settings(), {}
    routed = [{"id": SEED, "weight": 0.9}]
    route = Mock(return_value=routed)
    trace = Mock(return_value=None, side_effect=error)
    pool = Mock(connection=Mock(return_value=nullcontext(Mock())))
    graph = Mock()
    graph.query.return_value.result_set = [(TARGET,)]
    regular = Mock(return_value={"answer_md": "Regular answer", "mode_used": "local"})
    monkeypatch.setattr(answer, "_route_functions", route)
    monkeypatch.setattr(answer, "get_pool", lambda: pool)
    monkeypatch.setattr(answer, "_function_entity_ids", lambda conn, ids: [SEED])
    monkeypatch.setattr(answer, "connect_graph", lambda cfg: graph)
    monkeypatch.setattr(answer, "trace_impact", trace)
    monkeypatch.setattr(answer, "_local_answer", regular)

    result = answer.answer_question(QUESTION, "local", HISTORY, settings, usage)
    assert result["answer_md"] == "Regular answer"
    assert result["mode_used"] == "local"
    route.assert_called_once_with(QUESTION, HISTORY, settings, usage)
    trace.assert_called_once_with(
        "Alice Chen is out?",
        settings,
        function_ids=[SEED],
        universe_ids=[SEED],
        graph_scope={SEED, TARGET},
    )
    regular.assert_called_once_with(
        QUESTION,
        HISTORY,
        settings,
        usage,
        function_ids=[SEED],
        functions_consulted=routed,
        mode_used="local",
    )


@pytest.mark.parametrize(
    ("mode", "weight", "expected_mode"),
    [("auto", None, "global"), ("auto", 0.2, "hybrid"), ("auto", 0.9, "local")],
)
def test_disruption_respects_auto_mode(monkeypatch, mode, weight, expected_mode):
    routed = [] if weight is None else [{"id": SEED, "weight": weight}]
    trace = Mock(return_value=("Cited impact", []))
    regular = Mock(return_value={"answer_md": "Hybrid answer", "mode_used": "hybrid"})
    pool = Mock(connection=Mock(return_value=nullcontext(Mock())))
    graph = Mock()
    graph.query.return_value.result_set = []
    monkeypatch.setattr(answer, "_route_functions", lambda *args: routed)
    monkeypatch.setattr(answer, "get_pool", lambda: pool)
    monkeypatch.setattr(answer, "_function_entity_ids", lambda conn, ids: [SEED])
    monkeypatch.setattr(answer, "connect_graph", lambda cfg: graph)
    monkeypatch.setattr(answer, "trace_impact", trace)
    monkeypatch.setattr(answer, "_local_answer", regular)

    settings, usage = Settings(), {}
    result = answer.answer_question(QUESTION, mode, HISTORY, settings, usage)
    assert result["mode_used"] == expected_mode
    if expected_mode == "hybrid":
        trace.assert_not_called()
        regular.assert_called_once_with(
            QUESTION,
            HISTORY,
            settings,
            usage,
            function_ids=[SEED],
            functions_consulted=routed,
            mode_used="hybrid",
            with_company_report=True,
        )
    else:
        trace.assert_called_once()
        assert result["answer_md"] == "Cited impact"
        assert result["functions_consulted"] == routed

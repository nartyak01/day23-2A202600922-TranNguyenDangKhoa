"""Offline graph integration tests (no LLM API key required).

Uses mocked LLM responses to verify graph wiring and scenario flows end-to-end.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("langgraph")

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.scenarios import load_scenarios
from langgraph_agent_lab.state import initial_state


def _mock_llm_for_query(query: str) -> MagicMock:
    """Return a mock LLM that classifies/answers based on query semantics."""
    q = query.lower()
    if any(w in q for w in ("refund", "delete", "cancel")):
        route = "risky"
    elif any(w in q for w in ("order", "lookup", "status", "tracking")):
        route = "tool"
    elif any(w in q for w in ("fix it", "help me", "can you")) and len(q.split()) <= 4:
        route = "missing_info"
    elif any(w in q for w in ("timeout", "failure", "error", "crash", "unavailable")):
        route = "error"
    else:
        route = "simple"

    classify_result = MagicMock()
    classify_result.route = route
    classify_result.risk_level = "high" if route == "risky" else "low"
    classify_result.reasoning = "mock classification"

    answer_response = MagicMock()
    answer_response.content = f"Mock answer for: {query[:60]}"

    llm = MagicMock()
    structured = MagicMock()
    structured.invoke.return_value = classify_result
    llm.with_structured_output.return_value = structured
    llm.invoke.return_value = answer_response
    return llm


def _make_get_llm_mock(query: str):
    def get_llm_side_effect(*_args, **_kwargs):
        return _mock_llm_for_query(query)

    return get_llm_side_effect


@pytest.mark.parametrize("scenario_id", ["S01_simple", "S02_tool", "S03_missing", "S04_risky", "S05_error", "S06_delete", "S07_dead_letter"])
def test_offline_scenario_flow(scenario_id: str) -> None:
    scenarios = {s.id: s for s in load_scenarios("data/sample/scenarios.jsonl")}
    scenario = scenarios[scenario_id]

    with patch("langgraph_agent_lab.nodes.get_llm", side_effect=_make_get_llm_mock(scenario.query)):
        graph = build_graph(checkpointer=build_checkpointer("memory"))
        state = initial_state(scenario)
        result = graph.invoke(state, config={"configurable": {"thread_id": state["thread_id"]}})

    assert result["route"] == scenario.expected_route.value
    assert result.get("final_answer") or result.get("pending_question")
    finalize_events = [e for e in result.get("events", []) if e.get("node") == "finalize"]
    assert finalize_events, f"{scenario_id} did not reach finalize"

    if scenario.requires_approval:
        approval = result.get("approval", {})
        assert isinstance(approval, dict) and "approved" in approval


def test_offline_all_routes_terminate() -> None:
    graph = build_graph(checkpointer=build_checkpointer("memory"))
    for scenario in load_scenarios("data/sample/scenarios.jsonl"):
        with patch(
            "langgraph_agent_lab.nodes.get_llm",
            side_effect=_make_get_llm_mock(scenario.query),
        ):
            state = initial_state(scenario)
            result = graph.invoke(state, config={"configurable": {"thread_id": state["thread_id"]}})
        events = [e.get("node") for e in result.get("events", [])]
        assert "finalize" in events

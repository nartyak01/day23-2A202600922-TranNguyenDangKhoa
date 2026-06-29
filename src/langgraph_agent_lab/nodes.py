"""Node functions for the LangGraph workflow.

Each function receives AgentState and returns a partial state update dict.
Do NOT mutate input state — return new values only.

LLM REQUIREMENT:
- classify_node MUST use a real LLM call (structured output for intent classification)
- answer_node MUST use a real LLM call (grounded response generation)
- evaluate_node SHOULD use LLM-as-judge (bonus points; heuristic acceptable for base score)
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

from .llm import get_llm
from .state import AgentState, make_event


class ClassificationResult(BaseModel):
    route: str = Field(description="One of: simple, tool, missing_info, risky, error")
    risk_level: str = Field(description="high for risky routes, low otherwise")
    reasoning: str = ""


# ─── EXAMPLE: working node (provided for reference) ──────────────────
def intake_node(state: AgentState) -> dict:
    """Normalize raw query. This node is provided as a working example."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using an LLM."""
    llm = get_llm()
    structured_llm = llm.with_structured_output(ClassificationResult)

    prompt = f"""Classify this support ticket query into exactly one route.
Priority (highest first): risky > tool > missing_info > error > simple

Routes:
- risky: actions with side effects (refund, delete account, send email, cancel subscription)
- tool: information lookups (order status, tracking, search queries)
- missing_info: vague or incomplete queries lacking actionable context
- error: system failures (timeout, crash, service unavailable, processing failure)
- simple: general questions answerable without tools or risky actions

Query: {state.get("query", "")}"""

    result: ClassificationResult = structured_llm.invoke(prompt)
    route = result.route.strip().lower()
    valid_routes = {"simple", "tool", "missing_info", "risky", "error"}
    if route not in valid_routes:
        route = "simple"

    risk_level = "high" if route == "risky" else result.risk_level or "low"

    return {
        "route": route,
        "risk_level": risk_level,
        "events": [make_event("classify", "completed", f"route={route}")],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a mock tool call with transient failure simulation."""
    attempt = state.get("attempt", 0)
    route = state.get("route", "")

    if route == "error" and attempt < 2:
        result = "ERROR: transient timeout while calling external API"
    else:
        query = state.get("query", "")[:50]
        result = f"SUCCESS: mock tool result for '{query}'"

    return {
        "tool_results": [result],
        "events": [make_event("tool", "completed", result[:60])],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the retry-loop gate."""
    tool_results = state.get("tool_results", [])
    latest = tool_results[-1] if tool_results else ""
    evaluation_result = "needs_retry" if "ERROR" in latest.upper() else "success"

    return {
        "evaluation_result": evaluation_result,
        "events": [make_event("evaluate", "completed", f"result={evaluation_result}")],
    }


def answer_node(state: AgentState) -> dict:
    """Generate a final response using an LLM."""
    llm = get_llm()
    query = state.get("query", "")
    tool_results = state.get("tool_results", [])
    approval = state.get("approval")

    context_parts = [f"User query: {query}"]
    if tool_results:
        context_parts.append(f"Tool results: {tool_results[-1]}")
    if approval:
        context_parts.append(f"Approval decision: {approval}")
    if state.get("proposed_action"):
        context_parts.append(f"Proposed action: {state['proposed_action']}")

    prompt = f"""You are a helpful support agent. Generate a concise, grounded response.
Use only the context provided. Do not invent facts.

{chr(10).join(context_parts)}"""

    response = llm.invoke(prompt)
    final_answer = response.content if hasattr(response, "content") else str(response)

    return {
        "final_answer": final_answer,
        "events": [make_event("answer", "completed", "response generated")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information instead of hallucinating."""
    query = state.get("query", "")
    question = (
        f"Your request '{query}' is unclear. "
        "Could you provide more details about what you need help with?"
    )
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "asked for clarification")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for human approval."""
    query = state.get("query", "")
    action = f"Proposed risky action requiring approval: {query}"
    return {
        "proposed_action": action,
        "events": [make_event("risky_action", "completed", action[:60])],
    }


def approval_node(state: AgentState) -> dict:
    """Human-in-the-loop approval step."""
    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt

        decision = interrupt(
            {
                "proposed_action": state.get("proposed_action", ""),
                "query": state.get("query", ""),
            }
        )
        approved = bool(decision.get("approved", False)) if isinstance(decision, dict) else False
        reviewer = (
            decision.get("reviewer", "human-reviewer")
            if isinstance(decision, dict)
            else "human-reviewer"
        )
        comment = decision.get("comment", "") if isinstance(decision, dict) else ""
    else:
        approved = True
        reviewer = "mock-reviewer"
        comment = "auto-approved for offline/CI runs"

    return {
        "approval": {"approved": approved, "reviewer": reviewer, "comment": comment},
        "events": [make_event("approval", "completed", f"approved={approved}")],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt."""
    attempt = state.get("attempt", 0) + 1
    return {
        "attempt": attempt,
        "errors": [f"Retry attempt {attempt} failed due to transient error"],
        "events": [make_event("retry", "attempted", f"attempt={attempt}")],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Handle unresolvable failures after max retries exceeded."""
    attempt = state.get("attempt", 0)
    max_attempts = state.get("max_attempts", 3)
    message = (
        f"Request could not be completed after {attempt} attempt(s) "
        f"(max {max_attempts}). Escalating to dead letter queue."
    )
    return {
        "final_answer": message,
        "events": [make_event("dead_letter", "failed", message[:60])],
    }


def finalize_node(state: AgentState) -> dict:
    """Emit a final audit event. All routes must pass through here before END."""
    return {
        "events": [make_event("finalize", "completed", "workflow finished")],
    }

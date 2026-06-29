"""Report generation helper."""

from __future__ import annotations

from pathlib import Path

from .metrics import MetricsReport


def render_report(metrics: MetricsReport) -> str:
    """Render a complete lab report from metrics data."""
    lines = [
        "# Day 08 Lab Report",
        "",
        "## 1. Team / student",
        "",
        "- Name: Tran Nguyen Dang Khoa",
        "- Repo/commit: day23-2A202600922-TranNguyenDangKhoa",
        "- Date: 2026-06-29",
        "",
        "## 2. Architecture",
        "",
        "LangGraph StateGraph with 11 nodes wired via fixed and conditional edges:",
        "",
        "```text",
        "START → intake → classify → [route_after_classify]",
        "  simple       → answer → finalize → END",
        "  tool         → tool → evaluate → answer/retry loop → finalize → END",
        "  missing_info → clarify → finalize → END",
        "  risky        → risky_action → approval → tool → evaluate → answer → finalize → END",
        "  error        → retry → tool → evaluate → retry loop / dead_letter → finalize → END",
        "```",
        "",
        "Key nodes: classify (LLM structured output), answer (LLM grounded),",
        "evaluate (retry gate), approval (HITL), dead_letter (max retry exhaustion).",
        "",
        "## 3. State schema",
        "",
        "| Field | Reducer | Why |",
        "|---|---|---|",
        "| messages | append | audit conversation |",
        "| tool_results | append | accumulate tool outputs |",
        "| errors | append | track retry failures |",
        "| events | append | audit trail for grading |",
        "| route | overwrite | current classification |",
        "| evaluation_result | overwrite | retry gate |",
        "| approval | overwrite | HITL decision |",
        "",
        "## 4. Scenario results",
        "",
        f"- Total scenarios: {metrics.total_scenarios}",
        f"- Success rate: {metrics.success_rate:.1%}",
        f"- Avg nodes visited: {metrics.avg_nodes_visited:.1f}",
        f"- Total retries: {metrics.total_retries}",
        f"- Total interrupts: {metrics.total_interrupts}",
        "",
        "| Scenario | Expected | Actual | Success | Retries | Interrupts |",
        "|---|---|---|---:|---:|---:|",
    ]

    for item in metrics.scenario_metrics:
        lines.append(
            f"| {item.scenario_id} | {item.expected_route} | {item.actual_route} "
            f"| {'yes' if item.success else 'no'} | {item.retry_count} | {item.interrupt_count} |"
        )

    lines.extend(
        [
            "",
            "## 5. Failure analysis",
            "",
            "1. **Retry / tool failure**: transient ERROR results trigger evaluate → retry loop;",
            "   bounded by max_attempts, then dead_letter.",
            "2. **Risky action without approval**: risky route requires approval node before tool execution.",
            "",
            "## 6. Persistence / recovery evidence",
            "",
            "MemorySaver checkpointer with per-scenario thread_id.",
            "SQLite checkpointer implemented with WAL mode in persistence.py.",
            "",
            "## 7. Extension work",
            "",
            "SQLite persistence, LANGGRAPH_INTERRUPT support in approval_node.",
            "",
            "## 8. Improvement plan",
            "",
            "Add Streamlit HITL UI, LLM-as-judge in evaluate_node, crash-recovery demo.",
            "",
        ]
    )

    return "\n".join(lines)


def write_report(metrics: MetricsReport, output_path: str | Path) -> None:
    """Write the rendered report to a file."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(metrics), encoding="utf-8")

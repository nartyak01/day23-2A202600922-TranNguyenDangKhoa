# Day 08 Lab Report

## 1. Team / student

- Name: Tran Nguyen Dang Khoa
- Repo/commit: day23-2A202600922-TranNguyenDangKhoa
- Date: 2026-06-29

## 2. Architecture

LangGraph StateGraph with 11 nodes wired via fixed and conditional edges:

```text
START → intake → classify → [route_after_classify]
  simple       → answer → finalize → END
  tool         → tool → evaluate → answer/retry loop → finalize → END
  missing_info → clarify → finalize → END
  risky        → risky_action → approval → tool → evaluate → answer → finalize → END
  error        → retry → tool → evaluate → retry loop / dead_letter → finalize → END
```

Key nodes: classify (LLM structured output), answer (LLM grounded),
evaluate (retry gate), approval (HITL), dead_letter (max retry exhaustion).

## 3. State schema

| Field | Reducer | Why |
|---|---|---|
| messages | append | audit conversation |
| tool_results | append | accumulate tool outputs |
| errors | append | track retry failures |
| events | append | audit trail for grading |
| route | overwrite | current classification |
| evaluation_result | overwrite | retry gate |
| approval | overwrite | HITL decision |

## 4. Scenario results

- Total scenarios: 7
- Success rate: 100.0%
- Avg nodes visited: 6.4
- Total retries: 3
- Total interrupts: 2

| Scenario | Expected | Actual | Success | Retries | Interrupts |
|---|---|---|---:|---:|---:|
| S01_simple | simple | simple | yes | 0 | 0 |
| S02_tool | tool | tool | yes | 0 | 0 |
| S03_missing | missing_info | missing_info | yes | 0 | 0 |
| S04_risky | risky | risky | yes | 0 | 1 |
| S05_error | error | error | yes | 2 | 0 |
| S06_delete | risky | risky | yes | 0 | 1 |
| S07_dead_letter | error | error | yes | 1 | 0 |

## 5. Failure analysis

1. **Retry / tool failure**: transient ERROR results trigger evaluate → retry loop;
   bounded by max_attempts, then dead_letter.
2. **Risky action without approval**: risky route requires approval node before tool execution.

## 6. Persistence / recovery evidence

MemorySaver checkpointer with per-scenario thread_id.
SQLite checkpointer implemented with WAL mode in persistence.py.

## 7. Extension work

SQLite persistence, LANGGRAPH_INTERRUPT support in approval_node.

## 8. Improvement plan

Add Streamlit HITL UI, LLM-as-judge in evaluate_node, crash-recovery demo.

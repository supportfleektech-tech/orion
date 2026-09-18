# Agent Runtime

## State machine

```text
QUEUED
  ↓
INTENT
  ↓
PLAN
  ↓
RETRIEVE
  ↓
EXECUTE ←──── retry (bounded)
  ↓
VERIFY
  ├─ fail → REVISE → EXECUTE
  └─ pass → FINALIZE
                 ↓
              MEMORY
                 ↓
               DONE
```

## Planning

A plan is an implementation detail, not a promise. Store structured steps:

```json
{
  "goal": "produce report",
  "steps": [
    {"id":"s1","action":"retrieve_sources","status":"queued"},
    {"id":"s2","action":"analyze","depends_on":["s1"],"status":"queued"},
    {"id":"s3","action":"write_report","depends_on":["s2"],"status":"queued"},
    {"id":"s4","action":"verify","depends_on":["s3"],"status":"queued"}
  ],
  "budget": {"tool_calls": 20, "minutes": 10}
}
```

## Verification

Every non-trivial task should declare acceptance criteria before execution.

Examples:

- code: tests pass + lint passes;
- research: minimum source count + freshness + contradiction check;
- data: schema validation + row-count checks;
- browser: expected page state + screenshot/DOM evidence;
- document: required sections + no unresolved placeholders.

## Multi-agent pattern

Use specialized workers only when specialization improves reliability:

- Planner;
- Researcher;
- Coder;
- Data Analyst;
- Writer;
- Browser Operator;
- Critic/Verifier.

The parent orchestrator owns the final result and policy enforcement.

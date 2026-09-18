# Observability

## Metrics

Track:

- request latency p50/p95/p99;
- model latency;
- tokens in/out;
- model/provider success rate;
- tool success rate;
- retries;
- verification pass rate;
- memory retrieval hit rate;
- cloud escalation rate;
- task completion rate;
- user correction rate.

## Trace shape

```json
{
  "trace_id":"...",
  "task_id":"...",
  "events":[
    {"type":"model.started","model":"qwen3:4b"},
    {"type":"retrieval.completed","count":6},
    {"type":"tool.completed","tool":"calculate","ok":true},
    {"type":"verification.passed"}
  ]
}
```

## Privacy-safe logging

Store metadata by default. Raw prompts/results should be optional and scoped. Provide a local-only logging mode.

## Evaluation dashboard

The UI should show regression scores by capability:

- chat;
- RAG;
- tool selection;
- coding;
- research;
- planning;
- safety/policy compliance.

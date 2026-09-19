# Tools

## Registry

`ToolDefinition(name, description, parameters, risk, requires_confirmation, handler, category, tags, enabled)`

`parameters` is JSON Schema and is passed straight to the model as an OpenAI function definition.
`registry.openai_schemas()` filters out anything the policy engine currently disallows, so the model
cannot be tempted by capabilities it may not use.

## Built-in tools

| Tool | Category | Risk | Notes |
|---|---|---|---|
| `calculate` | utility | low | AST allowlist, bounded exponent |
| `current_time` | utility | low | UTC |
| `list_files` | files | low | Confined to `KNOWLEDGE_DIR` |
| `read_file` | files | low | Confined, 20k char cap |
| `write_file` | files | high | Approval required |
| `knowledge_search` | knowledge | low | RAG over ingested documents |
| `memory_search` | memory | low | Long-term memory lookup |
| `memory_write` | memory | medium | Stores durable facts |
| `web_search` | web | medium | SearXNG, requires `ENABLE_WEB_SEARCH` |
| `fetch_page` | network | medium | Readable text extraction |
| `http_request` | network | high | Approval + allowlist |
| `shell_exec` | shell | destructive | Approval, denylist, timeout, confined cwd |
| `browse_page` | browser | high | Approval, Playwright |

## Adding a tool

```python
from app.tools.registry import ToolDefinition, registry

async def my_tool(args: dict) -> dict:
    return {"echo": args["text"]}

registry.register(ToolDefinition(
    name="my_tool",
    description="Echo text back. Used for demonstration.",
    parameters={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
    risk="low",
    category="utility",
    handler=my_tool,
))
```

Register it from `app/tools/builtin.py` (or any module imported by `app.main`). Choose the risk tier
honestly: anything that writes, spends, sends or deletes is `high` or `destructive`.

Handlers must be `async`, accept a single dict and return a JSON-serialisable dict. Raise exceptions
for failures — the runtime catches them, records them and reports them to the model.

## MCP

ORION's tool contract is intentionally MCP-shaped (name, description, JSON Schema, handler), so a
client adapter can map external MCP servers into the registry. Federation is planned for v1.2; see
`ROADMAP.md`.

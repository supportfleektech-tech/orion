# MCP (Model Context Protocol)

ORION speaks MCP in both directions.

* **As a server**, it exposes a small read-only slice of itself so other
  assistants and editors can search your memory and knowledge.
* **As a client**, it connects out to other people's MCP servers and folds
  their tools into its own registry, so the agent can use them mid-conversation.

Both sides need the SDK, which is optional:

```bash
pip install -r backend/requirements-optional.txt
```

Nothing breaks without it. The MCP page reports that the SDK is missing, and
the rest of ORION carries on.

---

## ORION as a client

### Adding a server

**MCP servers** in the sidebar → **Add server**. Two transports:

| Transport | Use for | You provide |
|---|---|---|
| `stdio` | A local process, the common case | A command, e.g. `npx -y @modelcontextprotocol/server-filesystem /home/me/docs` |
| `http` | A remote streamable-HTTP endpoint | A URL |

On save, ORION connects, lists the server's tools, and caches them. The API
equivalent:

```bash
curl -X POST localhost:8000/v1/mcp/servers -H 'content-type: application/json' -d '{
  "name": "docs",
  "transport": "stdio",
  "command": "npx -y @modelcontextprotocol/server-filesystem /home/me/docs",
  "risk": "medium",
  "requires_confirmation": true
}'
```

### Namespacing

A tool called `search` on a server called `docs` is registered as
**`docs.search`**. This means:

* A remote server can never shadow a builtin. If it offers a `calculate`
  tool, that becomes `docs.calculate`; ORION's own `calculate` is untouched.
* The model, the audit log and the tool history all show where a capability
  came from.

### Policy

Discovered tools are **not** trusted to describe their own danger. Every tool
from a server inherits the `risk` level you set on that server, and passes
through the same policy gate as builtins:

* `low` — runs freely.
* `medium` / `high` / `destructive` — subject to the usual tier rules.
* `requires_confirmation` — every call queues for approval first.

Set the risk to match the *most* dangerous thing the server can do, not the
average. A filesystem server that can write files is not `low`.

The kill switch stops MCP tools along with everything else.

### Failure behaviour

External servers are flaky by nature, so nothing here can break a conversation:

| Situation | What happens |
|---|---|
| SDK not installed | Tools are not registered; the page explains the fix |
| Server unreachable | Status goes `error` with the message; the tool returns a failed result |
| Call exceeds 60s | Returns a timeout error to the model, which can try something else |
| Server row deleted mid-call | The handler reports that the server was removed |
| Remote tool raises | The error text is returned as a tool result, not an exception |

### Startup

Boot registers tools from the **cached** discovery results — it never connects
to external processes. Starting ORION therefore does not wait on a slow or
dead MCP server. Press **Refresh all** (or `POST /v1/mcp/refresh`) to
re-discover when a server's tool list changes.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/mcp/servers` | List servers, their tools and status |
| `POST` | `/v1/mcp/servers` | Register a server and discover its tools |
| `PATCH` | `/v1/mcp/servers/{id}` | Edit, enable or disable |
| `DELETE` | `/v1/mcp/servers/{id}` | Remove the server and unregister its tools |
| `POST` | `/v1/mcp/servers/{id}/refresh` | Reconnect and re-discover |
| `POST` | `/v1/mcp/refresh` | Refresh every enabled server |

Environment values for `stdio` servers are stored per server. The API returns
only the **key names**, never the values, since they are usually credentials.

---

## ORION as a server

```bash
python -m app.tools.mcp_server
```

Speaks stdio, so point any MCP client at that command. It exposes three
deliberately harmless tools:

| Tool | Does |
|---|---|
| `ping` | Health check |
| `search_memory` | Read-only memory search |
| `search_knowledge` | Read-only knowledge-base search |

Anything that writes, sends, spends or deletes is **not** here by design.
Those capabilities stay behind the HTTP API's policy gate and approval queue,
where they can be audited and revoked.

---

## SDK versions

The SDK renamed several things in 2.0 (`FastMCP` → `MCPServer`,
`inputSchema` → `input_schema`, `streamablehttp_client` →
`streamable_http_client`). ORION supports both majors, so `mcp>=1.10,<3` is
safe to install either way.

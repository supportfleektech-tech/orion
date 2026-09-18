# Tools + MCP

## Tool gateway

All tools, including MCP tools, must enter through the same gateway:

```text
LLM -> ToolPolicy -> CapabilityCheck -> ApprovalGate -> ToolRunner -> ResultValidator -> Audit
```

A tool definition contains:

- name;
- description;
- JSON schema;
- capability scope;
- risk tier;
- idempotency classification;
- timeout;
- retry policy;
- allowed network destinations;
- approval requirement.

## MCP integration

MCP gives ORION a standard discovery and invocation layer for tools/resources/prompts. The architecture should support:

- local stdio servers for private desktop tools;
- Streamable HTTP for remote servers;
- authenticated servers;
- per-tool allow/deny lists;
- server health;
- server provenance;
- schema caching;
- tool annotations such as read-only/destructive hints.

Do not let a third-party MCP server bypass ORION's own permission model.

## High-value internal tools

### Knowledge
`search_knowledge`, `open_document`, `list_sources`

### Files
`list_files`, `read_file`, `write_file` (approval), `move_file` (approval)

### Code
`git_status`, `git_diff`, `run_tests`, `run_linter`, `apply_patch` (sandbox)

### Web
`web_search`, `open_url`, `extract_page`, `download_file`

### Browser
`browser_open`, `browser_click`, `browser_type`, `browser_screenshot`

### Data
`sql_read`, `python_sandbox`, `csv_analyze`

### Automation
`schedule_task`, `run_workflow`, `cancel_task`

## Shell policy

Never expose unrestricted shell as a default LLM tool. Use an allowlisted command runner inside a sandbox with:

- working-directory jail;
- network isolation;
- CPU/RAM/time quotas;
- output limits;
- explicit command allowlist;
- read-only mode when possible.

# Security Architecture

## Threats

Assume prompts, web pages, documents, MCP servers and API responses can contain malicious instructions.

Major risks:

- prompt injection;
- data exfiltration;
- tool abuse;
- secret leakage;
- cross-user data leakage;
- browser session theft;
- SSRF;
- path traversal;
- unsafe code execution;
- accidental destructive actions.

## Defenses

### Prompt injection
Retrieved content is untrusted data. Never concatenate retrieved text into system instructions. Use explicit delimiters and provenance metadata.

### Tool permissions
The model requests capabilities; policy grants them. The model cannot grant itself access.

### Network policy
Outbound network requests should go through an allowlisted network tool. Block loopback/private IPs for arbitrary URL fetchers to reduce SSRF risk.

### Secrets
Do not index secrets. Redact common key/token formats from logs. Never include connector secrets in model context.

### Code execution
Use a sandbox. Start with disabled shell execution (`ALLOW_SHELL_TOOL=false`).

### Browser isolation
Use separate profiles per connector/account. Never expose cookies to the model as raw text.

### Approvals
Anything involving external publication, payments, account modification, destructive changes, or credentials defaults to approval.

### Audit
Log who/what/when/provider/tool/risk/result, but not raw credentials or full sensitive payloads.

## Kill switches

The UI and environment should support:

- disable cloud;
- disable web;
- disable browser;
- disable writes;
- disable all tools;
- local-only emergency mode.

# Integrations

## Connector architecture

Every connector implements:

```python
class Connector:
    provider: str
    async def capabilities(self) -> list[str]: ...
    async def health(self) -> dict: ...
    async def execute(self, operation: str, payload: dict) -> dict: ...
```

Separate `read:*` and `write:*` capability names.

## Priority integrations

### GitHub/GitLab
Read repositories/issues/PRs; create branches/PRs only with approval until proven reliable.

### Mail
Read/search/draft by default. Sending should require approval initially.

### Calendar
Read schedule, propose events, create events after approval.

### Messaging
Read/triage where permitted. Send messages as a distinct write capability.

### Cloud drives
Index selected folders; maintain source permissions and deletion synchronization.

### Social media
Use official APIs and official OAuth when available. Do not bypass platform controls or automate against terms. Store drafts separately from published posts.

### Generic REST/OpenAPI
Import an OpenAPI schema, convert safe endpoints to tools, classify writes as approval-required.

## Credentials

Never store API keys in prompts or vector memory. Use environment variables for development and an encrypted OS secret store for desktop production.

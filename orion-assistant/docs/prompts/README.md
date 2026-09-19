# Prompts

The **live** system prompt used by the agent runtime is
[`backend/app/prompts/system.md`](../../backend/app/prompts/system.md). Edit that file to change
ORION's behaviour — it is read at import time, so a restart applies your changes. No code edit
is needed.

The other files in this directory (`planner.md`, `executor.md`, `verifier.md`, `memory.md`) are
**design references** for the multi-agent split planned in v1.2. They are not loaded at runtime
today; the v1 runtime uses a single system prompt plus a tool loop. See `ROADMAP.md`.

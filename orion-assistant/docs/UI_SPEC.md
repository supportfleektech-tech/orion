# UI / UX Specification

## Visual direction

A premium, minimal, dark control room:

- dark graphite background;
- subtle blue/indigo accent;
- thin borders;
- compact typography;
- dense but breathable information architecture;
- responsive sidebar;
- command palette;
- keyboard-first navigation;
- real-time agent trace.

Avoid excessive glassmorphism and decorative animation. Motion should communicate state.

## Global shell

```text
┌───────────────┬─────────────────────────────────────────────┐
│ ORION         │ Search / Command      Mode   Voice Alerts  │
│               ├─────────────────────────────────────────────┤
│ Command       │                                             │
│ Conversations │                Main workspace               │
│ Tasks         │                                             │
│ Memory        │                                             │
│ Knowledge     │                                             │
│ Tools         │                                             │
│ MCP           │                                             │
│ Automations   │                                             │
│ Connectors    │                                             │
│ Evaluation    │                                             │
│ Security      │                                             │
│ Settings      │                                             │
│               │                                             │
│ ● Runtime     │                                             │
└───────────────┴─────────────────────────────────────────────┘
```

## Routes

- `/` Command Center
- `/chat` conversations
- `/chat/:conversationId` conversation detail
- `/tasks` task queue
- `/tasks/:id` task trace
- `/memory` memory explorer
- `/knowledge` document library
- `/knowledge/:id` document detail
- `/tools` tool registry
- `/mcp` MCP servers
- `/automations` scheduled workflows
- `/connectors` integrations
- `/evaluation` quality/regression dashboard
- `/security` permissions, audit, sessions
- `/settings` model/runtime preferences

## Chat workspace

Center: conversation.
Right rail: context, memory hits, tools used, sources, artifacts.
Bottom composer: text, attachment, voice, model mode, autonomy toggle.

## Task workspace

Show:

- goal;
- live step graph;
- current model/provider;
- tool calls;
- retrieved context;
- approvals;
- errors/retries;
- generated artifacts;
- final verification status.

## Memory workspace

Cards/table with:

- memory type;
- content;
- confidence;
- source;
- created/updated;
- scope;
- actions: edit/forget.

## Accessibility

Keyboard focus visible, semantic buttons, reduced motion, readable contrast, mobile breakpoints, screen-reader labels.

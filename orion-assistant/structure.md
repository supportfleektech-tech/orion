                         ┌──────────────────────┐
                         │   React / PWA UI     │
                         └──────────┬───────────┘
                                    │
                              FastAPI API
                                    │
                         ┌──────────▼───────────┐
                         │  ORION ORCHESTRATOR  │
                         └──────────┬───────────┘
                                    │
             ┌──────────────────────┼──────────────────────┐
             │                      │                      │
       Model Router             Memory/RAG             Tool Gateway
             │                      │                      │
      ┌──────┴──────┐        ┌──────▼──────┐       ┌──────▼──────────┐
      │             │        │ PostgreSQL  │       │ Policy / RBAC   │
   Ollama       OpenRouter   │ + pgvector  │       │ Approval Engine │
      │             │        └─────────────┘       └──────┬──────────┘
      │             │                                     │
 local inference   cloud burst                     ┌──────┼─────────────┐
                                                    │      │             │
                                                  MCP   Browser       APIs
                                                  tools  automation    SaaS
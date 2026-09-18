CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New conversation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('system','user','assistant','tool')),
    content TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY,
    kind TEXT NOT NULL,
    key TEXT,
    content TEXT NOT NULL,
    source TEXT,
    confidence REAL NOT NULL DEFAULT 0.5,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS memories_embedding_hnsw
ON memories USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS memories_fts
ON memories USING gin (to_tsvector('simple', content));

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    mime_type TEXT,
    hash TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
ON chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS chunks_fts
ON chunks USING gin (to_tsvector('simple', content));

CREATE TABLE IF NOT EXISTS tool_runs (
    id UUID PRIMARY KEY,
    tool_name TEXT NOT NULL,
    arguments JSONB NOT NULL DEFAULT '{}'::jsonb,
    result JSONB,
    risk TEXT NOT NULL DEFAULT 'low',
    status TEXT NOT NULL DEFAULT 'queued',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id UUID PRIMARY KEY,
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,
    task TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued',
    provider TEXT,
    model TEXT,
    result TEXT,
    trace JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approvals (
    id UUID PRIMARY KEY,
    tool_name TEXT NOT NULL,
    arguments JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS connector_secrets (
    id UUID PRIMARY KEY,
    provider TEXT NOT NULL,
    label TEXT NOT NULL,
    secret_ref TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'system',
    summary TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

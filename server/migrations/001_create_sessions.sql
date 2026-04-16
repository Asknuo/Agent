-- Migration 001: Create sessions table for session persistence (Requirement 3.1)
--
-- Run against your PostgreSQL database:
--   psql -d your_database -f server/migrations/001_create_sessions.sql

CREATE TABLE IF NOT EXISTS sessions (
    id          VARCHAR(64) PRIMARY KEY,
    user_id     VARCHAR(64) NOT NULL,
    tenant_id   VARCHAR(64) NOT NULL DEFAULT 'default',
    messages    JSONB       NOT NULL DEFAULT '[]'::jsonb,
    context     JSONB       NOT NULL DEFAULT '{}'::jsonb,
    status      VARCHAR(20) NOT NULL DEFAULT 'active',
    satisfaction INTEGER     CHECK (satisfaction BETWEEN 1 AND 5),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_sessions_user_id    ON sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_tenant_id  ON sessions (tenant_id);
CREATE INDEX IF NOT EXISTS idx_sessions_status     ON sessions (status);
CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions (updated_at DESC);

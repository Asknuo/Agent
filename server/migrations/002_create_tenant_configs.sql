-- Migration 002: Create tenant_configs table for per-tenant settings (Requirement 13.5)
--
-- Run against your PostgreSQL database:
--   psql -d your_database -f server/migrations/002_create_tenant_configs.sql

CREATE TABLE IF NOT EXISTS tenant_configs (
    tenant_id       VARCHAR(64) PRIMARY KEY,
    rate_limit_rpm  INTEGER     NOT NULL DEFAULT 30,
    knowledge_dir   VARCHAR(256) NOT NULL DEFAULT '',
    custom_prompts  JSONB       NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Runs once on first DB init (PostgreSQL entrypoint-initdb.d)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

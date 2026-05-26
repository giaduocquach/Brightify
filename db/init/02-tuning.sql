-- Optional: PostgreSQL tuning via ALTER SYSTEM (requires pg_reload_conf or restart)
-- Prefer passing -c flags via docker-compose command: instead (see docker-compose.yml §5.5)
ALTER SYSTEM SET shared_buffers = '2GB';
ALTER SYSTEM SET maintenance_work_mem = '1GB';
ALTER SYSTEM SET max_parallel_maintenance_workers = 2;
ALTER SYSTEM SET effective_cache_size = '4GB';
ALTER SYSTEM SET work_mem = '64MB';
ALTER SYSTEM SET max_connections = 50;

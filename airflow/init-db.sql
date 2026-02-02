-- Create airflow database if not exists (PostgreSQL way)
-- SELECT 'CREATE DATABASE airflow_db'
-- WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'airflow_db')\gexec

-- Or simpler approach - just create, ignore error if exists
-- The database might already exist from POSTGRES_DB env variable
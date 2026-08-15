-- Runs once when the PostgreSQL container initialises an empty data directory.
-- Schema objects are created by Alembic, not here: this file only installs extensions
-- that require superuser privileges.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- pg_trgm powers fast ILIKE/similarity search on asset names once the catalog grows.

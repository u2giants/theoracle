-- Extensions required by The Oracle.
-- Run BEFORE Drizzle's generated tables migration so that `vector(1536)` works.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

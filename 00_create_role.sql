-- Create the role the seed dump assigns ownership to (maintdb_dump.sql contains
-- "OWNER TO lukesevenish"), so a FRESH Postgres volume initializes cleanly instead
-- of aborting on a missing role. Mounted ahead of the dump in the compose files.
-- Idempotent and harmless if the role already exists.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lukesevenish') THEN
        CREATE ROLE lukesevenish;
    END IF;
END
$$;

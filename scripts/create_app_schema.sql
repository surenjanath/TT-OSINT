-- Run once as the database ADMIN (e.g. doadmin). Use when "permission denied for schema public".
-- Creates a schema "app" and grants the app user (db) full access so Django can create tables there.
-- Then set env var PG_SCHEMA=app in your app so Django uses this schema instead of public.

-- Create the schema (admin only).
CREATE SCHEMA IF NOT EXISTS app;

-- Grant the app user access (replace 'db' with your app's DB username if different).
GRANT ALL ON SCHEMA app TO db;
GRANT CREATE ON SCHEMA app TO db;

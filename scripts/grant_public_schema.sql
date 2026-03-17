-- Fix: permission denied for schema public (PostgreSQL 15+ only; not needed for PG 14)
--
-- IMPORTANT: Connect as the database ADMIN user (doadmin), NOT as the app user (db).
-- In DigitalOcean: Databases → your cluster → Connection details → use user "doadmin"
-- and that user's password. The "db" user cannot grant itself these privileges.
--
-- Run each line separately in psql (or both; replace 'db' if your app user has another name):
GRANT ALL ON SCHEMA public TO db;
GRANT CREATE ON SCHEMA public TO db;

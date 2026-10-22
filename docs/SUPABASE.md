# Supabase PostgreSQL deployment

## Target architecture and backend recommendation

Use **Render to run the existing Python/Flask Docker image**, with Supabase PostgreSQL for account approvals, assessments, job state, processing results and audit history. Render supports Flask services, Docker deployment and separate background workers. This preserves the tested OpenCV/PyMuPDF/Tesseract pipeline.

Start with one service process and its existing worker, backed by a persistent private disk for scans. Supabase private Storage and an independently supervised worker are the next step before separating services or adding replicas. Database support alone does not make the file pipeline stateless: do not deploy this version with ephemeral-only storage, multiple replicas or a worker without the same files.

The hosted Supabase schema/project must be explicitly provisioned. At the time this change was prepared, organization creation awaited dashboard sign-in; no unrelated project was modified. The repository does not provision a Render service, incur a backend hosting charge or create a live URL.

## Database setup

1. Create the dedicated MC-Killer Supabase organization/project in the chosen region.
2. Inspect existing tables and apply the initial SQL in `supabase/migrations/` once with an administrative migration connection. The migration creates a **private `mc_killer` schema**, not tables in `public`.
3. The migration creates a `mc_killer_backend` NOLOGIN role with table access limited to the application's needs. It has SELECT/INSERT/UPDATE on users/jobs and SELECT/INSERT on the audit table; no schema creation or audit update/delete privileges are granted. RLS is enabled for all three tables and grants access only to this backend role. Do not add `mc_killer` to the exposed Data API schemas or grant it to `anon`/`authenticated`.
4. Using the database administration interface, create a dedicated login role with a strong password and grant it membership in `mc_killer_backend`. Store the password in your hosting secret manager. Use that login for the backend. Do not run the app with the database-owner/postgres credential.
5. Get the connection hostname/port from the Supabase dashboard's Connect panel. Use direct Postgres for an IPv6-capable persistent backend, or the Supavisor **session pooler** for an IPv4 backend. Use your dedicated role's username in that connection string. Keep the full connection string server-side as `MCK_DATABASE_URL`; it is not a publishable Supabase API key.
6. Keep `MCK_DB_SSLMODE=verify-full`. `MCK_DB_SSLROOTCERT=system` uses libpq's system root trust; use the dashboard-provided trusted CA file path if your environment requires it. In hosted deployments set `MCK_REQUIRE_POSTGRES=1` so missing credentials cannot silently create a local SQLite database.
7. Start the backend with its private persistent file directory and the existing Google OAuth configuration. Confirm `/healthz`, teacher authorization, assessment creation, review and exports before live use.

The app uses a bounded psycopg pool (max 8 connections per process), parameterized queries, per-transaction private search paths, row locks for concurrent reviews, and SKIP LOCKED job claiming. Prepared statements are disabled for pooler compatibility. The app checks for the migrated schema at startup rather than executing privileged DDL through the runtime login.

## Authentication and access boundaries

Google school sign-in remains the existing server-side OIDC integration, including its approved-teacher list. Supabase Auth is not required by this design. Teachers have application sessions and do not receive a database connection or privileged Supabase key. The Python service enforces assessment ownership. Database RLS permits the trusted backend role; it does not attempt to use `auth.uid()` for non-Supabase sessions.

Run advisors after applying the migration and test that anonymous/authenticated Data API clients cannot see the private tables. Store service/database credentials only on the backend. No passwords, student information or database URLs belong in Git or browser code.

## Development, migration and tests

Leaving `MCK_DATABASE_URL` unset preserves the local SQLite workflow and migrates old SQLite account columns in place. Switching database backends does **not** copy old users, assessments, audit history or scans. Export/validate any live data and arrange a separate migration before switching an existing deployment. This pilot has no automatic SQLite-to-Postgres data importer.

The PostgreSQL integration test is enabled only with `MCK_TEST_DATABASE_URL`. It **drops the application's schema**, so it must point only to a disposable database. GitHub Actions starts a fresh PostgreSQL 17 container and exercises app uploads, JSONB results, review recalculation, finalization and restricted audit/schema access using a least-privilege runtime login. Local SQLite tests remain independent. Existing hosted databases must never be used as test fixtures.

References: [Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres), [Render Flask deployment](https://render.com/docs/deploy-flask), [Render background workers](https://render.com/docs/background-workers).

# Continue from another device

Snapshot: 22 October 2026 (Asia/Hong_Kong).

## Source and deployments
- Repository: https://github.com/killerscar-67/MC-Killer
- PR #1 contains the initial teacher pilot and today's fixes; main is the continuation branch after merge.
- Public website: https://mc-killer.pages.dev
- Cloudflare account: existing connected account; Pages project `mc-killer`, Direct Upload. Gateway source is in `cloudflare/pages/`. It is not automatically deployed from Git.
- Northflank service: https://app.northflank.com/t/hw2/project/default/services/mc-killer
- Northflank currently builds `codex/teacher-web-pilot` automatically. After merge, switch its build/deployment branch to `main` before further development. Branch change can restart the service and lose ephemeral image files.
- Supabase: https://supabase.com/dashboard/project/tdynkamfmbktqzebvrav (AC organization, MC-killer project, Singapore).
- Applied migration: `20261022090442_mc_killer_initial.sql`; recorded in `supabase_migrations.schema_migrations`. Do not reapply blindly.

## Authentication and configuration
School domain: `deliahw2.edu.hk`. Google callback:
`https://mc-killer.pages.dev/auth/google/callback`

Google OAuth, session secret and database connection credentials are stored in Northflank, never this repository. Keep the session secret stable. Database uses Supabase session pooler port 5432 because direct IPv6 was unreachable. TLS uses `verify-full` and a mounted CA certificate; the environment's actual mount path must match `MCK_DB_SSLROOTCERT`.

Teacher approval in the Northflank running container:
```sh
python -m mcmark.web authorize-teacher --data /data --email teacher@deliahw2.edu.hk
python -m mcmark.web revoke-teacher --data /data --email teacher@deliahw2.edu.hk
```
Only approve teachers. Google consent currently says WiserLife; create an independent MC-Killer OAuth configuration to avoid confusion without changing the other app. Confirm dedicated least-privilege database login; owner login was used during troubleshooting and should be replaced before live use.

## Highest-priority remaining work
1. Implement private persistent object storage for originals/evidence. PostgreSQL holds results/audits, but `/data` files are ephemeral and are lost on restarts/redeployments.
2. Benchmark OCR against teacher-verified anonymized field crops, separately for numbers, English and Traditional Chinese handwriting. Compare PaddleOCR PP-OCRv5 and current Tesseract; cloud OCR requires an approved data flow and credentials. Do not infer better accuracy without measurements.
3. Keep review flags for ambiguous marks/metadata. Current OCR threshold: minimum word confidence below 70; blank, error and format failures also flag review. Raw text and evidence retained.
4. Add roster reconciliation, teacher approval UI, backup/retention operations and capacity benchmarks. Current service has only 512 MB RAM.

## Local verification
```sh
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/python -m unittest discover -s tests -v
```
PostgreSQL integration uses a disposable DB only: see SUPABASE.md. Never use hosted student data as a test fixture. Real scans, secrets, local output and databases are intentionally excluded from source control.

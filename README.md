# MC-Killer

A teacher workspace for scanning, marking and reviewing multiple-choice answer sheets. This first release supports the Delia 100-question A–D sheet, using only the questions in each assessment's answer key.

## Current pilot (22 October 2026)

- Website: https://mc-killer.pages.dev — Cloudflare Pages gateway to the Python service on Northflank.
- Northflank: HW2 / Default / MC-Killer, US Central, free `nf-compute-20` (0.2 shared vCPU, 512 MB RAM, 2 GB ephemeral storage).
- Database: Supabase AC / MC-killer, Singapore, private `mc_killer` schema. Initial migration applied and recorded. Draft reusable-roster migration must be applied before deploying PR #5.
- Google login: verified `@deliahw2.edu.hk` accounts plus an explicit approved-teacher list. The Google consent screen currently displays WiserLife; a separate MC-Killer OAuth configuration is still recommended.
- Legacy OCR: Tesseract English + Traditional Chinese on Linux. Older assessments retain confidence/format review; the new roster-order workflow retains all written images without calling OCR.
- Class is digits followed by one uppercase letter; class number is digits only. Spaces/case are normalized, leading zeros retained, and ambiguous characters are not guessed.

**New hosted uploads use private persistent Supabase Storage (23 October 2026).** Originals and review evidence are saved outside the container. Development defaults to local mode. Three pre-existing assessment records had no local scan files at setup; their missing images could not be migrated. See [storage setup and migration](docs/STORAGE.md).

See [today's changelog](CHANGELOG.md) and [continuation notes](docs/HANDOFF.md) to resume on another device. Never copy secrets or student scans into Git.

## Teacher workflow

Use [editable reusable rosters](docs/REUSABLE_ROSTERS.md) to paste a class directly from Excel/Google Sheets or import it once,
add or withdraw students during the year, and select the saved list for each
assessment. Each exam keeps its own snapshot. Preview absences, arrange ordinary
answer sheets in the displayed class/number order, then upload scans. All five
written-field images remain available without handwriting OCR. No QR codes or
school-provided identification feature is required. Existing one-off CSV and
legacy assessments remain supported. See [scan-order instructions](docs/ROSTER_ORDER.md).

1. Sign in with an approved `@deliahw2.edu.hk` Google Workspace account.
2. Create an assessment with its title, subject, answer key and scoring; preview the class list and mark absentees.
3. Upload upright scans in class-number order, skipping absentees. Confirm that sheet count matches students sitting the exam.
4. Return to the assessment after background processing completes.
5. Review flagged question images. Names/classes/numbers are assigned from the roster; handwritten-field images remain available for reference.
6. Save teacher decisions. Scores and class/item statistics are recalculated; original readings and an audit trail remain available.
7. Resolve every flag, finalize to lock results, and download CSV or full evidence JSON.

Dark ballpoint and pencil fills use the same optical-density detector. Crosses, partial marks, faint traces, blanks and multiple selections are flagged conservatively. Crossed-out choices are never discarded automatically. Teacher decisions can confirm one choice, multiple choices or a blank.

## Run locally

Python 3.9+; Python 3.12 is used in the deployment image and CI.

```sh
python3 -m venv .venv
.venv/bin/pip install .
.venv/bin/python -m mcmark.web authorize-teacher --email teacher@deliahw2.edu.hk
export MCK_SECRET_KEY='replace-with-a-long-random-secret'
# Configure MCK_GOOGLE_CLIENT_ID, MCK_GOOGLE_CLIENT_SECRET and MCK_GOOGLE_REDIRECT_URI
# See docs/GOOGLE_LOGIN.md; for local HTTP use MCK_HTTPS=0.
.venv/bin/python -m mcmark.web serve --port 8000
```

Open http://127.0.0.1:8000. The server uses Waitress and starts one background worker. Keep one service process per data directory. Accounts, job state, raw files and results live in ignored `instance/` by default. Set `MCK_DATA_DIR` to an absolute private directory for a persistent deployment. A secret is mandatory; generate it with a password manager or `python3 -c 'import secrets; print(secrets.token_hex(32))'` and retain it across restarts. No default account exists. Google sign-in requires school OAuth configuration; without it the app displays a configuration notice. See [Google login setup](docs/GOOGLE_LOGIN.md). The explicit local-development password mode uses `MCK_AUTH_MODE=password` and `create-user`; passwords are entered interactively and hashed.

On Linux, install Tesseract and appropriate language data. On macOS, the automatic OCR backend uses Tesseract when available, otherwise local Apple Vision with Swift command line tools. Handwriting and signatures are best-effort. Low-confidence or empty readings retain their image crops and require teacher review. A readable but incorrect class number cannot be detected without external roster validation; teachers can correct it using the other written fields.

## Docker pilot

```sh
docker build -t mc-killer .
docker run --rm -it -v mc-killer-data:/data mc-killer authorize-teacher --data /data --email teacher@deliahw2.edu.hk
docker run --rm -p 127.0.0.1:8000:8000 -v mc-killer-data:/data --env-file /secure/path/mc-killer.env mc-killer serve --host 0.0.0.0 --data /data --port 8000
```

The environment file contains `MCK_SECRET_KEY` and, when served through HTTPS, `MCK_HTTPS=1`. Put a school-managed HTTPS reverse proxy in front of the service. The container runs as a non-root user. `/healthz` checks service/database availability without exposing assessment data. Back up the entire persistent data directory consistently, including the SQLite database and associated files.

This is a **single-server pilot**, not a completed school-wide production deployment. The current hosted pilot is listed above; it is not yet ready for school-wide use. See [deployment and next steps](docs/DEPLOYMENT.md) before exposing it to teachers.

## Processing and data

- Up to 100 files, 200 pages and 50 MB per upload batch; PDFs, PNG, JPEG, TIFF and BMP.
- Uploaded contents are opened and validated, not accepted solely by extension. Encrypted PDFs and oversized page/image dimensions are rejected.
- Private assessment access is enforced for pages, review mutations, images and exports.
- CSRF tokens, session rotation, HTTP-only cookies, login throttling and a restrictive content policy are included. Use HTTPS and `MCK_HTTPS=1` for deployment.
- PostgreSQL or SQLite persists the queue, results and audit history. Restart-interrupted jobs are marked failed for explicit retry. A partly failed batch cannot be finalized.
- Optimistic version checks prevent stale review forms from overwriting newer decisions.
- Finalization blocks unresolved answer/metadata/duplicate-identity flags and locks editing.
- Logs and results can contain student information: keep them inside the school's controlled environment.

Student exports contain marks, percentages, raw response statuses and review status. Class exports include mean, median, minimum, maximum, population standard deviation and pass/fail statistics. Item exports include facility, distractor frequencies, blanks, multiple marks and pending-review counts. Multiple-response option counts include each selected option; percentages may sum above 100%. Pending readings remain in provisional statistics until resolved.

## CLI and tests

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python examples/generate.py
.venv/bin/python -m mcmark.cli examples/sample-input --config examples/layout.json --output output/demo
```

For the Delia sheet, use `mcmark/layouts/delia-layout.json` and `--key answers.json`, where the key is a JSON object such as `{"1":"A","2":"B"}`. Only listed questions are processed. The CLI also supports teacher decisions through `--corrections review_queue.csv`. Its original configuration supports per-question weights and separate correct/wrong/blank/multiple marks; the web pilot exposes the common +1/0 scheme with configurable wrong-answer deduction.

Tests cover scoring, exports, template registration, all 400 empty boxes, pen/cross-out clues, OCR failure evidence, account isolation, upload validation, review recalculation, metadata corrections, stale forms, finalization, worker state and restart handling. Synthetic fixtures are generated locally. Real student scans, names, results, databases, passwords and secrets are not included.


## Where the backend and database live

The backend is `mcmark/web.py` (Flask/Waitress), with `mcmark/google_login.py` for school sign-in and the `mcmark/` processing modules. The frontend templates and static files are served by the same application.

With `MCK_DATABASE_URL`, the app uses Supabase PostgreSQL in a private `mc_killer` schema. Without it, SQLite lives at `<MCK_DATA_DIR>/school.sqlite`; the default local directory is `instance/`, and the Docker instructions use `/data/school.sqlite` on the persistent volume. Original scans and review evidence live under `<MCK_DATA_DIR>/batches/`. These are runtime files, excluded from Git. The repository stores application source; the running service is on Northflank and the hosted database is on Supabase, as listed above.


For Supabase setup, see [PostgreSQL deployment](docs/SUPABASE.md). The database migration is prepared in `supabase/migrations/`; committing it does not create a hosted project. No existing SQLite/student data is uploaded automatically. For private scan storage, see [storage setup and migration](docs/STORAGE.md).

On **Review flagged answers by question**, use the assessment-wide controls at the top to select eligible single choices and prepare confirmation across all questions. Question-level buttons remain available. Inspect images first, then select **Save selected decisions & recalculate** to apply. Existing manual choices are kept; cancelled/multiple/blank marks, uncertain alignment and unavailable images remain for individual review.

For singles excluded by cancellation/stroke checks, **Quick visual check** shows compact evidence cards. Inspect the images, select displayed choices you want to keep, confirm, then save. This is explicit teacher review, not automatic acceptance. Unresolved alignment failures are grouped by sheet and excluded from this view. See [review efficiency and alignment checks](docs/REVIEW_EFFICIENCY.md).

The latest detector retains a 0.70 review-clearance score, discounts printed-border halos from spill counts and distinguishes compact filled boxes from short diagonal cues. Cross and competing-mark safeguards remain. Validation results and limits are recorded in the review-efficiency guide.

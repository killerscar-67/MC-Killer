# Changelog

## 2026-10-23

### Added
- Opt-in private Supabase Storage backend for originals and review evidence, with integrity manifests and restart recovery.
- Ownership-checked image proxy, relative evidence references, generated upload filenames and required-storage configuration.
- Storage connectivity check and verified migration command that retains existing local files.
- Private hosted `mc-killer-scans` bucket (50 MB object limit), configured backend secrets and deployed persistent-storage release.
- Tests for storage integrity, privacy, failures and evidence access after local files disappear.

### Fixed
- Close a legacy SQLite fixture connection so test cleanup works on Windows.

### Validation and limitations
- Local suite: 41 tests, 40 passed and disposable PostgreSQL integration skipped locally. GitHub CI including PostgreSQL passed.
- Live private storage upload/download verified; anonymous public download denied. Synthetic original/review images survived container replacement with matching SHA-256 checksums; public health returned OK afterward.
- Three existing ready assessment records had no local scans/evidence to migrate; their historical images remain unavailable.

## 2026-10-22

### Added
- MCQ scan pipeline for PDFs/images, Delia 100-question A–D template and assessment-specific question counts/keys.
- Optical-density marking, blank/multiple/faint/cross-out review flags, evidence crops and teacher corrections.
- OCR of all five written fields: name, signature, class, class number and subject/paper.
- Configurable scoring, class summaries, item facility/distractor analytics, CSV and JSON exports.
- Teacher web workspace, Google OIDC, approved-teacher CLI, assessment ownership, audit history and finalization.
- Supabase PostgreSQL adapter, private schema migration, RLS, connection pooling and PostgreSQL CI integration.
- Free Northflank pilot and Cloudflare Pages fixed-origin streaming gateway at mc-killer.pages.dev.

### Fixed
- School Google domain corrected from delia.edu.hk to deliahw2.edu.hk, including validation, account picker, CLI and documentation.
- Class OCR normalized to digits + one uppercase letter; class number to digits-only validation. Raw OCR remains available and invalid readings require review.
- Hosted connectivity setup: IPv4 session pooler and mounted CA certificate for verified TLS.

### Validation and limitations
- Latest local suite: 35 tests, 34 passed and PostgreSQL integration skipped locally. Earlier full PostgreSQL CI passed; check latest GitHub Actions before rollout.
- Public login and database health verified before the latest OCR-format change; teacher completed school sign-in/approval and created an assessment.
- OCR remains Tesseract; PaddleOCR/Google Vision were researched but not installed or enabled.
- No scans were submitted to an external AI/OCR provider by the application.
- Uploaded scans/evidence remain ephemeral. No roster reconciliation, admin approval UI or school-wide capacity benchmark yet.

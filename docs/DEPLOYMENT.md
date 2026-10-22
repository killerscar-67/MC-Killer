# Pilot deployment and school rollout

## Current architecture

Browser → Flask/Waitress → Supabase PostgreSQL (or SQLite for development) + private files → one background processing thread.

See [Supabase setup](SUPABASE.md) for the PostgreSQL migration and connection configuration. Hosted provisioning is separate from committing this code.

Each teacher owns their assessments. The administrator approves school Google accounts using the CLI; see [Google Workspace setup](GOOGLE_LOGIN.md). The job queue survives service restarts; processing jobs interrupted by a restart become failed and can be retried. Database results are authoritative, and exports are generated from a database snapshot. Uploaded originals and raw OCR/mark evidence remain available on the server. Review decisions record actor, time, previous values and confirmed values. Finalization locks results.

The image processor uses OpenCV/PyMuPDF with Tesseract or macOS Vision OCR. No external AI service is integrated and no image is uploaded to an AI provider. OCR accuracy is not guaranteed by confidence values, especially for Chinese handwriting or signatures. Teachers must verify identity and unresolved marks.

## Before a school pilot

- Run one application process against one data directory; multiple Waitress processes and multiple containers sharing this SQLite directory are not supported. The in-process login limiter and startup job recovery assume a single process.
- Configure a stable secret, an HTTPS reverse proxy, secure cookies and a private persistent volume. Do not expose the development preview or its test account.
- Approve individual @delia.edu.hk teacher accounts, configure school Google OAuth and restrict server/filesystem access to designated administrators.
- Agree on who can access scans and how long scans, results, backups and audit history should be retained. This release has no automated deletion interface; administrators must manage retention carefully and remove database/file records together.
- Monitor processing failures, disk space and backups. Review server logs for failed batches; the UI intentionally does not expose internal paths or exception details.
- Test backup restoration and teacher account procedures before relying on the system for live marks.
- Compare representative pencil, pen, erased, crossed, skewed and faint sheets with manual marking. Measure false acceptance and false review rates, metadata errors and processing throughput. Do not infer school capacity from two sample sheets or synthetic tests.

Uploaded PDFs/images are parsed within the service process. This pilot validates content, page count, dimensions and size, but does not sandbox native parsers or provide malware scanning. For exposure beyond a small controlled pilot, isolate processing in constrained worker containers, add time/memory quotas and an upload scanning policy.

## Next school-wide milestones

1. Administrator UI for the Google teacher allowlist, and explicit sharing/department roles. Google login and CLI access revocation are implemented.
2. Roster import, identity reconciliation, duplicate resolution workflow and assessment-level permissions.
3. Private object storage and an independently supervised durable queue/worker service; bounded concurrency and retry/idempotency controls. PostgreSQL connectivity and a backend-only Supabase schema are implemented.
4. A supported archive/delete workflow with retention schedules, backup restoration checks and operational monitoring.
5. Benchmarking against teacher-reviewed real scans, template versioning, processing-version records and regression fixtures with consented/anonymized material.
6. Optional vision-model assistance for difficult handwriting/corrections only after the school approves its data flow. Suggestions should remain distinct from teacher-confirmed decisions.

Hosting, school identity provider, roster source and retention requirements need to be selected with school IT. This PR intentionally does not provision paid infrastructure or publish student data.

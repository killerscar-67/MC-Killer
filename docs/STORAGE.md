# Private persistent scans

The backend supports Supabase Storage for originals and review evidence.
PostgreSQL retains results, corrections and audits. The image route checks teacher
ownership before proxying private files; no storage credential reaches the browser.

## Runtime setup

Private bucket `mc-killer-scans` was created in project `tdynkamfmbktqzebvrav`
on 23 October 2026, with a 50 MB object limit and no public access policies.
Hosted activation requires these Northflank runtime settings:

```dotenv
MCK_STORAGE_BACKEND=supabase
MCK_REQUIRE_PERSISTENT_STORAGE=1
MCK_SUPABASE_URL=https://tdynkamfmbktqzebvrav.supabase.co
MCK_STORAGE_BUCKET=mc-killer-scans
```

Set `MCK_SUPABASE_STORAGE_KEY` as a secret runtime variable using this project's
backend secret key or legacy service-role key. It grants privileged project access:
keep it in the hosting secret manager, never Git, browser code, logs or screenshots.
Google teacher sign-in remains unchanged. No additional package is required.

Run `python -m mcmark.storage check` in the deployment environment. It verifies
the bucket is private, uploads/downloads a synthetic probe, then deletes only that
probe. Startup also checks private bucket access. Required-storage mode refuses
silent fallback to local disk. Development defaults to local mode.

## Protect existing files before any restart

The old deployment's ephemeral files can disappear while deploying this feature.
Before redeploying, preserve a private copy of `/data/batches`, or run the new
migration module against that directory with processing stopped. Never put student
files in Git. Missing old files must not be treated as successful migration.

With the old files available, the new code, existing database credentials and
storage settings, stop the service/worker and run:

```sh
python -m mcmark.storage migrate --data /data
```

Each batch's originals/output are copied and read back with SHA-256 verification
before the database is switched to object storage. The migration checks concurrent
changes, records an audit and retains local files. It stops on missing originals or
review evidence. Reruns skip completed batches. Keep processing stopped until done.

New uploads are durable before queuing. Workers restore verified inputs, process
locally, and save evidence before marking results ready. Storage failures leave
jobs failed for explicit retry. Successful jobs clear scratch files. Generated
object names contain no student names; the private input manifest retains original
filenames. Relative evidence paths survive container path changes.

## Verify rollout

1. Run the storage check and application tests.
2. Process an anonymized sample and check full-sheet, question and written-field images.
3. Verify another teacher gets 404 and anonymous visitors cannot retrieve evidence.
4. Redeploy and verify the same marks/images remain. Retry an interrupted batch.

No automatic deletion policy is enabled. Agree retention with the school before
deleting records. Back up objects separately: database backups do not contain scan
bytes. Failed uploads may leave private orphan objects; reconcile against batch
IDs before cleanup. Monitor storage/egress quotas and scratch disk usage. This
does not add multiple-worker support.

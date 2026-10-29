# Changelog

## 2026-10-29 — Faster visual review and bounded alignment recovery

- Slightly relaxed automatic review clearance (balanced-v2): row correlation 0.70 → 0.65, connected stroke area 12 → 10 pixels; tolerate up to 16 selected-box spill pixels only with at most 4 around other choices. Density/span thresholds and cancellation, competing-ink and failed-alignment guards remain. The 240-answer development replay has 63 → 57 pending answers, unchanged selections and zero observed unflagged errors.
- Added compact, image-based confirmation of flagged single choices, including cancellation warnings after explicit teacher inspection. Failed alignment and multiple/blank readings remain separate.
- Added sheet-level alignment summaries, low-score/boundary retries up to 14 pixels, stricter retry evidence and equal-location rounding tolerance. Recovery diagnostics are preserved; review crops follow accepted offsets.
- Added Select eligible single choices and Confirm selected current choices controls across all questions, retaining question-level controls.
- Bulk selection loads eligible evidence images, including offscreen/lazy images, before selecting rows. Missing/broken images stay excluded.
- Existing manual decisions are kept. Cancellation, multiple, blank and alignment eligibility rules remain unchanged. Decisions still require Save selected decisions & recalculate; no automatic finalisation.

## 2026-10-29 — Paste and edit rosters in the browser

- Moved roster renaming and school-year editing to a visible form near the title; history remains separately collapsible.
- Added an editable roster grid: paste rows directly from Excel or Google Sheets, with optional headers, English/Chinese names and leading-zero class numbers. File uploads remain available.
- Saved rows retain permanent references; teachers can edit transfers, withdraw/reactivate students and append new rows. Omitted records remain intact.
- Pasted changes use the existing signed preview/confirmation, ownership, CSRF and stale-revision checks. Invalid cells can be corrected without losing the pasted grid.
- No database migration or external spreadsheet service is required.

## 2026-10-28 — Editable reusable rosters (PR #5 draft)

- Added teacher-private saved rosters, CSV/XLSX import with preview/confirmation, manual additions, transfers, withdrawals/reactivation, stable student references and versioned audit history.
- New assessments can reuse saved rosters and retain independent candidate snapshots. Existing one-off CSV and class-number scan order remain supported. No QR identification or personalised printing is included.
- Added explicit candidate updates and image-based sheet-to-student reassignment while results remain open, preserving original identities. Submitted/finalised history is not silently rewritten by school roster edits.
- Added missing-submission exports and complete unique-candidate assignment checks before finalisation.
- Added an additive backend-only PostgreSQL migration with RLS/audit permissions plus local SQLite support. Migration and deployment remain pending.
- Added regression coverage for stable references, XLSX/CSV, inactive students, stale/unauthorised edits, snapshots, candidate updates, reassignment and finalisation.

## 2026-10-27 — Roster-order identity workflow (PR #5)

- Replaced the OCR-experiment scope with class-list CSV preview, numeric class-number order and explicit absence selection.
- New web assessments require sheet count to equal non-absent students and assign names/classes/numbers from the confirmed roster snapshot.
- Skip all handwritten-field OCR in roster mode while retaining five written-field image crops; subject comes from assessment details.
- Added attendance/submission table and private UTF-8 CSV export, roster confirmation/assignment audit, read-only roster identities and post-processing count checks.
- Existing assessments and legacy CLI/API configurations keep their previous OCR workflow. No roster migration, model download or deployment is included.
- See docs/ROSTER_ORDER.md for ordering and file-format requirements.

## Unreleased

### 2026-10-27: labelled-batch mismatch fixes
- Retry boundary-limited local row registration within a nine-pixel search, retaining minimum correlation and boundary rejection. Added shifted and still-out-of-range regression cases.
- Recover small density-supported partial marks as provisional candidates; keep weak-mark review mandatory and reject smaller specks.
- Add teacher-confirmed cancellation suggestions for extended diagonal evidence when another selected choice remains; preserve every original/current selection and keep ambiguity review.
- Detector stroke-v2.2 on the now-development 240-label batch: direct agreement 229 -> 233/240; including suggestions 234 -> 240/240; pending rows 67 -> 63, no observed unflagged errors. Seven cancellations still require confirmation. No colour masking or answer-key-based inference.
- All six earlier sample sheets retain selections and expected cancellation suggestions; no out-of-scope selections. Local suite: 66 tests, 65 passed and PostgreSQL skipped. Not deployed; independent evaluation and full hosted capacity remain outstanding.


### 2026-10-27: visual batch confirmation
- Add explicit selection/confirmation for eligible single-choice cards grouped by question, preserving manual decisions and existing save/audit protections. Ambiguous cancellations, multiple marks, blanks and uncertain alignment remain excluded.
- Add offline red-annotation impact diagnostic; no production masking or automatic flag suppression. The 12-sheet experiment reduced pending flags 67 to 54 but changed three blank readings and several suggestions, requiring labels before enabling any filtering.
- 24 of 67 pending rows in the new batch qualify for visual batch confirmation. Latest local suite: 62 tests, 61 passed and PostgreSQL integration skipped.


### 2026-10-26: simpler review controls
- Shortened Pending label, removed redundant Confirm current shortcut, and kept primary choices on one row (scrollable on narrow screens).
- Place decision buttons to the right of each student’s evidence on wider screens, stacking below on mobile.
- Changed grouped review to a vertical student list with all question groups initially expanded.
- Replaced dropdowns with accessible choice buttons for pending, blank and individual options; multiple-selection combinations remain available in an expandable section.
- Browser-verified one-click selection and highlighted state. Existing transactional saves/audit behaviour is unchanged; 60 local tests, 59 passed and one PostgreSQL integration skipped.

### 2026-10-26: question-grouped teacher review
- Added an assessment-wide pending-answer page grouped by question, with student identification, row images, original/current readings, dark coverage, reasons and suggestions. Individual sheet review remains available.
- Teachers can prepare current/suggested/custom decisions and save across students in one transaction. Unchanged answers stay pending; identity flags remain separate.
- Preserves ownership, CSRF, stale-form rejection, finalization locks, original readings, per-answer teacher records and an audit event. Invalid decisions abort the whole save.
- Synthetic browser preview verified images and quick-confirm controls. Local suite: 60 tests, 59 passed and PostgreSQL skipped locally. No deployment or change to detector thresholds in this follow-up.

### 2026-10-26: loop/circle refinement
- Compact cross-out clues now require four diagonal arms plus straight ink support on both sides of each diagonal; arc tangents alone are insufficient. Large crosses retain the surrounding-line path with at least 30 outside-ink pixels.
- Store straight-diagonal support and detector_version=stroke-v2.1. Suggestions remain provisional and ambiguous patterns remain reviewable.
- Added ellipse/loop, looped multi-selection and cross-over-loop regressions, alongside existing compact/fill-plus-X tests.
- Reused three labelled sheets: marked reviews now 16/29 (3, 6, 7), down from initial PR #4's 17/29 and live stroke-v2's 28/29. Candidate selection sets and all three true cancellation suggestions remain correct; intentional B+C has no cancellation suggestion. All 271 intended blanks remain unselected.
- 57 local tests: 56 passed, PostgreSQL integration skipped. Independent writer/scanner validation and hosting benchmarks remain outstanding; no deployment.


- Balanced review policy accepts isolated strokes only with strong local registration, sufficient ink and no competing/cancellation evidence; original diagnostic reasons remain recorded. Conservative policy remains available via layout config.
- Review screen defaults to unresolved questions with an option to show all decisions. One explicit action confirms only rows flagged solely as blank, with the existing audit trail and stale-form protection.
- Three reused labelled sheets: marked-question review flags reduced from 28/29 to 17/29; all selections and three cancellation suggestions unchanged, all 271 blanks remain unselected. These are development regressions, not independent accuracy estimates.
- Local suite: 54 tests, 53 passed and PostgreSQL integration skipped locally. Handwriting OCR and broader capacity/accuracy validation remain outstanding.

## 2026-10-23

### Added
- Added template-subtracted thin-stroke candidates and compact/dense-fill cross-out clues for boxed marks.
- Thin strokes are selected provisionally with mandatory review; raw density selections remain preserved.
- Cancellation remains a teacher-confirmed suggestion. Review displays per-option state and dark coverage, not a correctness confidence.
- Detector version is stored in each new response; existing assessments and corrections are not reprocessed.
- Added synthetic tests for thin/faint lines, small Xs, X over fill, single slashes, specks, one-pixel shifts and answer-key independence.
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

### Mark detection pilot validation
- PR #3 merged to main (merge commit 4d8a730); live exports confirm detector_version=stroke-v2.
- Reused three user-labelled 100-question sheets locally: 297 exact selection sets and three correct cancellation suggestions requiring teacher confirmation; all 271 intended blanks remained unselected. The first two sheets were development cases; the third was initially tested without tuning.
- Live export assessed Q1-10 only: the three matching test sheets had 27 exact selection sets and three correct cancellation suggestions, including the intentional B+C multi-selection.
- Subsequent teacher review exports preserve previous readings, decisions and recalculated marks. Latest supplied export has all six sheets with review_required=false and score_is_provisional=false. This does not independently confirm the assessment finalization lock.
- Local detector-only runs took approximately 0.34-0.36 seconds per sheet and about 129 MB peak RSS on the developer machine; these exclude OCR and are not a Northflank capacity benchmark.
- Handwriting OCR remains Tesseract and performed poorly in the pilot (29 of 30 identity fields initially flagged unrecognized). Teacher identity verification remains necessary.
- Review workload remains high; full-pipeline memory/throughput, concurrent uploads, broader independent writer samples and prior teacher-crop regression coverage remain outstanding. An earlier diagnostic alongside production exited with code 9 and the container restarted; avoid repeating full-document diagnostics in the live 512 MB container.
- Student PDFs, identity data and raw result exports are retained locally and are not committed to the public repository.

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

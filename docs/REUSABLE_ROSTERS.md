# Editable reusable rosters

This workflow uses ordinary school answer sheets. **No QR codes, personalised printing or additional school-provided identification are required.** Identity comes from the teacher-confirmed class-list/scan order. Equal counts cannot detect swapped papers; teachers must arrange the stack and use image evidence to correct an incorrect assignment.

## Teacher workflow

1. Open **My rosters**, create a name and school year, then paste from Excel/Google Sheets into the editable grid, import CSV/XLSX, or add students manually. Rosters are private to the owning teacher; school-wide sharing is not implemented.
2. Import up to 200 students, with class, number, english_name and optional chinese_name. Names can be English, Chinese or both. Class numbers retain leading zeros. Common spaced headers such as Class No. and English Name are accepted. UTF-8 CSV and XLSX are supported; CSV uploads are 1 MB maximum and expanded XLSX data is limited to 20 MB.
3. Preview imports before applying. No changes are saved at preview. Active class/number pairs must be unique; 01 and 1 are equivalent. Omitted rows are kept. For bulk updates, export the roster and retain its record_id column. Set active=false for withdrawal. Add new students with **Add student** when updating an existing roster.
4. Use **Edit students** to change names/class/numbers or reactivate a withdrawn student. Every edit preserves the permanent student reference. No hard-delete workflow is supplied; withdrawals remain visible in history. A fresh roster imported from an exported CSV retains valid permanent references, allowing a new school-year list without inferring identity from names/numbers.
5. Create an assessment, choose the saved roster, click **Preview class list**, select absentees and confirm scan order. Saved rosters are sorted by class and numeric class number. A single-class CSV can still be uploaded for a one-off assessment. Active saved students are offered by default; inactive students are excluded. The submission is checked against the previewed roster version/digest.
6. Stack original papers in the displayed order, skipping absentees, and upload scans. Total pages must equal expected students. Each PDF/TIFF page is one sheet. A failed page fails the batch rather than silently shifting later student assignments. No handwritten OCR is run; all five written zones remain private image evidence.
7. While processed results remain open, **Review assessment candidates** can explicitly add new roster students or mark an unsubmitted candidate absent. Source roster edits never change existing assessment snapshots automatically. Submitted identities retain their historical name/class/number even after transfers or withdrawals.
8. **Correct student assignments** allows an explicit sheet-to-candidate correction after checking the written fields. Original identity, previous/current decisions and actor/time are retained. One student cannot be assigned to two sheets. Leaving a sheet unassigned requires review. Adding a candidate never automatically shifts the existing scan assignments.
9. The attendance/submission CSV reports missing submissions. Finalisation requires every expected candidate to have exactly one assigned sheet, in addition to all existing answer/identity review checks. Mark a genuine non-submission absent or correct the assignments first. Finalised candidate/identity/results records are locked; later roster edits do not alter them.

Example initial import:

```csv
class,number,english_name,chinese_name
5A,01,EXAMPLE STUDENT,
5A,02,ANOTHER STUDENT,測試學生
```

Permanent references identify records; they are not credentials and do not grant access. The teacher owner still controls all roster, preview, assessment, evidence and export operations.

## Data and safeguards

- `rosters`: owner, name, school year, version and JSON student records. `roster_audit`: append-only application history including changed values. SQLite initializes these locally; PostgreSQL uses the migration below.
- Assessments retain a copied roster, expected/absent state, source revision/year and stable student references inside private config/results. No cross-assessment result rewrite or automatic student merge occurs.
- POST operations retain CSRF and enabled-teacher checks. Owner predicates protect every roster resource. Version checks reject stale edits. Bulk import previews are signed, tied to teacher/roster/version and expire after 15 minutes; replay after a save is rejected.
- PostgreSQL tables stay in the backend-only `mc_killer` schema with RLS and backend-role-only grants. Audit has select/insert privileges, no update/delete grant. Browser/anonymous Data API access is not added. Application ownership is enforced by the backend, as with existing assessments.
- CSV exports escape formula-like text. XLSX is read as data; formulas/macros are never evaluated. Real rosters, exports, preview tokens, scans and audit values must not be committed to public Git.

## Deployment and validation

Apply `supabase/migrations/20261028030452_reusable_rosters.sql` to the intended database **before deploying this branch**. It adds two private tables/indexes/policies/grants; it does not rewrite existing jobs, users or results. No production database migration or deployment was performed as part of implementing this draft.

The CI PostgreSQL service applies all migrations to a disposable database and verifies application reads/writes, roster preview/export and denial of audit deletion. Local SQLite tests cover stable references, CSV/XLSX import, duplicate numbers, inactive students, preview/confirmation, CSRF/ownership, stale edits, assessment snapshots, explicit candidate changes, identity corrections and finalisation locks. Existing ordered-stack/no-OCR pipeline tests remain in the suite.

Before school-wide rollout, pilot a real exam stack with a teacher checking written identities against assignments. Independent scanner/mark detection validation remains a separate concern. This change does not claim recognition accuracy or detect equal-count scan-order mistakes.

Rollback: stop new roster use and redeploy the previous application. Leave the additive roster tables intact so snapshots/audit can be recovered. Do not delete student history to roll back application code.

## Paste from a spreadsheet

Copy a rectangular selection in this order: **Class, Class number, English name, Chinese name**. Click the first destination cell in the grid and paste. A header row (`Class`, `Class No.`, `English Name`, `Chinese Name`) is optional when pasting from the Class column. Leave unavailable Chinese names empty; a student must have at least one name. The optional fifth column accepts Active/Inactive or true/false.

The grid supports ordinary Tab navigation, direct cell editing, adding rows and removing unsaved rows. Saved rows appear automatically and keep their stable references. Paste into those rows only when you intend to update those same students; append new students using Add row. A repeated active class/number is rejected rather than silently merged. Use Inactive for withdrawals. Preview changes, check the before/after values and select Apply changes to save. Reset unsaved changes restores the initially displayed grid after confirmation. Invalid input stays editable.

The grid uses plain-text clipboard data and local application code; it does not embed a third-party spreadsheet or send rosters to an external service. Existing file import/export remains available, including a no-JavaScript file-upload fallback. No additional database migration is needed.

To rename a saved roster, open it from My rosters and use the visible **Rename roster** form near the top. Edit Roster name (and School year if needed), then select **Save roster details**. The saved list shows the updated name; existing assessment snapshots retain their original details.

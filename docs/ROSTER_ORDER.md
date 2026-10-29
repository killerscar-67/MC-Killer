# Class-list order and exam submissions

Saved, editable rosters are also available; see [reusable rosters](REUSABLE_ROSTERS.md). No QR identification is required. The one-off CSV path below remains supported.

New web assessments use the teacher's class list as the identity source. Papers
are stacked in numeric class-number order, skipping absent students. A scanned
sheet is assigned to the next student who sat the exam. This workflow trusts that
the exam stack and scan order are correct; it does not attempt to infer identities
from handwriting or detect a swapped pair of papers with equal counts.

## Teacher workflow

1. Export one class list as UTF-8 CSV, including the header below. Chinese names
   and UTF-8 BOM files are supported. Leading zeros in class numbers are retained.

   ```csv
   class,number,name
   3A,01,Example Student
   3A,02,Another Student
   3A,03,Third Student
   ```

   `class_number` or `student_id` can replace the `number` header. The app sorts
   numerically, so 2 precedes 10. Duplicate numbers, including 01 versus 1, and
   mixed classes are rejected. The limit is 200 students and 1 MB per roster.
2. In **New exam assessment**, preview the class list and check **Absent** beside
   students who did not sit the exam. Attendance and submission are distinct:
   absence is explicitly selected; submission is recorded when sheets are processed.
3. Upload the ordered papers, preferably as one multipage PDF. For multiple files,
   inspect the displayed file order; the server retains that order and processes
   each file's pages in sequence. Each page is one answer sheet.
4. Confirm the papers follow the displayed order. The upload is blocked unless
   page count equals the number of non-absent students. Changing the roster,
   absences or scan selection clears the order confirmation.
5. Processing assigns names, classes and class numbers from the roster and subject
   from assessment details. No handwritten-field OCR is called. All five written
   regions, including names and signatures, remain as reference image crops.
6. Review answer flags as usual. Roster identities do not generate handwriting
   review flags or require a separate metadata-confirmation step. They are read-only
   in individual sheet review. Finalization still requires all answer/sheet flags
   to be resolved and locks results.
7. View the class-list attendance/submission table on the assessment and download
   its UTF-8 CSV. Absent students are included as **Absent / Not expected**; matched
   sheets are **Present / Submitted**, with their sequential sheet numbers.

## Data and compatibility

The roster and absence snapshot belong to the assessment and are stored in its
existing private database config. Preview requires teacher sign-in and CSRF,
returns no-cache responses, and does not save a one-off CSV separately. Selecting a saved roster copies its active students and records the source revision. Submitted
CSV bytes are parsed again and checked against the preview digest. A roster
confirmation audit records the digest, absences and expected sheet count; successful
processing records the assignment count/order. Each result retains its original
roster assignment and position. Existing ownership checks also protect submission
exports, image evidence and review changes. Saved reusable rosters require the additive migration documented in REUSABLE_ROSTERS.md; the original one-off CSV format remains unchanged.

Counts are checked again after processing. A failed page does not shift remaining
student identities into ready results; the batch fails for explicit retry. Original
scans and handwritten evidence use the existing private scan storage backend.

Existing assessments and legacy CLI/API configurations without roster mode keep
their previous OCR/review behavior. They are not reprocessed or matched to a new
class list automatically. New web forms select roster mode and offer saved rosters or a one-off CSV. This PR replaces the
offline OCR-experiment scope; no PaddleOCR dependency or model download is added.

All tests and browser checks use synthetic rosters and blank/generated sheets.
Never commit real class lists, names, exam sheets or submission records to Git.

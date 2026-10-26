# Stroke-aware boxed mark detector (candidate release)

The original dark-density threshold remains 0.35. New template-subtracted connected strokes can add a provisional candidate below this threshold. Printed template ink plus a one-pixel halo is excluded from this candidate analysis to suppress small registration errors. Tiny specks are rejected. All thin candidates require teacher confirmation; scores remain provisional until review.

Cross clues combine the existing surrounding-line detector, smaller intersecting diagonals near the option centre, and four diagonal arms outside the fill core. The last case helps when a filled box masks the centre of an X. Single diagonal cancellation clues require review without automatic exclusion. An X may be an intended selection, so cancellation is never a final automatic correction. If exactly one non-crossed candidate remains, it is displayed as a suggestion only. No interpretation depends on the answer key.

Responses record `detector_version=stroke-v2`, original density selections, candidate selections, per-option features/states, reasons and suggestions. Review displays dark coverage (not correctness confidence). Existing results/teacher corrections remain unchanged. The same new detector applies to newly processed boxed layouts; circular metadata grids retain the old detector.

## Validation so far

- Local complete suite: 46 tests, 45 passed and disposable PostgreSQL integration skipped locally.
- Clean template: all 100 questions / 400 boxes produced no selections or cross flags.
- Detection-only local smoke benchmark: 0.081 seconds for 100 questions; process peak RSS 56.4 MB on the developer Mac. This excludes rendering, alignment, OCR, network and web-server concurrency and is not a Northflank capacity estimate.
- Synthetic tests cover one-pixel dark/faint horizontal strokes, small X, filled box plus X, single diagonal, ordinary fill, empty/speckled boxes and one-pixel translation.

## Release gate and remaining limitations

This is the first review-assisted stage, not proven handwriting accuracy. Before deployment, visually label the affected real rows and compare old/new candidate detection and cancellation suggestions against teacher decisions. Keep held-out sheets independent from tuning. Measure missed thin marks, incorrect unreviewed choices, cancellation errors, unnecessary review and full-process memory/time on the 512 MB host.

A mark exactly overlapping existing printed ink may leave no detectable new ink. Oblique ticks, single cancellation strokes, heavy scribbles, faint erasures and larger misregistration remain ambiguous. Synthetic tests cannot establish a real-world error rate. Add consented/anonymized real fixtures rather than committing student scans. Reprocessing existing jobs requires an explicit workflow that preserves teacher overrides; this release does not change them automatically.

## Real-crop validation follow-up

A read-only comparison used saved question crops and saved teacher decisions from the pilot. It recovered thin responses on one sheet (including Q2, Q4, Q6, Q11, Q14 and Q19), but the first draft proposed multiple extra options on another sheet. This falsified the assumption that synthetic blank-template tests alone established adequate suppression of real scan artefacts. The candidate now uses a wider printed-ink halo and local contrast limit, and only promotes a unique weak candidate. Multiple weak candidates remain ambiguous and do not override the density reading. This refinement still requires a completed real-crop rerun; do not deploy based on the initial synthetic pass.

The first original-PDF diagnostic exited with code 9 and the host restarted once, consistent with memory pressure while diagnostics shared the 512 MB live container. Health subsequently returned OK. Avoid full-document comparison alongside the live web process; use saved crops or an isolated worker. The crop comparison does not mutate jobs or teacher decisions. No student images are committed.

## 23 October: locally supplied thin-stroke scan

The user confirmed Q1-10 as A B C D A B B D C B, with Q11-100 blank. The live main detector returned blanks for all first ten. The initial draft also missed border strokes and produced a wrong Q9 candidate. The question sampling strip is only four pixels high; per-row matching found residual offsets of 1-4 pixels after global homography.

Added bounded per-row template registration using a small ROI rather than warping/copying a full page per question. Low match score or a best match at the search boundary disables weak-candidate promotion and requires alignment review. A one-pixel printed-ink halo is retained after reliable row alignment.

On the supplied scan after this refinement: all 10 marked answers match the user-confirmed labels; none of the 90 blank questions receives a selected option. Marked rows remain provisional for review. This scan was used for tuning and is NOT a held-out accuracy evaluation. It does not validate real cancellation marks. The local baseline/candidate run, including PDF rendering and global alignment but excluding OCR, took approximately 0.30 seconds and peaked at 128.4 MB RSS on the developer Mac. This is not a host capacity measurement.

The scan, identity fields, crops and detailed readings stay local and are excluded from Git. Independent labelled cancellation sheets and full-process memory/throughput checks remain release requirements.

## Second locally supplied scan: registration and cancellation

The user confirmed Q1-10 as C B D D A B C B A A and Q11-100 blank; Q1 A is cancelled and Q6 B is circled emphasis. Before tuning, the candidate and main global registration rejected this page because the RANSAC inliers covered only a shallow header region. A stricter descriptor ratio retry (0.6 after 0.7) obtained page-spanning inliers, retaining all minimum-inlier, coverage and projected-corner checks.

Following the retry and candidate-preservation refinement: Q2-10 selections match all nine confirmed answers. Q1 keeps A+C as provisional raw candidates and suggests C; no automatic cancellation is committed. All 90 blank questions stay unselected. Q2/Q6/Q8 still produce possible-cross flags on loops/emphasis; these are ambiguous rather than final cancellations. Thus this is improved review assistance, not 10/10 automatic final marking. A lone cross-like stroke with no alternative is retained as an ambiguous candidate rather than discarded as blank.

Both supplied pages now serve as development cases. The first page was rechecked after these changes and retains ten matching selections with 90 blank questions unselected. Neither is independent held-out evidence after tuning. Synthetic coverage includes lone-cross ambiguity and registration retry. Current local suite: 51 tests, 50 passed, PostgreSQL skipped locally. Real scans and detailed images remain excluded from Git.

## Balanced review policy (proposed follow-up)

New boxed readings record review_policy=balanced-v1 and original_review_reasons. A single choice can bypass density/thin-mark review only if local registration >=0.70, interior density >=0.08, stroke component area >=12 and span >=7, with <=2 new ink pixels in every competing option. Any other reason, cancellation clue, or diagonal ambiguity keeps review mandatory. These thresholds are heuristic gates, not calibrated probabilities. Set review_policy=conservative in the layout config to retain all original flags. Existing results are not rewritten.

The sheet view initially shows unresolved questions; uncheck the filter to see every decision. A teacher can explicitly confirm all rows flagged only as blank in one save. Faint/cancelled/poorly aligned blanks are excluded. Identity remains a single confirmation per sheet; roster matching is not implemented.

Regression on the three reused labelled sheets reduced marked review counts from 10/10/8 to 3/7/7 (17 of 29 marked rows), without changing candidate selections or cancellation suggestions. All 271 intended blank rows remain unselected and still need individual or explicit batch confirmation. Samples used for this change are no longer independent validation. Full suite: 54 tests, 53 passed, PostgreSQL integration skipped locally.

## Loop/circle refinement (2026-10-26, draft)

The stroke-v2.1 candidate rejects compact cross hypotheses unless four outer arms and straight diagonal support are present. For each slope sign, sample five distances (3 through 7 pixels) on each side, allowing a one-pixel neighborhood. Require at least 80% support on each side for a tested slope (0.6/0.8/1.0/1.2). This corroborates the existing geometry; it is not a general loop recognizer or calibrated confidence. Legacy long crosses still require both surrounding-line directions and at least 30 outside pixels. Some circles, tick shapes and irregular fills remain ambiguous and retain other review reasons. No option is automatically removed.

Synthetic regressions cover six ellipse size/weight combinations (including low-registration fallback), looped multi-selection and an X over a loop, in addition to compact and dense-fill X cases. Reused real scans retain all expected selections, three true cancellation suggestions, intentional B+C without a false suggestion, and all 271 blanks. False cross-out flags on second-sheet Q2/Q6/Q8 and third-sheet Q5 are removed; some retain stray/diagonal/weak-ink review. Marked review counts are 3/6/7 (16 of 29). No new incorrect automatic decisions were observed on these development samples; broader accuracy is unmeasured. Full suite: 57 tests, 56 passed and PostgreSQL skipped locally. Fresh writers/scanners, irregular loops, rotations and faint cancellation coverage remain required before completing the draft requirements.

## Assessment-wide review by question

Open the assessment's “Review flagged answers by question” link. Only unresolved responses appear, grouped in configured question order, with student cards in a vertical list and question groups expanded by default. Each card keeps the evidence crop, original density reading, current choices, option states/dark coverage, reasons and suggestion. The individual review link opens the existing sheet screen.

“Confirm current” and “Use suggestion” prepare a decision; teachers must save selected decisions to apply them. BLANK, single and multiple choices are available. Empty decisions remain pending. The save is atomic across students, rejects stale forms and finalized assessments, and records actor, timestamp, previous selections and changes. Identity or duplicate-sheet flags remain unresolved until handled through individual sheet review. This workflow reduces navigation; it does not improve the detector's accuracy or remove additional flags. Tests cover multi-student saves, invalid-save rollback, unchanged pending responses, original-reading preservation, grading, audit, CSRF, ownership and finalization. Current local suite: 60 tests, 59 passed and PostgreSQL skipped.

Grouped review uses native radio inputs styled as large clickable choice buttons: Keep pending, Blank and each option. Multiple-choice combinations are available in an expandable section. These controls also work without JavaScript; quick-confirm buttons are optional shortcuts. Selecting a decision does not save it automatically.

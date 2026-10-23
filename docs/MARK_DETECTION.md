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

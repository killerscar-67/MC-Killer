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

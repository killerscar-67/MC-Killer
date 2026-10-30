# Review efficiency and alignment recovery

## Teacher workflow

The assessment review page retains question-level controls and individual-sheet review. Assessment-wide Select eligible single choices only selects the existing eligible subset. Confirm selected current choices prepares pending radio decisions and preserves manual choices; Save selected decisions & recalculate applies them through the existing signed-in, CSRF, revision and audit workflow.

Quick visual check adds compact cards for current single choices, including warned strokes and suspected cancellations. Its default filter shows cases excluded from automatic selection; All single choices includes the ordinary eligible subset too. Inspect each image before selecting. Select displayed single choices loads the displayed evidence, skips unavailable images and checks the visible subset. This is explicit human review, not a relaxed detector threshold. Confirm prepares those selected choices; the assessment-wide confirmation button can also prepare them. Duplicate compact/detailed selections count only once. To change an answer, follow the card's detailed-review link. Changing filters clears hidden compact checkboxes but does not undo prepared radio decisions.

Blank/multiple readings and failed alignment are not compact single candidates. Failed alignment rows are grouped by sheet with a link to full-sheet evidence. The summary is navigation, not a manual realignment tool; unresolved rows still require review. Finalized assessments offer no bulk/compact editing controls.

## Automatic row retry

The detector first searches within five pixels. A boundary or low-score match triggers bounded retries at nine and fourteen pixels. Expanded candidates require correlation of at least 0.60 and may not reduce the previous best score, except for a 0.001 tolerance when the offset is identical (OpenCV window rounding). A boundary maximum or a failed base confidence check still flags alignment; weak-stroke recovery remains suppressed for failed registration. The 14-pixel cap is below half the configured Delia option and row spacing. This is specific to the supported sheet layout, not unrestricted deskewing.

Diagnostics include alignment_version=row-bounded-v2, offset, score and search radius. Successful expanded searches additionally retain initial and recovered diagnostics in alignment_recovery. Question evidence crops follow accepted local offsets; raw input files remain untouched. Existing assessment results are not automatically reprocessed or overwritten.

## Local validation, 29 October 2026

- Python suite: 88 tests, 87 passed; PostgreSQL integration skipped locally and covered by CI. Five JavaScript checks cover scope, manual preservation, lazy/missing images, duplicate compact/detail selection and roster clipboard parsing.
- Previously labelled 12-page development batch (240 answers): direct agreement remains 233/240, pending answers originally 63, balanced-v2 at 0.70: 61, balanced-v3: 54 and zero observed unflagged errors. This is a regression replay, not independent accuracy evidence.
- Six earlier sheets (600 positions): selections and cancellation suggestions unchanged.
- Simulated increasing vertical drift on the eighth development sheet: failed-alignment rows 8 -> 0, direct matches 11/20 -> 18/20, zero observed unflagged errors. The two remaining mismatches remain flagged multiple marks. The perturbation reflects the drift pattern observed in hosted diagnostics; this does not prove the exact production homography is fixed.
- Browser checks use synthetic rows: explicit compact selection/confirmation of warned singles saves those decisions while leaving excluded/untouched responses pending. No production teacher decisions or student data are modified.

After deployment, re-run the original PDF as a new assessment to verify the hosted alignment path. Preserve the reviewed assessment. Independent new-writer/scanner evaluation and broader pen-shape improvements remain outstanding; no automatic learning from teacher corrections is enabled.

## Modest review-clearance adjustment (balanced-v2)

This adjusts automatic clearance of review flags, not answer detection or grading. The density selection threshold remains unchanged. For an isolated single choice, the minimum row-match correlation stays at 0.70, minimum connected-stroke area 10 pixels (previously 12), with unchanged minimum density 0.08 and stroke span 7. Correlation is a template-match score, not a calibrated probability of a correct answer.

A generic stray-ink flag may also clear if the chosen option has at most 16 outside-ink pixels, every other option has at most 4 outside-ink pixels and at most 2 new core-ink pixels, and no option has a diagonal/cross clue. Missing spill measurements prevent this exception. Multiple/blank readings, possible cancellations/cross-outs, uncertain alignment and competing marks remain pending. Original review reasons and the auto-accept explanation are retained. The conservative configuration still keeps all flags.

On the same 240 labelled development answers, two additional readings clear review (one minor-spill case and one small isolated stroke): 63 -> 61 pending, no answer changes, all seven existing mismatches remain flagged. The six earlier sheets retain all 600 selections/suggestions, with 580 -> 578 pending positions (this includes deliberately unused blank positions). These are development/regression results, not independent validation or a guaranteed production review rate.

### Threshold comparison, 30 October 2026

The user selected a minimum row-match score of 0.70. Replay with the other balanced-v2 guards held fixed: 0.70 yields 61 pending answers; 0.65 and 0.60 each yield 57. No selections changed and all three trials have zero observed unflagged errors in the same labelled development batch. This comparison replays the review-clearance policy over saved detection evidence, not a fresh independent scan test. Lowering the score does not address the main workload: 54 of the 61 remaining rows at 0.70 have a single selected choice. Pen-shape and connected stray-ink discrimination need separate implementation and held-out validation before suppressing more warnings.

## Print-aware and compact-fill checks (balanced-v3 / stroke-v2.3)

The minimum row-match score remains **0.70**. Printed borders and letters plus their one-pixel halo are excluded from effective stray-ink counts. Raw outside-ink counts remain recorded and continue to feed existing cancellation evidence. The change does not alter density samples, mark selections or answer-key logic.

Connected-component measurements separate spill linked to new ink in the chosen box from detached ink. A one-pixel dilation is used only to bridge tiny gaps for connectivity; dilated pixels are never counted as ink or density. Normal minor-spill limits remain 16 selected-box pixels and 4 around other choices. A verified compact fill can extend to 24 selected-box spill pixels only when at most 2 are detached. Competing core ink remains capped at 2 pixels per other option.

A compact fill has at least 80% coverage of its inner sample and at most 2 new ink pixels beyond the fill body (vertical reach >= sample half-height + 4, horizontal reach >= sample half-width + 4). This geometry may explain a short diagonal cue in a dense fill. It cannot clear any actual cross clue, a diagonal clue on another option, multiple/blank responses, failed alignment or conservative mode. Minimum stroke area, span, density and 0.70 score still apply. Original flags and auto-accept explanations remain in the evidence. This is a narrow rule for compact fills, not a general handwriting classifier or automatic learning. Extended strokes and many irregular loops remain pending.

Development replay: 240 answers retain 233 direct matches, with pending answers 61 -> 54 relative to balanced-v2 at 0.70 (original baseline 63). All seven mismatches remain flagged; zero observed unflagged errors. The six earlier sheets retain all 600 selections and cancellation suggestions; their pending positions change 578 -> 577, including intentionally unused blanks. Tests cover halo-only residuals, attached/detached ink, known competing marks and 30/45/60-degree dark/faint crosses over fills. The same development material informed the changes, so these results do not replace a fresh held-out batch or hosted validation.

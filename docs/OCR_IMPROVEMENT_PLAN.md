# Handwritten metadata OCR improvement plan

Status: offline benchmark implemented on 2026-10-27; production engine/profile selection remains unchanged. See OCR_BENCHMARK.md for commands, measured diagnostics and remaining validation. This work is independent of the marking/review changes in PR #4.

## Problem and baseline

The current pipeline reads all five written fields from the registered 1192 x 1685 page. Tesseract uses one-line segmentation (--psm 7) and English plus Traditional Chinese when available. Class and class-number format checks run after recognition. Low-confidence/invalid readings require review. Apple Vision remains a macOS-only alternative.

The six existing development samples are not independent evaluation data. The prior live batch flagged 29 of 30 written fields unrecognized; this is a review-rate observation, not a character-accuracy measurement.

## Required scope

### Reproducible local benchmark
- [ ] Define a local-only labelled manifest with sample/writer/scanner codes, source page, field, expected transcription, blank/illegible status and development/held-out split.
- [ ] Benchmark the existing engine before changing it. Never use model guesses as ground truth.
- [ ] Report exact field accuracy separately for class, number, English/Chinese name and subject; character error rate for applicable text fields; false nonempty results on blank crops; review rate; wrong automatic identity acceptance.
- [ ] Measure timing and peak memory for a full worker process including OCR subprocesses, not just imported model size or detector-only RSS.
- [ ] Keep PDFs, crops, rosters, student identifiers, raw OCR outputs and reference transcriptions out of the public repository.

### Higher-quality crops and preprocessing
- [x] Preserve registration transforms and map field zones back to original-resolution pixels; avoid inventing extra detail by enlarging an already downsampled crop.
- [x] Retain the untouched evidence crop alongside any recognition variant.
- [ ] Evaluate grayscale/contrast variants, deskew and printed-border suppression without erasing faint strokes or characters crossing a border.
- [ ] Add blank-field detection with checks against faint handwriting; distinguish blank, illegible, error and recognized states.

### Field-specific recognition
- [x] Pass field context to OCR: class allows digits and uppercase letters; class number allows digits; names allow English/Traditional Chinese.
- [x] Preserve raw text and record normalized text separately. Do not silently replace O/0, I/1, S/5 or similar ambiguous characters to produce a plausible identity.
- [x] Validate class format and number format without treating a valid-looking result as proof of the correct student.
- [ ] Use assessment subject as comparison context, not as a substitute for the written subject.
- [ ] Preserve the signature image and attempted transcription. Decide its review policy explicitly; text recognition must never be represented as signature authentication.

### Engine comparison
- [ ] Add an optional local PaddleOCR adapter in a separate, pinned benchmark environment; compare it with Tesseract on identical crops/reference labels.
- [x] Record engine/model versions and preprocessing parameters. Confidence values from different engines are not directly interchangeable.
- [x] Keep production defaults unchanged until accuracy and resource checks pass.
- [ ] Treat cloud OCR as a later opt-in option requiring explicit authorization for named field images and provider, plus reviewed cost/data handling. No external uploads in this draft.

### Roster-assisted identity (separate milestone)
- [ ] Define assessment-scoped roster import and access controls before implementation.
- [ ] Compare class, number and name independently and flag conflicts instead of overriding written values.
- [ ] Show roster suggestions separately from raw written identity and preserve teacher decisions/audit history.
- [ ] Prevent silent assignment on duplicate, ambiguous or conflicting identities. Test wrong-but-readable class/number and English/Chinese name variants.

## Validation and merge gates
- [ ] Unit/integration coverage for format constraints, blank/faint/illegible crops, engine failures, raw-evidence preservation and conflicting identity candidates.
- [ ] Development benchmark results against the current main baseline.
- [ ] Independently labelled samples from additional writers/scanners, with held-out cases not used for tuning.
- [ ] Field-specific acceptance thresholds justified by observed error/review tradeoffs; no claims of calibrated probability without calibration.
- [ ] Hosted full-pipeline memory/throughput assessment against the current 512 MB service; no large OCR experiments alongside production requests.
- [ ] Google login, teacher ownership, private evidence access and correction/export behaviour remain intact.
- [ ] CI, changelog, deployment/configuration instructions and rollback guidance updated before enabling a new engine.
- [ ] Teacher pilot confirms fewer identity edits without increased wrong student matches.

Numerical release targets should be agreed after a reliable labelled baseline is established. No handwriting accuracy or hosting-capacity gain is claimed by this planning commit.

## First offline experiment

The 12-page batch produced 60 field crops and five Tesseract variants (300 readings); PaddleOCR recognition compared three image variants (180 readings). No registration/recognition errors occurred. Neither engine is approved for deployment: written-field reference labels and independent validation are outstanding. PaddleOCR process peak RSS was about 880 MB on macOS, exceeding the hosted service's 512 MB budget before adding the web worker. The >=70 confidence/format diagnostic is not accuracy or an engine-independent acceptance threshold. Blank-field detection, roster matching, calibrated thresholds and hosted capacity remain unimplemented/unvalidated.

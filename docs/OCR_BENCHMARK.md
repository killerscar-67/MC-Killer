# Offline handwritten-field OCR benchmark

This draft provides experiments, not a deployable OCR upgrade. Production still selects its existing engine automatically and uses the legacy recognition profile. Optional experiments do not assign identities, alter assessment records, or upload scans. All five written zones remain available, including signature; signature transcription is not authentication.

## Run Tesseract comparisons

Use a private output directory outside version control. Install the normal application dependencies and local Tesseract with English/Traditional Chinese language files. Run:

```sh
python -m mcmark.ocr_benchmark /private/path/sheets.pdf \
  --layout mcmark/layouts/delia-layout.json \
  --output /private/path/ocr-benchmark --engine tesseract
```

Alternatively install the optional `ocr-benchmark` extra and select `--engine tesserocr --tessdata /private/path/tessdata`. This binding was used locally because a standalone Tesseract binary was unavailable. It uses Tesseract 5.5.3; it is not evidence of identical results from the deployed binary. Python 3.9 macOS arm64 was used for that experiment. Pin language files by the SHA-256 values recorded in the private result; default system language files are not automatically hashed, so record their versions separately.

The tool compares legacy low-resolution crops/PSM7, low-resolution crops/field settings, original-resolution crops/PSM7, original-resolution crops/field settings, and original-resolution CLAHE/field settings. Class and number use PSM8 with restricted alphabets only in the experimental profile. No O/0 or I/1 substitutions are made. Original-resolution crops are warped directly from 300-DPI PDF renders using the validated registration transform, capped at 3x the layout scale and five million pixels per field. It retains grayscale evidence before contrast preprocessing.

Outputs include `ocr-results.json`, evidence crops and `expected-fields.template.json`. Reruns preserve an existing label template. Copy the template and transcribe what is actually written from the evidence; use explicit blank/illegible notes in a separate reference manifest. Candidate roster entries are comparison context, not evidence of a field's written contents. The current runner does not yet score reference labels or distinguish blank from illegible. That evaluator and an independently labelled held-out set remain release gates.

## Run the optional PaddleOCR comparison

Use a **separate Python 3.12 environment**, not the production worker. The local experiment used `paddleocr==3.3.2`, `paddlepaddle==3.3.1`, `paddlex==3.3.13`, and `opencv-contrib-python==4.10.0.84`. Install those pins and the benchmark's ordinary dependencies there. Download the official [PP-OCRv5_mobile_rec](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_rec) model into a local directory first. The runner requires local inference files and disables the model-host connectivity check; it does not select an online OCR API.

```sh
python -m mcmark.paddle_benchmark /private/path/ocr-benchmark/ocr-results.json \
  --model-dir /private/path/PP-OCRv5_mobile_rec \
  --output /private/path/ocr-benchmark/paddle-results.json
```

This uses recognition only on the same legacy, original-resolution and contrast crops, CPU, two threads and MKL-DNN disabled. Field-specific Tesseract segmentation/whitelists do not apply to PaddleOCR. It records model hashes and package versions. Process RSS measures this runner, not a full hosted web worker or aggregate subprocess memory. Platform/runtime differences prevent inferring Northflank capacity from these measurements.

## First experiment, 2026-10-27

Twelve sheets × five written fields = 60 fields. There are no confirmed written-field transcriptions yet, so **accuracy is not measured**. The existing threshold (minimum word confidence >=70 plus class/number format validation) is used only as a diagnostic. Confidence scales differ between engines and are not calibrated probabilities.

| Engine and crop/settings | Fields passing diagnostic /60 |
| --- | ---: |
| Tesseract, legacy | 5 |
| Tesseract, legacy crop + field settings | 2 |
| Tesseract, original crop + legacy settings | 2 |
| Tesseract, original crop + field settings | 0 |
| Tesseract, original crop + contrast/field settings | 0 |
| PaddleOCR, legacy crop | 17 |
| PaddleOCR, original crop | 17 |
| PaddleOCR, original crop + contrast | 11 |

Tesseract processed all 300 variants in 31.43 seconds with 545.3 MB parent peak RSS, including PDF registration/crop generation. PaddleOCR processed 180 existing crops in 13.75 seconds with 880.4 MB process peak RSS, including model loading but excluding downloads and crop generation. These are single local macOS runs, not equivalent throughput tests, production capacity claims or independently labelled accuracy results. Both finished without registration/recognition errors.

Higher resolution and restricted alphabets did not improve this diagnostic. PaddleOCR reads more fields with high confidence, but cannot be approved on confidence alone and exceeded the current 512 MB hosting budget. Neither experimental profile is enabled in the app.

Next: label field transcriptions, test blank/faint handwriting and wrong-but-readable identifiers, score field/character accuracy and false identity acceptance, gather independent writers/scanners, then assess engine-specific thresholds and whole-worker Linux memory. Roster assistance requires separate conflict handling, ownership checks and audit design. Do not lower production thresholds based on these counts.

## Privacy, validation and rollback

Never commit source PDFs, crop images, names, rosters, labels or raw OCR results to the public repository. Use private paths and restrict access to downloaded outputs. The benchmark performs local recognition; model downloads must happen separately without uploading field images.

Run `python -m unittest discover -s tests`. Tests cover original-coordinate crop transforms, bounds checks, default settings, raw-text preservation, invalid/low-confidence formats, Tesseract options/headerless TSV, local-model requirements and crop path containment. They use synthetic images and mocked engines, and do not download models.

No engine rollout is part of this draft; rollback consists of stopping the offline experiment. Future deployment must explicitly wire a validated profile/engine, pin models, measure full worker/subprocess memory and test teacher ownership, evidence access and exports before changing defaults.

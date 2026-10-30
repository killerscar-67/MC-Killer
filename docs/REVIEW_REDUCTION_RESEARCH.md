# Review-reduction research and validation — 30 October 2026

## Outcome

The final candidate, stroke-v2.5 / balanced-v5, requires **35 reviews out of 240 configured questions (14.58%)** on the existing labelled development batch. The previous PR #7 head required 47; the earlier shape-only version required 54. This meets the requested 10–15% range on this batch, without changing any detected selections or cancellation suggestions. Direct agreement remains 233/240 (97.08%); all seven mismatches require review, and all 205 automatically accepted readings match the labels.

This is evidence of no observed accuracy loss on the available material, not proof of an unchanged error rate on future scans. The material has already influenced development. Lower-contrast and compressed variants can exceed 15% review, and unresolved cancellation cases remain in synthetic stress tests. The detector never imposes a review quota to make the percentage look better. Existing assessments are not rewritten. This PR is not a hosted rollout.

## Research basis and decisions

| Method | Evidence and applicability | Decision |
| --- | --- | --- |
| Printed-template removal and careful registration | Loke et al. separate printed content from response ink and discuss artefacts and faint strokes. Their findings support measuring print and student ink separately; they do not validate our cancellation rules. | Retain reference subtraction, the printed halo and separately verified printed alignment. Preserve raw measurements. |
| Binary/grayscale agreement | Hernández-Mier et al. combine binary and grayscale evidence in their answer-sheet pipeline. Their forms differ from ours and do not establish cancellation-intent accuracy here. | Compare template-subtracted response ink at three darkness cutoffs and five nearby sample positions. |
| Spatial mark geometry | The Bayesian mark-array work uses pixel distribution, occupancy and aspect ratio. These are useful local descriptors even without fitting its full optimization model. | Measure connected-body width, height and bounding-box coverage for a narrow horizontal-fill exception. |
| Connected components and option context | OpenCV provides component labels and region statistics. A component wholly outside a box's expanded region differs from ink entering that answer box. | Exclude remote spill only beside an otherwise empty, unselected option, and only with stable response evidence. No colour or authorship assumption. |
| Selective classification / abstention | Risk–coverage research evaluates accepted-prediction error together with coverage. A low review rate alone is not evidence of accuracy. | Record review rate, direct agreement, errors among accepted readings and newly unflagged errors. Keep difficult cases pending. |
| Lower global thresholds | Earlier trials of 0.65 and 0.60 produced the same 57 pending readings under the older policy. They did not solve shape ambiguity. | Keep the acceptance correlation minimum at 0.70. No further global density relaxation. |
| Red-ink removal | Colour does not establish whether ink belongs to the teacher or student. Students may use coloured ball pens. | Do not erase marks by colour in the production detector. |
| Trained mark classifier / vision model | A classifier might improve loop/tick discrimination, but the available final-answer labels do not separately label stroke shape or cancellation intent. Reusing these pages for training and validation would inflate apparent performance. | Defer automatic learned clearance until independently labelled writers/scanners and a separate calibration/test set exist. No student images sent to an external AI service. |

Sources: [Loke et al., PLOS ONE, 2018](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0206420); [Hernández-Mier et al., Journal of Imaging, 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12470569/); [Bayesian optical-mark-array research, IEICE](https://globals.ieice.org/en_transactions/information/10.1587/transinf.2024IIP0010/_f); [OpenCV connected-component and shape documentation](https://docs.opencv.org/4.9.0/d3/dc0/group__imgproc__shape.html); [Geifman and El-Yaniv, NeurIPS 2017](https://proceedings.neurips.cc/paper/2017/hash/4a8423d5e91fda00bb7e46540e2b0cf1-Abstract.html); [selective calibration, Fisch et al., 2022](https://arxiv.org/abs/2208.12084).

The implementation is a local engineering adaptation of these ideas, not a reproduction of any paper's reported accuracy. No third-party recognition code or trained model was copied.

## Implemented checks

### Remote ink beside empty options

Component connectivity is measured before masking printed borders, because masking can split a stroke at the box edge. A remote component must never enter the answer box plus a three-pixel margin. Its effective outside-ink count may be excluded only for an unselected option with density below 0.08, no more than two new core-ink pixels and no diagonal/cross evidence. The selected option's spill is never subtracted this way. Original counts and review reasons remain recorded, alongside remote_outside_ink_pixels and remote_ink_excluded_options.

This handles an annotation beside an empty option without interpreting its colour or deciding who wrote it. Any component that enters the protected box region, any competing core mark, and missing/failed stability evidence retain the warning.

### Fifteen-way stability check

A flagged single choice is sampled at its accepted position and at one-pixel offsets left, right, up and down. Each position is checked at the configured darkness cutoff and at cutoffs 30 units lighter/darker (normally 120, 150 and 180). Template pixels and their one-pixel halo are excluded; at least eight usable pixels are required per sample.

At every variant, the chosen option must retain at least 0.12 new-ink coverage, other options must remain below 0.08 and the chosen-to-runner-up margin must be at least 0.12. At the central position, all cutoff variants must meet the configured density threshold, normally 0.35. These are robustness measurements, not calibrated confidence probabilities or statistically independent votes. The check gates the new exceptions; it never selects a different answer.

A first trial using raw density was sensitive to printed borders entering the jittered windows. Comparing new ink against the same reference windows removed that artefact without lowering the acceptance cutoff.

### Horizontal fill geometry

The connected raw-ink body touching the inner sample must be a single component, have at least 70% inner coverage, width at least the sample width, height no more than twice the sample height, aspect ratio at least 2.5 and at least 45% bounding-box coverage. Clipped bodies/ink at the inspection boundary are rejected. Stable evidence, sufficient registration and absence of every diagonal/cross clue are also required.

Only such a body can use the existing 24-pixel spill cap and bypass the detached-spill guard on the chosen option. This does not apply to loops, vertical strokes, crossings or ambiguous competing marks. The ordinary 16-pixel limit remains otherwise. auto_accept_reason identifies this exception.

### Additional cancellation vetoes

The broader investigation found failures that existed before these changes. A separate radial check now examines opposite diagonal arms over slopes 0.45–2.2, with ink beyond the fill core and support along each arm. Sparse, tall bodies with both straight-diagonal supports also require review. These add unresolved_cross_geometry; they do not discard a choice or invent a cancellation suggestion.

More than two new core-ink pixels in an unselected option now produce unresolved_competing_ink even when the stroke misses both the density and thin-candidate gates. Both new reasons block automatic eligibility in the bulk selector. Explicit image-based human review remains available.

## Experiments and ablations

Every row below uses the same 240-answer development batch; these are sequential engineering trials, not independent evaluations.

| Trial | Pending | Decision |
| --- | ---: | --- |
| Shape-only PR #7 version | 54 | Earlier baseline |
| Printed-anchor verification with detached-spill guard | 47 | Starting head for this work |
| Remote-option ink context alone | 36 | Promising; add stability verification before use |
| Remote context + horizontal geometry + raw-density stability | 36 | Border contamination in jittered windows; revise measurement |
| Same features with template-subtracted stability | 33 | Meets target, but continue cancellation stress |
| Wider radial cancellation veto | 34 | Keep the extra review for safety |
| Sparse-cross veto and unclipped-body requirement | **35** | Final candidate |

A previous permissive anchor trial that produced 39 reviews failed an existing faint-cross regression and was rejected. The final candidate has no changed selections or suggestions on the original batch. The seven incorrect direct readings are still reviewed; 28 additional correct readings remain flagged. Review-reason counts overlap, so they must not be summed as distinct questions.

## Fresh PDF registration and degradation checks

The reproducible benchmark rerendered and registered the original PDF, then compared the previous head and candidate on the same registered images. The answer key was not used. Labels are confirmed student selections.

| Input condition | Previous head pending | Candidate pending | Candidate rate | Candidate direct agreement | Unflagged errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original | 47 | **35** | **14.58%** | 233/240 | 0 |
| Brightness +20 | 34 | 34 | 14.17% | 232/240 | 0 |
| Contrast ×0.8, offset +35 | 50 | 39 | 16.25% | 233/240 | 0 |
| Gaussian blur, sigma 0.6 | 39 | 34 | 14.17% | 233/240 | 0 |
| JPEG quality 70 | 50 | 37 | 15.42% | 233/240 | 0 |
| Translation +1, −1 pixels | 47 | 35 | 14.58% | 233/240 | 0 |

There are 1,440 derived readings here, not 1,440 independent students. No condition introduced an unflagged error. The brightness variant changes one additional direct reading, which remains flagged in both versions. Poorer inputs can legitimately need more than 15% review.

On this local machine, original-batch detection took about 0.79 seconds versus 0.53 seconds for the previous head, excluding rendering/registration. Registration took approximately 1.07 seconds for the 12 pages. These are single-run observations, not Northflank performance guarantees. The changes use small image regions and existing NumPy/OpenCV dependencies; no inference service or large model is added.

## Cancellation stress and remaining failures

The synthetic matrix contains 360 combinations: isolated X, X over a fill, X over a loop and a separate answer plus X; five angles, three ink intensities, two thicknesses and three arm lengths. Faint ink is combined with existing fill using the darker value, so a faint pen does not artificially lighten a black fill.

| Synthetic family | Cases | Previous automatic acceptances | Candidate automatic acceptances |
| --- | ---: | ---: | ---: |
| Isolated X | 90 | 5 | **0** |
| X over a fill | 90 | 20 | 12 |
| X over a loop | 90 | 8 | 5 |
| Another answer plus faint X | 90 | 4 | **0** |
| Total | 360 | 37 | **17** |

No case previously held for review became automatically accepted. Nevertheless, **17 synthetic cancellation scenarios are still accepted**. They are residual blind spots, largely shallow crossings over existing ink; they must not be described as passed cancellation tests. A crossing mostly hidden inside a fill may have little observable evidence, and this experiment cannot establish student intent. The benchmark records each remaining configuration for follow-up. This is why a zero-error or future-accuracy guarantee would be unjustified even though the development review target is reached.

The six earlier sheets retain all 600 selections and cancellation suggestions. Their pending positions remain 572, including deliberately unused questions; those unused positions are not added to the denominator to lower the claimed review rate. The simulated drift case remains 18/20 direct matches, no alignment failures, and both mismatches flagged.

## Validation limits and rollout

- 101 Python tests: 100 passed, one PostgreSQL integration test skipped locally; five JavaScript tests passed. CI separately covers PostgreSQL.
- Zero observed errors among 205 accepted development readings does not prove zero risk. Even under an independent-identically-distributed assumption, 0/205 would permit an approximately 1.45% one-sided upper 95% error bound. Reuse for tuning and clustering by writer mean that assumption does not hold here; the number is illustrative only.
- The 0.70 score is template correlation, using either whole-row evidence or the guarded printed-anchor check. It is not “70% confidence.” No future batch is promised a fixed review rate.
- Before a broad rollout, freeze this candidate and test new labelled sheets from independent writers/scanners, including blanks, faint marks, loops, ticks, cross-outs and multi-selections. Keep these sheets out of tuning. Count accepted errors, review rate and family-specific failures; fail the release check on any newly unflagged error.
- After deployment, upload the PDF as a **new** assessment and compare with confirmed labels. Preserve the existing reviewed assessment and teacher decisions. Do not automatically learn rules from corrections or use the correct-answer key to resolve student marks.

## Reproducing the benchmark

Use a trusted baseline source from commit c7c905e0b5b1d30665478c0785199b25218de6d4 and the private PDF/confirmed response-label JSON. The baseline file is executed as Python; do not pass an untrusted downloaded file. Results include page/question-level response data and must remain private.

```sh
python tools/benchmark_review_reduction.py \
  --pdf /private/path/batch.pdf \
  --labels /private/path/confirmed-response-labels.json \
  --baseline-vision /private/path/baseline-vision.py \
  --questions 20 --perturbations --synthetic \
  --output /private/path/review-benchmark.json
```

The tool validates complete, unique label coverage, rerenders/registers the PDF, records source hashes and reports original/degraded results plus all unresolved synthetic configurations. A missing label is never interpreted as blank. No production data, grading decisions or remote services are changed.

# Cancellation-regression follow-up — 2 November 2026

## Outcome

Stroke-v2.6 / balanced-v6 flags all **17 previously accepted cancellation cases**. In the original 360-case synthetic matrix, cancellation acceptances change **17 -> 0**. The 17 patterns were also moved across seven question positions and all four choices: **0 accepted out of 476 checks**. All 28 ordinary-fill controls at those positions remain accepted. These tests overlap and are synthetic; they are not independent writers or proof of general cancellation accuracy.

Fresh registration of the private 12-page PDF gives **41/240 reviews (17.08%)**, up from 35. Direct agreement is unchanged at 233/240; all seven mismatches stay flagged, all 199 automatically accepted readings match the confirmed labels, and no selections or cancellation suggestions change. The six additional reviews are the measured cost of stronger cancellation protection. The earlier 14.58% development rate no longer describes the latest candidate. No review quota is applied.

## What changed

Short shallow crossings can leave only a few visible pixels outside a dark fill. A faint stroke over a dark printed border may expose some arms while others blend into the border. The older detector's extra-ink cutoff and diagonal extent requirements missed this evidence.

A separate review veto now checks shallow opposing tips using the template-relative image:

- Tip evidence must darken the reference by more than eight grayscale units and remain below intensity 200. Stronger context evidence uses a difference greater than 18. These cutoffs apply only to the new ambiguity check; answer-density sampling, weak-mark recovery and the 0.70 review-clearance correlation minimum are unchanged.
- Both neighbouring pixel centres are checked for fractional layout coordinates. This avoids a one-pixel translation/parity dependence without moving answer samples.
- A short four-tip pattern must have a clear region between its outer tips: at most 20% stronger context ink. Longer paired tips must lie beyond an ordinary loop's width and have at least two supporting pixels per arm.
- A dense fill may also be ambiguous when tiny, separated corner lobes have mirrored evidence that is visible or obscured by dark template print. Each visible lobe is limited to three pixels on one row and a two-pixel horizontal span; at least one mirrored location must be obscured by print. Broad overfill alone does not satisfy this exception.

Evidence fields include shallow_cross_clue, shallow_tip_mode and short/long tip counts. Positive evidence adds the existing unresolved_cross_geometry review reason. It **does not classify the choice as cancelled, discard a mark, change a score or create a cancellation suggestion**. The teacher decides from the retained image. The bulk automatic selector already excludes this warning; explicit image-based review remains available.

## Tests and measurements

| Check | Previous head | Latest candidate |
| --- | ---: | ---: |
| Original synthetic cancellation matrix, 360 cases | 17 automatic acceptances | **0** |
| Reported 17 patterns across seven question positions and A–D | — | **0/476 accepted** |
| Ordinary fills at the same 28 positions | — | **28/28 accepted** |
| Original labelled PDF, pending questions | 35/240 | **41/240** |
| Original labelled PDF, direct agreement | 233/240 | **233/240** |
| Original labelled PDF, unflagged errors | 0 observed | **0 observed** |

Fresh PDF registration followed by the same derived-image checks gives:

| Condition | Pending | Rate | Direct agreement | Unflagged errors |
| --- | ---: | ---: | ---: | ---: |
| Original | 41 | 17.08% | 233/240 | 0 |
| Brightness +20 | 38 | 15.83% | 232/240 | 0 |
| Contrast ×0.8, offset +35 | 59 | 24.58% | 233/240 | 0 |
| Gaussian blur, sigma 0.6 | 40 | 16.67% | 233/240 | 0 |
| JPEG quality 70 | 45 | 18.75% | 233/240 | 0 |
| Translation +1, −1 pixels | 41 | 17.08% | 233/240 | 0 |

These 1,440 derived readings reuse the same writers. Lower contrast produces substantially more warnings with the sensitive veto; this is an outstanding workload limitation, not an accuracy claim. A local printed-band brightness/contrast normalization trial gave no measurable improvement in these counts and was not included.

All 600 selections and cancellation suggestions on the six earlier sheets remain unchanged. Their pending positions change 572 -> 573, including deliberately unused blanks. The drift test stays at 18/20 direct matches with no alignment failures and both mismatches flagged.

Local checks: **107 Python tests, 106 passed and one PostgreSQL integration skip**, plus **five JavaScript tests passed**. The new regression module contains six test methods covering the original failures, fractional/positional variants, preservation of another selected answer and ordinary-fill controls. The layout checks deliberately extend beyond the question/option used by the original synthetic matrix.

## Reproduction and limits

Run the synthetic regression module with no student data:

```sh
python -m unittest tests.test_cancellation_regressions -v
```

For the fresh private PDF and degradation comparison, use tools/benchmark_review_reduction.py with a trusted baseline vision.py from commit e4c0f15d3ca47791ae735aa33fb519a3f2637743. Pass the independently confirmed response-label JSON, never the correct-answer key. See the benchmark instructions in REVIEW_REDUCTION_RESEARCH.md. Outputs contain private responses and must remain outside Git.

Earlier trials illustrate the tradeoff: a broad bilateral-tip rule eliminated the location-test misses but increased the real batch to 66 reviews. It was rejected. The retained rule requires specific mirrored print/ink context and narrow lobes; it gives 41 reviews while covering the recorded cancellation regressions.

The finite synthetic tests do not establish a universal zero-error guarantee. Crossings fully hidden inside existing ink may be unobservable, and genuinely ambiguous marks still need human judgement. Independent writer/scanner evaluation and a fresh hosted assessment remain necessary before a wider rollout. This change does not merge/deploy the PR or reprocess existing teacher decisions.

# Manual-search threshold calibration

Recorded on 2026-09-16 using `text-embedding-3-small`, the current nine-chunk
synthetic manual index, and cosine similarity. These results evaluate retrieval
evidence only; they do not evaluate an LLM-generated answer.

## Calibration results

| Case | Category | Top score | Top section | Expected outcome |
| --- | --- | ---: | --- | --- |
| `cal-relevant-door` | relevant | 0.532200 | `SV-DOOR-02` | retrieve |
| `cal-paraphrased-battery` | paraphrased | 0.707813 | `SV-BATTERY-01` | retrieve |
| `cal-relevant-tyre` | relevant | 0.540366 | `SV-TYRE-01` | retrieve |
| `cal-relevant-cable` | relevant | 0.530787 | `GPU-CABLE-01` | retrieve |
| `cal-paraphrased-leak` | paraphrased | 0.650336 | `FLT-LEAK-01` | retrieve |
| `cal-borderline-routine` | borderline | 0.379912 | `SV-TYRE-01` | abstain |
| `cal-wrong-model` | wrong-model | 0.381753 | `SV-DOOR-02` | abstain |
| `cal-unsupported-oil` | unsupported | 0.207559 | `SV-TYRE-01` | abstain |
| `cal-unsupported-radio` | unsupported | 0.231726 | `SV-BATTERY-01` | abstain |

The lowest supported calibration score was `0.530787`; the highest negative
score was `0.381753`. The application threshold was frozen at `0.40` before
the held-out cases were run. This round value rejects every calibration
negative while retaining every calibration positive.

## Held-out results at the frozen 0.40 threshold

| Case | Category | Top score before threshold | Result | Expected section |
| --- | --- | ---: | --- | --- |
| `held-paraphrased-door` | paraphrased | 0.424157 | retrieve | `SV-DOOR-01` |
| `held-paraphrased-panel` | paraphrased | 0.514501 | retrieve | `GPU-PANEL-01` |
| `held-relevant-fork` | relevant | 0.461866 | retrieve | `FLT-FORK-01` |
| `held-wrong-model` | wrong-model | 0.279983 | abstain | none |
| `held-unsupported-coolant` | unsupported | 0.220427 | abstain | none |

All five held-out cases passed without changing the threshold.

## Limitations

- The corpus and evaluation set are deliberately small and synthetic.
- The separation margin is narrow: the threshold is only about 0.018 above
  the highest calibration negative, so new manuals or questions require a new
  calibration set rather than an informal threshold adjustment.
- Cosine similarity measures semantic proximity, not factual answerability.
- A relevant superseded passage can outrank a current passage. Version labels
  make that visible, but a later answer layer must not present superseded text
  as current guidance.
- These results are learning-POC evidence, not production validation, a safety
  certification, or evidence of generative answer quality.

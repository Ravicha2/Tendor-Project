# ADR 0002: Three-Arm Evaluation (baseline / OCR / OCR+VLM)

## Status

Accepted

## Context

ADR 0001 defined a 2-arm comparison: baseline (no OCR, no VLM) vs improved (VLM only, no OCR). This conflates two independent variables: OCR and VLM picture description. For council meeting minutes that are often scanned PDFs, the realistic upgrade path is OCR first, then VLM on top of OCR. We need to isolate the effect of each.

## Decision

Replace the 2-arm design with a 3-arm design:

| Arm | `do_ocr` | `do_picture_description` | Purpose |
|---|---|---|---|
| `baseline` | False | False | Text layer only, no vision |
| `ocr` | True | False | OCR recovers text from scanned pages |
| `ocr_vlm` | True | True | OCR + VLM describes figures/charts |

The `improved` arm (`do_ocr=False`, `do_picture_description=True`) is dropped entirely. It tested an unrealistic configuration: VLM without OCR, which is not how meeting minutes are processed in production.

## Consequences

- Each arm isolates one variable: `baseline` vs `ocr` shows the effect of OCR; `ocr` vs `ocr_vlm` shows the effect of VLM on top of OCR.
- Results directory structure: `results/baseline/`, `results/ocr/`, `results/ocr_vlm/`. The old `results/improved/` is no longer produced.
- Extraction (LangExtract) remains constant across all three arms.
- Passing `"improved"` as an arm name now raises `ValueError`.
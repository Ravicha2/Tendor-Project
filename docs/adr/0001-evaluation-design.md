# ADR 0001: Evaluation Design for Document Parsing Comparison

> **Note**: Decisions 2 and 3 (arm configuration) have been superseded by [ADR 0002](0002-three-arm-evaluation.md), which expands from 2 arms to 3 (baseline, ocr, ocr_vlm).

## Status

Accepted

## Context

Tendor needs evidence on whether a better document-parsing layer measurably improves procurement signal extraction over a sensible baseline. This is a take-home evaluation with a 1-2 day timeframe.

## Decisions

### 1. Definition of "better"

Composite of three dimensions:

- **Signal count**: raw signals extracted per arm per document, with confidence-tier breakdown
- **Sampled precision**: stratified random sample of ~30 signals (1 per confidence tier per document per arm), each judged actionable or noise. Precision is fraction of actionable signals in the sample.
- **Field accuracy**: for matching signals across arms, correctness of budget_value, asset_or_location, and category

No golden dataset. Annotating procurement signals requires domain expertise the author lacks. Sampled precision is a pragmatic substitute: it measures whether extracted signals are real procurement opportunities without requiring exhaustive ground truth.

### 2. Baseline arm: Docling standard pipeline, no OCR, no vision

Docling `StandardPdfPipeline` with `do_ocr=False`, `PyPdfiumDocumentBackend`, `do_picture_description=False`. Keeps table structure extraction (TableFormer), HTML support, and section-aware parsing. Represents the best text-and-structure-only parser. Same engine as the other arms, isolating OCR and VLM capabilities as variables.

No local OCR (EasyOCR/Tesseract). No VLM. Text extraction from PDF text layer only.

> **Superseded**: See [ADR 0002](0002-three-arm-evaluation.md) for the current 3-arm design (baseline, ocr, ocr_vlm).

### 3. Improved arm: Docling standard pipeline + VLM picture description via OpenRouter

> **Superseded**: This arm has been replaced by `ocr` and `ocr_vlm` in [ADR 0002](0002-three-arm-evaluation.md). The `improved` arm (no OCR, VLM only) has been dropped; the new arms isolate OCR and VLM as independent variables.

VLM prompt: domain-specific, procurement-aware. "Describe this image. Focus on any project names, budget figures, locations, procurement indicators, or council decisions visible."

Directly tests the brief's hypothesis: whether recovering information from figures, charts, maps, and scanned pages improves signal extraction.

### 4. Extraction engine: LangExtract (both arms, constant)

Same model (`google/gemini-3.1-flash-lite` via OpenRouter), same prompt, same schema. Parser is the only variable: VLM picture description on vs off.

Google's langextract library for structured extraction with source grounding. Source grounding maps to the brief's `evidence_excerpt` requirement.

Schema mapping: `signal_type` to LangExtract's `extraction_class`, `evidence_excerpt` to `extraction_text`, remaining 10 fields to `attributes`. Type coercion (numbers, arrays, floats) handled in post-processing.

### 5. Validation: stratified sampled signal review

No golden dataset. Annotating procurement signals from council documents requires domain expertise in tendering that the author does not have. Without that expertise, manual annotation produces unreliable ground truth: under-counting real signals (not knowing what counts) and over-counting marginal ones (not knowing what does not).

Instead, a stratified random sample of ~30 signals (roughly 1 per confidence tier per document per arm, where available) is manually reviewed. Each signal is judged as **actionable** (a real procurement opportunity a supplier could act on) or **noise** (too vague, not procurement-related, or a duplicate). Precision is the fraction of actionable signals in the sample.

### 6. Evaluation scope

- **All docs**: Raw signal counts, confidence score distributions, structural comparison (table/text preservation), parse latency, token cost
- **All docs**: Sampled precision (stratified random sample, actionable vs noise)
- **Doc 05 (image-heavy)**: Deep-dive on VLM-specific signals, deduplication, and misattribution analysis

### 7. Negative findings required

The brief asks for honest assessment of where the improved parser does NOT help or costs too much. Explicitly report: cases where baseline matches or beats improved parser, latency cost, and production trade-offs. Report misattributed signals (VLM reads text correctly but misinterprets context) and signal count inflation from duplicates.

### 8. Project structure

Flat layout, uv for package management:

```ini
Tendor_project/
├── documents/           # Source docs
├── src/
│   ├── parse.py        # Parser harness: baseline + improved
│   ├── extract.py      # LangExtract extraction with signal schema
│   └── evaluate.py     # Compare outputs against golden, compute metrics
├── results/            # Parser + extraction results (gitignored)
├── docs/adr/           # Architecture decision records
├── writeup.md          # 1-3 page write-up
├── pyproject.toml      # Dependencies (uv)
└── README.md           # Setup + run instructions
```

### 9. Output format: Markdown + sidecar metadata JSON

Each document produces two files in `results/<arm>/`:
- `<doc_name>.md`: Markdown output from Docling's `export_to_markdown()`. Fed to LangExtract for signal extraction.
- `<doc_name>_meta.json`: Metadata including parse time, page count, table count, image count, and VLM picture descriptions (ocr_vlm arm only). Used for evaluation and tracing signal sources.

All three arms produce the same file structure. The only difference is the metadata JSON includes `picture_descriptions` in the `ocr_vlm` arm.

> **Updated**: See [ADR 0002](0002-three-arm-evaluation.md) for the current arm definitions.

- LangExtract schema mapping: can it handle budget_value (number), likely_supplier_categories (array), confidence_score (0-1 float)? Resolve during first extraction test.
- OpenRouter config: API key, rate limits. Resolve during implementation.
- VLM prompt for picture description: domain-specific, procurement-aware. Resolved: "Describe this image. Focus on any project names, budget figures, locations, procurement indicators, or council decisions visible."
- Which 3 sections to spot-check in Brisbane hard doc. Resolve after inspecting document structure.
- LangExtract chunking config (max_char_buffer, extraction_passes) per doc size. May need tuning.

## Risks

- **PyMuPDF4LLM removed from evaluation**: Original baseline conflated multiple variables (table handling, HTML support, OCR). Isolated to single variable: VLM vision capability. PyMuPDF4LLM comparison can be added later if needed.
- **VLM picture description prompt**: A generic "describe this image" prompt may miss procurement-relevant content. May need a domain-specific prompt. Test early.
- **VLM non-determinism**: Picture descriptions vary between runs. Commit actual results, use temperature=0 if supported, note in write-up.
- **Extraction LLM non-determinism**: LangExtract results also vary. Same mitigation: commit actual results, use temperature=0.
- **API costs**: VLM calls (gemini-2.5-pro @ $1.25/$10 per 1M) for ~20-30 images + extraction calls (gemini-3.1-flash-lite @ $0.25/$1.50 per 1M) for full doc text. Estimate under $5 total.
- **Easy doc shows no difference**: Valid finding, not a failure. Medium and hard docs are where vision should show gains.
- **Docling install**: Heavy ML deps even without OCR (PyTorch for TableFormer). Test install early.

## Assumptions

- Docling runs on CPU without GPU (4 docs is small scale).
- Docling's PyPdfiumDocumentBackend fully disables OCR when do_ocr=False (confirmed in GitHub discussions).
- VLM via OpenRouter can handle all image content in the 4 docs without rate limiting issues.
- User has/will set up OpenRouter API access (gemini-2.5-pro for VLM, gemini-3.1-flash-lite for extraction).
- Easy and medium docs contain enough procurement signals to be meaningful.
- User can read council docs well enough to build ~25-35 signal golden sample.
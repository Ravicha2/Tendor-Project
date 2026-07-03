# ADR 0001: Evaluation Design for Document Parsing Comparison

## Status

Accepted

## Context

Tendor needs evidence on whether a better document-parsing layer measurably improves procurement signal extraction over a sensible baseline. This is a take-home evaluation with a 1-2 day timeframe.

## Decisions

### 1. Definition of "better"

Composite of three dimensions:

- **Recall gain**: count of valid signals found by improved parser that baseline missed (confirmed against manual golden sample)
- **Field accuracy**: for signals both parsers find, correctness of budget_value, asset_or_location, and category
- **Table-specific recovery**: signals that exist only in table content, which baseline mangles

Not just raw signal count, which can be inflated by loose extraction.

### 2. Baseline arm: Docling standard pipeline, no vision

Docling `StandardPdfPipeline` with `do_ocr=False`, `PyPdfiumDocumentBackend`, `do_picture_description=False`. Keeps table structure extraction (TableFormer), HTML support, and section-aware parsing. Represents the best text-and-structure-only parser. Same engine as the improved arm, isolating vision capability as the only variable.

No local OCR (EasyOCR/Tesseract). No VLM. Text extraction from PDF text layer only.

### 3. Improved arm: Docling standard pipeline + VLM picture description via OpenRouter

Same Docling `StandardPdfPipeline` with table structure, HTML, etc., plus `PictureDescriptionApiOptions` pointing to OpenRouter with `google/gemini-2.5-pro`. The VLM describes charts, maps, figures, and reads text from scanned/image pages. No local OCR dependency; the VLM handles both text-in-image and visual understanding.

VLM prompt: domain-specific, procurement-aware. "Describe this image. Focus on any project names, budget figures, locations, procurement indicators, or council decisions visible."

Directly tests the brief's hypothesis: whether recovering information from figures, charts, maps, and scanned pages improves signal extraction.

### 4. Extraction engine: LangExtract (both arms, constant)

Same model (`google/gemini-3.1-flash-lite` via OpenRouter), same prompt, same schema. Parser is the only variable: VLM picture description on vs off.

Google's langextract library for structured extraction with source grounding. Source grounding maps to the brief's `evidence_excerpt` requirement.

Schema mapping: `signal_type` to LangExtract's `extraction_class`, `evidence_excerpt` to `extraction_text`, remaining 10 fields to `attributes`. Type coercion (numbers, arrays, floats) handled in post-processing.

### 5. Golden sample: manual annotation on easy + medium docs

Two-pass approach: read documents manually first to build oracle ground truth, then compare both parser outputs against it. Easy doc (~10 pages, ~5-10 signals) and medium doc (~31 pages, ~10-20 signals).

Hard doc (115 pages): spot-check 3 signal-rich sections + structural comparison (table preservation stats, text recovery stats). No full golden sample.

HTML doc (39 KB): structural comparison + qualitative notes only.

### 6. Evaluation scope

- **Easy + Medium**: Full golden sample (recall, field accuracy, table recovery)
- **Hard**: Spot-check 3 sections + structural comparison
- **HTML**: Structural comparison + qualitative notes
- **All docs**: Parsing time per page (cost/latency data)

### 7. Negative findings required

The brief asks for honest assessment of where the improved parser does NOT help or costs too much. Explicitly report: cases where baseline matches or beats improved parser, latency cost, and production trade-offs.

### 8. Project structure

Flat layout, uv for package management:

```ini
Tendor_project/
├── documents/           # Source docs
├── golden/             # Manually annotated golden samples (JSON)
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
- `<doc_name>_meta.json`: Metadata including parse time, page count, table count, image count, and VLM picture descriptions (improved arm only). Used for evaluation and tracing signal sources.

Both arms produce the same file structure. The only difference is the metadata JSON includes `picture_descriptions` in the improved arm.

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
# Tendor POC: Document Parsing Comparison

Does a better document-parsing layer measurably improve procurement signal extraction?

## Setup

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Run

```bash
# Step 1: Parse all documents (baseline, ocr, ocr_vlm)
uv run python src/parse.py

# Step 2: Extract signals from all parser outputs
uv run python src/extract.py

# Step 3: Evaluate against golden sample
uv run python src/evaluate.py
```

## Project structure

- `documents/` - source PDFs and HTML
- `golden/` - manually annotated golden samples
- `results/` - parser output and extraction results (gitignored)
- `src/parse.py` - baseline, ocr, and ocr_vlm arms via Docling
- `src/extract.py` - LangExtract signal extraction (same config all arms)
- `src/evaluate.py` - compare arms against golden sample
- `docs/adr/` - decision records

## Evaluation design

See [ADR 0001](docs/adr/0001-evaluation-design.md).
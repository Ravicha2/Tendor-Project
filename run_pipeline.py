"""Run the full Tendor pipeline: parse → extract for all documents and arms.

Usage:
    uv run python run_pipeline.py [--arms baseline ocr ocr_vlm] [--skip-parse] [--skip-extract]
"""

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DOCUMENTS = Path("documents")
VALID_ARMS = ("baseline", "ocr", "ocr_vlm")


def run_parse(arms: list[str], doc_paths: list[Path]) -> None:
    from src.parse import parse_document

    for arm in arms:
        print(f"\n=== PARSE: {arm} ===")
        for doc in doc_paths:
            print(f"  Parsing {doc.name} ({arm})...", flush=True)
            start = time.monotonic()
            md, meta = parse_document(doc, arm=arm)
            elapsed = time.monotonic() - start
            print(f"  -> {md.name}, {meta.name} ({elapsed:.1f}s)")


def run_extract(arms: list[str], doc_names: list[str]) -> None:
    from src.extract import extract_signals

    for arm in arms:
        print(f"\n=== EXTRACT: {arm} ===")
        for name in doc_names:
            print(f"  Extracting {name} ({arm})...", flush=True)
            start = time.monotonic()
            try:
                out = extract_signals(arm, name)
                elapsed = time.monotonic() - start
                print(f"  -> {out.name} ({elapsed:.1f}s)")
            except FileNotFoundError as e:
                print(f"  -> SKIP: {e}")
            except Exception as e:
                print(f"  -> ERROR: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full Tendor pipeline")
    parser.add_argument(
        "--arms", nargs="+", choices=VALID_ARMS, default=list(VALID_ARMS),
        help="Which arms to run (default: all)",
    )
    parser.add_argument("--skip-parse", action="store_true", help="Skip the parse stage")
    parser.add_argument("--skip-extract", action="store_true", help="Skip the extract stage")
    args = parser.parse_args()

    doc_paths = sorted(DOCUMENTS.glob("*"))
    doc_names = [p.stem for p in doc_paths]

    if not doc_paths:
        print("No documents found in ./documents/", file=sys.stderr)
        sys.exit(1)

    print(f"Documents: {', '.join(doc_names)}")
    print(f"Arms: {', '.join(args.arms)}")

    if not args.skip_parse:
        run_parse(args.arms, doc_paths)

    if not args.skip_extract:
        run_extract(args.arms, doc_names)

    print("\nDone.")


if __name__ == "__main__":
    main()
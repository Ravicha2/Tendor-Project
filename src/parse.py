"""Parser harness: baseline and improved arms via Docling."""

import json
import os
import time
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, PictureDescriptionApiOptions
from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
from docling.document_converter import DocumentConverter, PdfFormatOption, HTMLFormatOption

PROCUREMENT_PROMPT = (
    "Describe this image. Focus on any project names, budget figures, "
    "locations, procurement indicators, or council decisions visible."
)

VALID_ARMS = ("baseline", "improved")


def _build_converter(arm: str) -> DocumentConverter:
    if arm not in VALID_ARMS:
        raise ValueError(f"arm must be one of {VALID_ARMS}, got '{arm}'")

    pdf_opts = PdfPipelineOptions(
        do_ocr=False,
        do_picture_description=arm == "improved",
        generate_picture_images=arm == "improved",
        enable_remote_services=arm == "improved",
    )

    if arm == "improved":
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        pdf_opts.picture_description_options = PictureDescriptionApiOptions(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
            params={"model": "google/gemini-2.5-pro"},
            prompt=PROCUREMENT_PROMPT,
            timeout=60,
            picture_area_threshold=0.0,
        )

    format_options = {
        InputFormat.PDF: PdfFormatOption(
            pipeline_options=pdf_opts,
            backend=PyPdfiumDocumentBackend,
        ),
        InputFormat.HTML: HTMLFormatOption(),
    }

    return DocumentConverter(format_options=format_options)


def parse_document(
    path: Path | str,
    arm: str,
    out_dir: Path | str | None = None,
) -> tuple[Path, Path]:
    """Parse a document through the baseline or improved arm.

    Returns (md_path, meta_path) paths to the output files.
    """
    path = Path(path)
    if arm not in VALID_ARMS:
        raise ValueError(f"arm must be one of {VALID_ARMS}, got '{arm}'")

    converter = _build_converter(arm)
    start = time.monotonic()
    result = converter.convert(path)
    parse_time = time.monotonic() - start

    doc_name = path.stem
    arm_dir = Path(out_dir) if out_dir else Path("results") / arm
    arm_dir.mkdir(parents=True, exist_ok=True)

    md_path = arm_dir / f"{doc_name}.md"
    meta_path = arm_dir / f"{doc_name}_meta.json"

    # Export markdown
    md_path.write_text(result.document.export_to_markdown())

    # Collect metadata
    doc = result.document
    meta = {
        "parse_time_seconds": round(parse_time, 2),
        "page_count": len(doc.pages),
        "table_count": len(doc.tables),
        "image_count": len(doc.pictures),
    }

    # Improved arm: include picture descriptions
    if arm == "improved":
        descriptions = []
        for pic in doc.pictures:
            if pic.meta and pic.meta.description:
                descriptions.append({"ref": pic.self_ref, "description": pic.meta.description.text})
        meta["picture_descriptions"] = descriptions

    meta_path.write_text(json.dumps(meta, indent=2))

    return md_path, meta_path


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    arm = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    doc_paths = sorted(Path("documents").glob("*"))
    for doc in doc_paths:
        print(f"Parsing {doc.name} ({arm})...")
        md, meta = parse_document(doc, arm=arm)
        print(f"  -> {md}, {meta}")
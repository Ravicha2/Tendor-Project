"""Tests for parse_document: baseline, ocr, and ocr_vlm arms via Docling."""

import json
from pathlib import Path

from src.parse import parse_document

DOCUMENTS = Path(__file__).parent.parent / "documents"
RESULTS = Path(__file__).parent.parent / "results"


class TestParseDocument:
    """TDD tests for parse_document(path, arm)."""

    def test_baseline_returns_md_and_meta(self, tmp_path):
        """parse_document with arm='baseline' produces .md and _meta.json."""
        out_dir = tmp_path / "baseline"
        doc = DOCUMENTS / "01_easy_logan_transport.pdf"
        md_path, meta_path = parse_document(doc, arm="baseline", out_dir=out_dir)

        assert md_path.exists()
        assert meta_path.exists()
        assert md_path.suffix == ".md"

    def test_ocr_returns_md_and_meta(self, tmp_path):
        """parse_document with arm='ocr' produces .md and _meta.json."""
        out_dir = tmp_path / "ocr"
        doc = DOCUMENTS / "01_easy_logan_transport.pdf"
        md_path, meta_path = parse_document(doc, arm="ocr", out_dir=out_dir)

        assert md_path.exists()
        assert meta_path.exists()

    def test_ocr_vlm_returns_md_and_meta(self, tmp_path):
        """parse_document with arm='ocr_vlm' produces .md and _meta.json."""
        out_dir = tmp_path / "ocr_vlm"
        doc = DOCUMENTS / "01_easy_logan_transport.pdf"
        md_path, meta_path = parse_document(doc, arm="ocr_vlm", out_dir=out_dir)

        assert md_path.exists()
        assert meta_path.exists()

    def test_meta_has_required_fields(self, tmp_path):
        """_meta.json includes parse_time_seconds, page_count, table_count, image_count."""
        out_dir = tmp_path / "baseline"
        doc = DOCUMENTS / "01_easy_logan_transport.pdf"
        _, meta_path = parse_document(doc, arm="baseline", out_dir=out_dir)
        meta = json.loads(meta_path.read_text())

        assert isinstance(meta["parse_time_seconds"], (int, float))
        assert isinstance(meta["page_count"], int)
        assert isinstance(meta["table_count"], int)
        assert isinstance(meta["image_count"], int)

    def test_baseline_meta_has_no_vlm_token_usage(self, tmp_path):
        """Baseline _meta.json must NOT contain vlm_token_usage key."""
        out_dir = tmp_path / "baseline"
        doc = DOCUMENTS / "01_easy_logan_transport.pdf"
        _, meta_path = parse_document(doc, arm="baseline", out_dir=out_dir)
        meta = json.loads(meta_path.read_text())

        assert "vlm_token_usage" not in meta

    def test_baseline_meta_has_no_picture_descriptions(self, tmp_path):
        """Baseline _meta.json must NOT contain picture_descriptions key."""
        out_dir = tmp_path / "baseline"
        doc = DOCUMENTS / "01_easy_logan_transport.pdf"
        _, meta_path = parse_document(doc, arm="baseline", out_dir=out_dir)
        meta = json.loads(meta_path.read_text())

        assert "picture_descriptions" not in meta

    def test_ocr_meta_has_no_picture_descriptions(self, tmp_path):
        """OCR _meta.json must NOT contain picture_descriptions key."""
        out_dir = tmp_path / "ocr"
        doc = DOCUMENTS / "01_easy_logan_transport.pdf"
        _, meta_path = parse_document(doc, arm="ocr", out_dir=out_dir)
        meta = json.loads(meta_path.read_text())

        assert "picture_descriptions" not in meta

    def test_ocr_vlm_meta_has_picture_descriptions(self, tmp_path):
        """OCR+VLM _meta.json MUST contain picture_descriptions and vlm_token_usage keys."""
        out_dir = tmp_path / "ocr_vlm"
        doc = DOCUMENTS / "01_easy_logan_transport.pdf"
        _, meta_path = parse_document(doc, arm="ocr_vlm", out_dir=out_dir)
        meta = json.loads(meta_path.read_text())

        assert "picture_descriptions" in meta
        assert "vlm_token_usage" in meta

    def test_invalid_arm_raises(self):
        """Invalid arm value raises ValueError."""
        import pytest
        with pytest.raises(ValueError, match="arm"):
            parse_document(DOCUMENTS / "01_easy_logan_transport.pdf", arm="invalid")

    def test_html_parses_with_html_backend(self, tmp_path):
        """HTML document parses successfully via HTML backend in both arms."""
        doc = DOCUMENTS / "04_edge_cityofsydney_agenda.html"
        for arm in ("baseline", "ocr", "ocr_vlm"):
            out_dir = tmp_path / arm
            md_path, meta_path = parse_document(doc, arm=arm, out_dir=out_dir)
            assert md_path.exists(), f"{arm} arm failed for HTML"
            assert meta_path.exists(), f"{arm} arm meta missing for HTML"
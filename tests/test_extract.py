"""Tests for extract_signals: LangExtract signal extraction on both arms."""

import json
import os
from pathlib import Path

import pytest

from src.extract import (
    coerce_signal,
    extract_signals,
    load_config,
    SIGNAL_TYPES,
    OPPORTUNITY_STAGES,
)

RESULTS = Path(__file__).parent.parent / "results"


class TestCoerceSignal:
    """Unit tests for type coercion of raw LangExtract attributes."""

    def test_budget_value_string_to_number(self):
        raw = {
            "signal_type": "capital_works_item",
            "project_name": "Road upgrade",
            "asset_or_location": "Main St",
            "category": "transport",
            "budget_value": "2500000",
            "budget_value_basis": "mentioned_value",
            "opportunity_stage": "funded_or_budgeted",
            "tender_pathway": "civil works",
            "likely_supplier_categories": "civil construction",
            "confidence_score": "0.78",
            "evidence_excerpt": "Council allocated $2.5M.",
            "needs_human_review": "true",
        }
        result = coerce_signal(raw)
        assert isinstance(result["budget_value"], (int, float))
        assert result["budget_value"] == 2500000

    def test_budget_value_none(self):
        raw = {"signal_type": "capital_works_item", "budget_value": None}
        result = coerce_signal(raw)
        assert result["budget_value"] is None

    def test_confidence_score_to_float(self):
        raw = {"signal_type": "capital_works_item", "confidence_score": "0.9"}
        result = coerce_signal(raw)
        assert isinstance(result["confidence_score"], float)
        assert result["confidence_score"] == 0.9

    def test_confidence_score_clamped_to_1(self):
        raw = {"signal_type": "capital_works_item", "confidence_score": "1.5"}
        result = coerce_signal(raw)
        assert result["confidence_score"] == 1.0

    def test_confidence_score_clamped_to_0(self):
        raw = {"signal_type": "capital_works_item", "confidence_score": "-0.1"}
        result = coerce_signal(raw)
        assert result["confidence_score"] == 0.0

    def test_likely_supplier_categories_comma_separated(self):
        raw = {"signal_type": "capital_works_item", "likely_supplier_categories": "civil construction, road infrastructure"}
        result = coerce_signal(raw)
        assert result["likely_supplier_categories"] == [
            "civil construction",
            "road infrastructure",
        ]

    def test_likely_supplier_categories_already_list(self):
        raw = {"signal_type": "capital_works_item", "likely_supplier_categories": ["civil construction", "road infrastructure"]}
        result = coerce_signal(raw)
        assert result["likely_supplier_categories"] == [
            "civil construction",
            "road infrastructure",
        ]

    def test_needs_human_review_to_bool(self):
        for truthy in ("true", "True", "TRUE", True):
            assert coerce_signal({"signal_type": "capital_works_item", "needs_human_review": truthy})["needs_human_review"] is True
        for falsy in ("false", "False", "FALSE", False):
            assert coerce_signal({"signal_type": "capital_works_item", "needs_human_review": falsy})["needs_human_review"] is False

    def test_all_12_fields_present(self):
        raw = {
            "signal_type": "capital_works_item",
            "project_name": "Chambers Flat Road upgrade",
            "asset_or_location": "Chambers Flat Road, Logan",
            "category": "transport",
            "budget_value": "2500000",
            "budget_value_basis": "mentioned_value",
            "opportunity_stage": "funded_or_budgeted",
            "tender_pathway": "civil works package",
            "likely_supplier_categories": "civil construction, road infrastructure",
            "confidence_score": "0.78",
            "evidence_excerpt": "Council allocated $2.5 million for Chambers Flat Road.",
            "needs_human_review": "true",
        }
        result = coerce_signal(raw)
        expected_keys = {
            "signal_type", "project_name", "asset_or_location", "category",
            "budget_value", "budget_value_basis", "opportunity_stage",
            "tender_pathway", "likely_supplier_categories", "confidence_score",
            "evidence_excerpt", "needs_human_review",
        }
        assert set(result.keys()) == expected_keys

    def test_signal_type_must_be_valid(self):
        raw = {"signal_type": "invalid_type"}
        with pytest.raises(ValueError, match="signal_type"):
            coerce_signal(raw)

    def test_opportunity_stage_noncanonical_kept(self):
        """LLM may produce non-canonical stages; keep them as-is rather than reject."""
        raw = {"signal_type": "capital_works_item", "opportunity_stage": "planning_approval"}
        result = coerce_signal(raw)
        assert result["opportunity_stage"] == "planning_approval"

    def test_budget_value_null_string(self):
        """LLM may return 'null' as a string for budget_value."""
        raw = {"signal_type": "capital_works_item", "budget_value": "null"}
        result = coerce_signal(raw)
        assert result["budget_value"] is None


class TestLoadConfig:
    """Unit tests for LangExtract config loading."""

    def test_config_has_required_fields(self):
        cfg = load_config()
        assert cfg.model_id == "google/gemini-3.1-flash-lite"
        assert cfg.provider == "openai"
        assert cfg.provider_kwargs.get("base_url") == "https://openrouter.ai/api/v1"
        assert cfg.provider_kwargs.get("temperature") == 0.0

    def test_config_reads_api_key(self, monkeypatch):
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-123")
        cfg = load_config()
        assert cfg.provider_kwargs["api_key"] == "test-key-123"


class TestExtractSignalsIntegration:
    """Integration tests calling OpenRouter API. Skip without API key."""

    @pytest.fixture
    def has_api_key(self):
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            pytest.skip("OPENROUTER_API_KEY not set")

    def test_baseline_easy_doc(self, has_api_key, tmp_path):
        """extract_signals on baseline arm for easy doc produces valid _signals.json."""
        # Copy the parsed markdown to tmp_path so we don't pollute results/
        src_md = RESULTS / "baseline" / "01_easy_logan_transport.md"
        if not src_md.exists():
            pytest.skip("Parsed markdown not found, run parse first")

        arm_dir = tmp_path / "baseline"
        arm_dir.mkdir()
        (arm_dir / "01_easy_logan_transport.md").write_text(src_md.read_text())

        signals_path = extract_signals("baseline", "01_easy_logan_transport", results_dir=tmp_path)
        assert signals_path.exists()
        signals = json.loads(signals_path.read_text())
        assert isinstance(signals, list)
        if signals:
            s = signals[0]
            assert "signal_type" in s
            assert s["signal_type"] in SIGNAL_TYPES
            assert isinstance(s["budget_value"], (int, float, type(None)))
            assert isinstance(s["confidence_score"], float)
            assert 0.0 <= s["confidence_score"] <= 1.0
            assert isinstance(s["likely_supplier_categories"], list)

    def test_improved_easy_doc(self, has_api_key, tmp_path):
        """extract_signals on improved arm for easy doc produces valid _signals.json."""
        src_md = RESULTS / "improved" / "01_easy_logan_transport.md"
        if not src_md.exists():
            pytest.skip("Parsed markdown not found, run parse first")

        arm_dir = tmp_path / "improved"
        arm_dir.mkdir()
        (arm_dir / "01_easy_logan_transport.md").write_text(src_md.read_text())

        signals_path = extract_signals("improved", "01_easy_logan_transport", results_dir=tmp_path)
        assert signals_path.exists()
        signals = json.loads(signals_path.read_text())
        assert isinstance(signals, list)
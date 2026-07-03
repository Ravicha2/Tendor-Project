"""Signal extraction using LangExtract on both parser arms."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from langextract.data import ExampleData, Extraction
from langextract.extraction import extract
from langextract.factory import ModelConfig

load_dotenv()

SIGNAL_TYPES = {
    "procurement_intent",
    "budget_approved",
    "capital_works_item",
    "operational_pain_point",
    "planned_action",
}

OPPORTUNITY_STAGES = {
    "tender_ready",
    "funded_or_budgeted",
    "planning/design",
    "pain_identified",
    "monitor_only",
}

PROMPT_DESCRIPTION = (
    "Extract pre-tender procurement signals from Australian council meeting minutes. "
    "Each signal is one concrete indication that a council may go to market soon: "
    "a tender, budget approval, capital works item, operational pain point, or planned action. "
    "Focus on project names, budget figures, locations, procurement indicators, and council decisions."
)

# Few-shot example from the brief
FEW_SHOT_TEXT = (
    "6.5 Local Roads (Kerb and Channel) Statement of Intent (SOI) 2026\n"
    "That the Statement of Intent for Local Roads (Kerb and Channel), "
    "as detailed in this report at Table 1, be adopted as the basis for funding "
    "and programming of the Local Roads (Kerb and Channel) Program of Council's "
    "Capital Roadworks and Drainage Program. Council allocated $2.5 million for "
    "Chambers Flat Road."
)

FEW_SHOT_EXTRACTION = Extraction(
    extraction_class="capital_works_item",
    extraction_text="Council allocated $2.5 million for Chambers Flat Road.",
    attributes={
        "project_name": "Chambers Flat Road upgrade",
        "asset_or_location": "Chambers Flat Road, Logan",
        "category": "transport",
        "budget_value": "2500000",
        "budget_value_basis": "mentioned_value",
        "opportunity_stage": "funded_or_budgeted",
        "tender_pathway": "civil works package",
        "likely_supplier_categories": ["civil construction", "road infrastructure"],
        "confidence_score": "0.78",
        "needs_human_review": "true",
    },
)

EXAMPLES = [
    ExampleData(text=FEW_SHOT_TEXT, extractions=[FEW_SHOT_EXTRACTION]),
]

# Attributes that come from LangExtract extraction_class/extraction_text mapping
MAPPED_FROM_EXTRACTION = {"signal_type", "evidence_excerpt"}

# All 12 expected field names
ALL_FIELDS = {
    "signal_type", "project_name", "asset_or_location", "category",
    "budget_value", "budget_value_basis", "opportunity_stage",
    "tender_pathway", "likely_supplier_categories", "confidence_score",
    "evidence_excerpt", "needs_human_review",
}


@dataclass
class LangExtractConfig:
    model_id: str | None = None
    model_url: str | None = None
    api_key_env: str = "OPENROUTER_API_KEY"
    provider: str = "openai"
    temperature: float = 0.0

    def __post_init__(self) -> None:
        if self.model_id is None:
            self.model_id = os.getenv("LANGEXTRACT_MODEL_ID", "google/gemini-3.1-flash-lite")
        if self.model_url is None:
            self.model_url = os.getenv("LANGEXTRACT_MODEL_URL", "https://openrouter.ai/api/v1")

    @property
    def api_key(self) -> str | None:
        return os.environ.get(self.api_key_env)


def load_config() -> ModelConfig:
    """Build a LangExtract ModelConfig for OpenRouter."""
    cfg = LangExtractConfig()
    return ModelConfig(
        model_id=cfg.model_id,
        provider=cfg.provider,
        provider_kwargs={
            "api_key": cfg.api_key,
            "base_url": cfg.model_url,
            "temperature": cfg.temperature,
        },
    )


def coerce_signal(raw: dict) -> dict:
    """Coerce raw extraction attributes to correct types for the 12-field schema."""
    # Map extraction_class → signal_type, extraction_text → evidence_excerpt
    result = {
        "signal_type": raw.get("signal_type", ""),
        "evidence_excerpt": raw.get("evidence_excerpt", ""),
    }

    if result["signal_type"] not in SIGNAL_TYPES:
        raise ValueError(f"invalid signal_type: {result['signal_type']}")

    # Copy string fields through
    for key in ("project_name", "asset_or_location", "category",
                "budget_value_basis", "opportunity_stage", "tender_pathway"):
        result[key] = raw.get(key)

    # budget_value → number or None
    bv = raw.get("budget_value")
    if bv is None or bv == "" or str(bv).lower() == "null":
        result["budget_value"] = None
    elif isinstance(bv, (int, float)):
        result["budget_value"] = bv
    else:
        # Strip currency symbols and commas
        cleaned = str(bv).replace("$", "").replace(",", "").strip()
        try:
            result["budget_value"] = float(cleaned)
            if result["budget_value"] == int(result["budget_value"]):
                result["budget_value"] = int(result["budget_value"])
        except ValueError:
            result["budget_value"] = None

    # confidence_score → float clamped to [0, 1]
    cs = raw.get("confidence_score")
    if cs is None or cs == "":
        result["confidence_score"] = 0.5  # ponytail: default mid when missing
    else:
        result["confidence_score"] = max(0.0, min(1.0, float(cs)))

    # likely_supplier_categories → list
    cats = raw.get("likely_supplier_categories")
    if cats is None:
        result["likely_supplier_categories"] = []
    elif isinstance(cats, list):
        result["likely_supplier_categories"] = cats
    elif isinstance(cats, str):
        result["likely_supplier_categories"] = [
            c.strip() for c in cats.split(",") if c.strip()
        ]
    else:
        result["likely_supplier_categories"] = [str(cats)]

    # needs_human_review → bool
    nhr = raw.get("needs_human_review")
    if isinstance(nhr, bool):
        result["needs_human_review"] = nhr
    elif isinstance(nhr, str):
        result["needs_human_review"] = nhr.lower() == "true"
    else:
        result["needs_human_review"] = True  # ponytail: default True for safety

    return result


def _extraction_to_signal(ext: Extraction) -> dict | None:
    """Convert a LangExtract Extraction to a signal dict, or None if invalid."""
    raw = {
        "signal_type": ext.extraction_class,
        "evidence_excerpt": ext.extraction_text,
    }
    # Merge attributes
    if ext.attributes:
        raw.update(ext.attributes)
    try:
        return coerce_signal(raw)
    except ValueError:
        # Skip signals with invalid types/stages
        return None


def extract_signals(
    arm: str,
    doc_name: str,
    results_dir: Path | str | None = None,
) -> Path:
    """Run LangExtract signal extraction on a parsed markdown document.

    Args:
        arm: "baseline" or "improved"
        doc_name: Document name stem (e.g. "01_easy_logan_transport")
        results_dir: Override results directory. Defaults to ./results/

    Returns:
        Path to the _signals.json output file.
    """
    if arm not in ("baseline", "improved"):
        raise ValueError(f"arm must be 'baseline' or 'improved', got '{arm}'")

    results_dir = Path(results_dir) if results_dir else Path("results")
    md_path = results_dir / arm / f"{doc_name}.md"

    if not md_path.exists():
        raise FileNotFoundError(f"Parsed markdown not found: {md_path}")

    text = md_path.read_text()
    if not text.strip():
        raise ValueError(f"Parsed markdown is empty: {md_path}")

    config = load_config()

    # ponytail: max_char_buffer=2000 for longer docs to keep chunks meaningful
    # extraction_passes=2 for better recall on sparse long docs
    result = extract(
        text_or_documents=text,
        prompt_description=PROMPT_DESCRIPTION,
        examples=EXAMPLES,
        config=config,
        max_char_buffer=2000,
        temperature=0.0,
        extraction_passes=2,
        show_progress=True,
        fetch_urls=False,
    )

    # result is AnnotatedDocument when input is str
    signals = []
    for ext in result.extractions:
        signal = _extraction_to_signal(ext)
        if signal is not None:
            signals.append(signal)

    out_path = results_dir / arm / f"{doc_name}_signals.json"
    out_path.write_text(json.dumps(signals, indent=2, ensure_ascii=False))
    return out_path


if __name__ == "__main__":
    import sys
    load_dotenv()
    arm = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    doc_name = sys.argv[2] if len(sys.argv) > 2 else "01_easy_logan_transport"
    out = extract_signals(arm, doc_name)
    print(f"Wrote {out}")
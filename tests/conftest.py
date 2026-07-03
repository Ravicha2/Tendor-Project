"""Load .env for integration tests that call OpenRouter API."""

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
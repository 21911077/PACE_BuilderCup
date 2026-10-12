"""Runtime settings, read from environment variables only."""
import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"


@dataclass(frozen=True)
class Settings:
    gemini_model: str          # e.g. the current Flash model ID shown in AI Studio
    google_api_key: str        # AI Studio key (default auth mode)
    use_vertex: bool           # USE_VERTEX=1 -> Agent Platform (formerly Vertex AI) via ADC
    gcp_project: str
    gcp_location: str
    mock_llm: bool             # MOCK_LLM=1 -> no Gemini or network calls, synthetic data
    cache_dir: Path
    wiki_user_agent: str
    max_writer_attempts: int


def get_settings() -> Settings:
    env = os.environ.get
    return Settings(
        gemini_model=env("GEMINI_MODEL", ""),
        google_api_key=env("GOOGLE_API_KEY", ""),
        use_vertex=env("USE_VERTEX", "0") == "1",
        gcp_project=env("GOOGLE_CLOUD_PROJECT", ""),
        gcp_location=env("GOOGLE_CLOUD_LOCATION", "global"),
        mock_llm=env("MOCK_LLM", "0") == "1",
        cache_dir=Path(env("CACHE_DIR", "/tmp/t2l_cache")),
        wiki_user_agent=env(
            "WIKI_USER_AGENT",
            "Trend2Line/0.1 (AI Builder Cup prototype; set WIKI_USER_AGENT with a contact)",
        ),
        max_writer_attempts=int(env("MAX_WRITER_ATTEMPTS", "3")),
    )

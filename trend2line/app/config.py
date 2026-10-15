"""Runtime settings, read from environment variables only."""
import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
STATIC_DIR = BASE_DIR / "static"


@dataclass(frozen=True)
class Settings:
    gemini_model: str          # current Flash model ID (run `python -m scripts.smoke_gemini` to list them)
    google_api_key: str        # AI Studio key ("AIza...") or Vertex AI express-mode key ("AQ....")
    gemini_auth: str           # auto | ai_studio | vertex_express | vertex_adc
    gcp_project: str
    gcp_location: str
    mock_llm: bool             # MOCK_LLM=1 -> canned Gemini outputs; trend data is still fetched live
    offline: bool              # OFFLINE=1 -> no network at all (tests/CI); synthetic, clearly labelled curves
    cache_dir: Path
    wiki_user_agent: str
    max_writer_attempts: int
    http_cache_hours: float

    @property
    def resolved_auth(self) -> str:
        """Express-mode keys start with 'AQ.' and must be sent to Vertex AI, not AI Studio."""
        if self.gemini_auth != "auto":
            return self.gemini_auth
        if self.google_api_key.startswith("AQ."):
            return "vertex_express"
        if self.google_api_key:
            return "ai_studio"
        return "vertex_adc"


def get_settings() -> Settings:
    env = os.environ.get
    auth = env("GEMINI_AUTH", "auto")
    if env("USE_VERTEX", "0") == "1" and auth == "auto":  # backwards compatible
        auth = "vertex_adc"
    return Settings(
        gemini_model=env("GEMINI_MODEL", ""),
        google_api_key=env("GOOGLE_API_KEY", ""),
        gemini_auth=auth,
        gcp_project=env("GOOGLE_CLOUD_PROJECT", ""),
        gcp_location=env("GOOGLE_CLOUD_LOCATION", "global"),
        mock_llm=env("MOCK_LLM", "0") == "1",
        offline=env("OFFLINE", "0") == "1",
        cache_dir=Path(env("CACHE_DIR", "/tmp/t2l_cache")),
        wiki_user_agent=env(
            "WIKI_USER_AGENT",
            "Trend2Line/0.2 (AI Builder Cup prototype; set WIKI_USER_AGENT with a contact email)",
        ),
        max_writer_attempts=int(env("MAX_WRITER_ATTEMPTS", "3")),
        http_cache_hours=float(env("HTTP_CACHE_HOURS", "12")),
    )

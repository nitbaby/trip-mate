from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    # LLM provider: gemini (default) | openai (any OpenAI-compatible API, e.g. Groq) | anthropic
    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    gemini_reasoning_effort: str = "low"  # keeps "thinking" short so replies start fast and fit max_tokens
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_api_key: str = ""      # for llm_provider=openai
    llm_model: str = ""
    llm_base_url: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    live_mode: str = "mock"  # mock | real
    embeddings: str = "onnx"  # onnx (Chroma MiniLM) | fastembed (HF) | hash (tests)
    tripmate_data_dir: Path = REPO_ROOT / "data"
    # retrieval confidence thresholds (cosine similarity, MiniLM); calibrated on samples/, re-tune with eval/ in Phase 6
    conf_high: float = 0.45
    conf_agree: float = 0.35   # top >= this AND a second hit >= conf_low from the same document counts as high
    conf_low: float = 0.25     # below this nothing is returned and confidence is "none"
    max_tools_per_turn: int = 6
    max_external_calls_per_session: int = 30

    @property
    def db_path(self) -> Path:
        return self.tripmate_data_dir / "tripmate.db"

    @property
    def uploads_dir(self) -> Path:
        return self.tripmate_data_dir / "uploads"

    @property
    def chroma_dir(self) -> Path:
        return self.tripmate_data_dir / "chroma"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    d = Path(s.tripmate_data_dir).expanduser()
    # relative paths are anchored at the repo root, never the process cwd (backend/ vs repo root differ)
    s.tripmate_data_dir = (d if d.is_absolute() else REPO_ROOT / d).resolve()
    s.tripmate_data_dir.mkdir(parents=True, exist_ok=True)
    s.uploads_dir.mkdir(parents=True, exist_ok=True)
    return s

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    live_mode: str = "mock"  # mock | real
    embeddings: str = "onnx"  # onnx (Chroma MiniLM) | fastembed (HF) | hash (tests)
    tripmate_data_dir: Path = REPO_ROOT / "data"

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
    s.tripmate_data_dir = Path(s.tripmate_data_dir).resolve()
    s.tripmate_data_dir.mkdir(parents=True, exist_ok=True)
    s.uploads_dir.mkdir(parents=True, exist_ok=True)
    return s

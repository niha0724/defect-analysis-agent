"""Central configuration, loaded from environment / .env.

Every module imports the singleton ``settings`` object rather than reading
os.environ directly, so there is exactly one place that defines defaults.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root = two levels up from this file (config/settings.py -> repo/)
ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---------- Paths ----------
    root_dir: Path = ROOT_DIR
    data_dir: Path = ROOT_DIR / "data"
    sample_dir: Path = ROOT_DIR / "data" / "sample"
    raw_dir: Path = ROOT_DIR / "data" / "raw"
    processed_dir: Path = ROOT_DIR / "data" / "processed"

    # ---------- Embeddings ----------
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Any sentence-transformers model. BGE variants trade speed for recall.",
    )

    # ---------- Vector store ----------
    chroma_dir: str = "./chroma_db"
    chroma_collection: str = "historical_defects"

    # ---------- Chunking ----------
    chunk_size: int = 800          # characters
    chunk_overlap: int = 120

    # ---------- Retrieval ----------
    top_k: int = 5

    # ---------- Agent LLM (Milestone 2) ----------
    llm_provider: str = "huggingface"          # huggingface | openai_compatible
    huggingfacehub_api_token: str = ""
    llm_model: str = "Qwen/Qwen2.5-7B-Instruct"

    openai_compatible_base_url: str = "http://localhost:11434/v1"
    openai_compatible_api_key: str = "not-needed"
    openai_compatible_model: str = "qwen2.5:7b"

    llm_temperature: float = 0.1
    llm_max_tokens: int = 1024

    @property
    def chroma_path(self) -> str:
        """Absolute path for the Chroma persistent client."""
        p = Path(self.chroma_dir)
        return str(p if p.is_absolute() else (self.root_dir / p))


settings = Settings()

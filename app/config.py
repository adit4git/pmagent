"""Central configuration loaded from environment."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ROOT / ".env"), extra="ignore")

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    log_level: str = "INFO"
    require_approval_for_proposals: bool = True

    # Paths
    root: Path = ROOT
    data_dir: Path = ROOT / "app" / "data"
    docs_dir: Path = ROOT / "app" / "data" / "documents"
    db_dir: Path = ROOT / "app" / "data" / "db"
    sqlite_path: Path = ROOT / "app" / "data" / "db" / "firm.sqlite"
    chroma_path: Path = ROOT / "app" / "data" / "db" / "chroma"
    audit_log_path: Path = ROOT / "audit_log.jsonl"

    def ensure_dirs(self) -> None:
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.docs_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional

# Look for .env in project root (parent of backend/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # LLM
    LITELLM_MODEL: str = "deepseek/deepseek-chat"
    LITELLM_API_KEY: str = ""
    LITELLM_API_BASE: str = ""
    LITELLM_TIMEOUT: int = 60

    # MySQL
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "yuqing"

    # ChromaDB
    CHROMA_PATH: str = "data/chroma_db"

    # Application
    LANGUAGE: str = "zh"
    MAX_CONTEXT_MESSAGES: int = 20
    MEMORY_RECALL_COUNT: int = 5
    AUTO_MEMORY_EXTRACTION: bool = True

    # Debug
    LOG_LEVEL: str = "INFO"

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            "?charset=utf8mb4"
        )

    @property
    def chroma_abs_path(self) -> str:
        p = Path(self.CHROMA_PATH)
        if not p.is_absolute():
            return str(_PROJECT_ROOT / p)
        return self.CHROMA_PATH

    class Config:
        env_file = str(_PROJECT_ROOT / ".env")
        env_file_encoding = "utf-8"


settings = Settings()

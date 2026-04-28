from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API keys — loaded from environment or .env
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    firecrawl_api_key: str = Field(default="", alias="FIRECRAWL_API_KEY")
    serpapi_key: str = Field(default="", alias="SERPAPI_KEY")

    # Paths
    root_dir: Path = PROJECT_ROOT

    @property
    def raw_dir(self) -> Path:
        return self.root_dir / "raw"

    @property
    def wiki_dir(self) -> Path:
        return self.root_dir / "wiki"

    @property
    def graph_dir(self) -> Path:
        return self.root_dir / "graph"

    @property
    def retrieval_dir(self) -> Path:
        return self.root_dir / "retrieval"

    @property
    def config_dir(self) -> Path:
        return self.root_dir / "config"

    @property
    def agents_dir(self) -> Path:
        return self.root_dir / "agents"

    # Model assignments
    model_bulk_extraction: str = "claude-haiku-4-5-20251001"
    model_wiki_compilation: str = "claude-sonnet-4-6"
    model_contradiction: str = "claude-opus-4-7"
    model_query_synthesis: str = "claude-sonnet-4-6"
    model_deep_analysis: str = "claude-opus-4-7"
    model_relevance_scoring: str = "claude-haiku-4-5-20251001"
    model_supervisor: str = "claude-sonnet-4-6"

    # Pipeline
    chunk_size: int = 512
    chunk_overlap: int = 64
    relevance_threshold: float = 0.6
    supervisor_interval_seconds: int = 60

    # Cloudflare Access / gateway
    cf_access_team_domain: str = Field(default="", alias="CF_ACCESS_TEAM_DOMAIN")
    cf_access_aud_tag: str = Field(default="", alias="CF_ACCESS_AUD_TAG")
    gateway_cors_origins: list[str] = Field(
        default_factory=list,
        alias="GATEWAY_CORS_ORIGINS",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

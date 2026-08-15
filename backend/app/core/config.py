"""Application configuration.

All configuration is environment driven (12-factor). Nothing secret is ever committed;
``.env.example`` documents the contract and ``.env`` is git-ignored.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application --------------------------------------------------------
    app_name: str = "Enterprise Metadata Copilot"
    app_env: Literal["local", "dev", "test", "staging", "prod"] = "local"
    debug: bool = True
    log_level: str = "INFO"
    log_json: bool = False
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- PostgreSQL ---------------------------------------------------------
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "emc"
    postgres_password: SecretStr = SecretStr("change-me-locally")
    postgres_db: str = "metadata_copilot"
    database_url: str | None = None
    db_echo: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20

    # --- Neo4j / graph ------------------------------------------------------
    graph_store: Literal["neo4j", "memory"] = "neo4j"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("change-me-locally")
    neo4j_database: str = "neo4j"

    # --- LLM ----------------------------------------------------------------
    llm_provider: Literal["mock", "openai", "azure_openai"] = "mock"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: SecretStr | None = None
    llm_api_base: str | None = None
    llm_temperature: float = 0.0
    llm_max_tokens: int = 1200
    llm_timeout_seconds: int = 60

    # --- Embeddings ---------------------------------------------------------
    embedding_provider: Literal["hash", "openai"] = "hash"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimension: int = 1536
    embedding_api_key: SecretStr | None = None
    embedding_api_base: str | None = None

    # --- Vector store / RAG -------------------------------------------------
    vector_store: Literal["pgvector", "memory"] = "pgvector"
    rag_top_k: int = 8
    rag_chunk_size: int = 900
    rag_chunk_overlap: int = 120
    hybrid_keyword_weight: float = 0.4
    hybrid_semantic_weight: float = 0.6

    # --- Lineage ------------------------------------------------------------
    lineage_default_depth: Annotated[int, Field(ge=1)] = 3
    lineage_max_depth: Annotated[int, Field(ge=1)] = 15
    lineage_min_confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.3
    lineage_auto_verify_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.99

    # --- Security -----------------------------------------------------------
    auth_enabled: bool = False
    jwt_secret: SecretStr | None = None
    jwt_algorithm: str = "RS256"
    jwt_audience: str = "enterprise-metadata-copilot"
    jwt_issuer: str | None = None
    default_principal: str = "local-developer"

    # --- Ingestion ----------------------------------------------------------
    ingestion_schedule_seconds: int = 0
    ingestion_batch_size: int = 500

    # ------------------------------------------------------------------ #
    # Validators / derived values
    # ------------------------------------------------------------------ #
    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("log_level")
    @classmethod
    def _upper_log_level(cls, value: str) -> str:
        return value.upper()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def async_database_url(self) -> str:
        """SQLAlchemy async URL (asyncpg)."""
        if self.database_url:
            return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        dsn = PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            path=self.postgres_db,
        )
        return str(dsn)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        """Synchronous URL used by Alembic and offline scripts."""
        return self.async_database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.app_env in {"staging", "prod"}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def docs_url(self) -> str | None:
        """Interactive docs are disabled in production by default."""
        return None if self.is_production else "/docs"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()


settings = get_settings()

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_path: Path = API_DIR / "var" / "nammaspace.sqlite3"
    storage_root: Path = API_DIR / "var" / "storage"
    reconstruction_root: Path = API_DIR / "var" / "reconstruction"
    colmap_binary: str = "colmap"
    dense_colmap_image: str = "colmap/colmap:latest"
    docker_binary: str = "docker"
    max_upload_bytes: int = 512 * 1024 * 1024
    upload_chunk_bytes: int = 8 * 1024 * 1024
    allowed_origins: str = ""
    dev_auth_token: str = "local-dev-only-change-me"
    dev_tenant_id: str = "local-tenant"
    dev_user_id: str = "local-user"
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""
    oidc_tenant_claim: str = "tenant_id"
    worker_poll_seconds: float = 1.0

    @field_validator("database_path", "storage_root", "reconstruction_root", mode="before")
    @classmethod
    def resolve_data_paths(cls, value: str | Path) -> Path:
        path = Path(value)
        return path if path.is_absolute() else (API_DIR / path).resolve()

    @property
    def origin_list(self) -> list[str]:
        configured = [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]
        if configured or self.app_env != "development":
            return configured
        return ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()

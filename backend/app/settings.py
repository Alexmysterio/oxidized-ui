from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_LANGUAGES = ("es", "en")
LANGUAGE_RE = re.compile(r"^[a-z]{2}(-[A-Z]{2})?$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "production"
    app_version: str = "0.1.0"

    secret_key: str = Field(min_length=32)
    fernet_key: str
    oxidized_source_token: str = Field(min_length=24)

    oxidized_api_url: str = "http://oxidized:8888"
    oxidized_container_name: str = "oxidized"
    docker_proxy_url: str = "http://docker-socket-proxy:2375"
    supervisor_url: str = ""
    supervisor_program: str = "oxidized"
    supervisor_logfile: str = "/var/log/supervisor/oxidized.log"
    ui_internal_url: str = "http://oxidized-ui:8080"
    ui_hostname: str = ""
    ui_https_port: int = 443

    data_dir: Path = Path("/data")
    oxidized_config_dir: Path = Path("/oxidized-config")
    locales_dir: Path = Path("/app/locales")
    static_dir: Path = Path("/app/static")
    database_url: str | None = None

    default_language: str = "es"
    session_cookie_secure: bool = False
    session_cookie_name: str = "oxidized_ui_session"
    session_absolute_hours: int = Field(default=12, ge=1, le=168)
    session_idle_minutes: int = Field(default=30, ge=1, le=1440)

    trusted_origins: str = ""
    trust_proxy_headers: bool = False

    bootstrap_admin_username: str = ""
    bootstrap_admin_password: str = ""
    bootstrap_admin_language: str = "es"

    auto_migrate: bool = True
    disable_background_tasks: bool = False
    ui_log_level: str = "INFO"
    metrics_token: str = ""
    inbound_webhook_token: str = ""
    oidc_enabled: bool = False
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_scopes: str = "openid profile email"
    oidc_default_role: str = "viewer"
    oidc_auto_create: bool = True

    config_backup_keep: int = Field(default=0, ge=0, le=500)
    poll_interval_seconds: int = Field(default=30, ge=5, le=3600)

    login_max_failures_per_user: int = Field(default=5, ge=1, le=100)
    login_max_failures_per_ip: int = Field(default=20, ge=1, le=1000)
    login_window_minutes: int = Field(default=15, ge=1, le=1440)

    oxidized_connect_timeout: float = 4.0
    oxidized_read_timeout: float = 60.0
    docker_connect_timeout: float = 3.0
    docker_read_timeout: float = 60.0

    max_config_bytes: int = Field(default=1_000_000, ge=1024)
    max_csv_bytes: int = Field(default=5_000_000, ge=1024)
    max_csv_rows: int = Field(default=25_000, ge=1)
    max_log_lines: int = Field(default=5000, ge=1, le=100_000)

    @field_validator("secret_key")
    @classmethod
    def _secret_key_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 bytes")
        return value

    @field_validator("fernet_key")
    @classmethod
    def _fernet_key(cls, value: str) -> str:
        try:
            Fernet(value.encode("ascii"))
        except Exception as exc:  # noqa: BLE001 - normalize any crypto parsing failure
            raise ValueError("FERNET_KEY is not a valid Fernet key") from exc
        return value

    @field_validator("oxidized_source_token")
    @classmethod
    def _source_token_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) < 24:
            raise ValueError("OXIDIZED_SOURCE_TOKEN must contain at least 24 bytes")
        return value

    @field_validator("default_language", "bootstrap_admin_language")
    @classmethod
    def _language_format(cls, value: str) -> str:
        if not LANGUAGE_RE.match(value):
            raise ValueError("invalid language code")
        return value

    @model_validator(mode="after")
    def _validate_urls(self) -> Settings:
        for name in ("oxidized_api_url", "docker_proxy_url", "ui_internal_url"):
            value = getattr(self, name)
            if not (value.startswith("http://") or value.startswith("https://")):
                raise ValueError(f"{name} must be an http(s) URL")
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$", self.oxidized_container_name):
            raise ValueError("OXIDIZED_CONTAINER_NAME is not a valid Docker container name")
        if not re.match(r"^[a-z0-9][a-z0-9-]*$", self.app_env):
            self.app_env = "production"
        return self

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'oxidized-ui.sqlite3').as_posix()}"

    @property
    def config_file(self) -> Path:
        return self.oxidized_config_dir / "config"

    @property
    def backup_dir(self) -> Path:
        return self.oxidized_config_dir / ".ui-backups"

    @property
    def trusted_origin_list(self) -> list[str]:
        origins = [part.strip().rstrip("/") for part in self.trusted_origins.split(",") if part.strip()]
        host = self.ui_hostname.strip().rstrip("/")
        if host:
            origins.extend((f"https://{host}", f"https://{host}:{self.ui_https_port}"))
        return list(dict.fromkeys(origins))

    @property
    def available_languages(self) -> list[str]:
        """Discover languages from files; fall back to the built-in pair.

        Adding a language only requires adding a JSON file under the locales
        directory used by the image/build. The backend never translates text.
        """
        candidates: list[Path] = []
        if self.locales_dir.exists():
            candidates.extend(self.locales_dir.glob("*.json"))
        # Development convenience: the source lives in frontend/public/locales.
        repo_locales = Path(__file__).resolve().parents[2] / "frontend" / "public" / "locales"
        if repo_locales.exists():
            candidates.extend(repo_locales.glob("*.json"))
        codes = sorted({path.stem for path in candidates if re.fullmatch(r"[a-z]{2}(-[A-Z]{2})?", path.stem)})
        if not codes:
            codes = list(DEFAULT_LANGUAGES)
        if self.default_language in codes:
            codes = [self.default_language, *[code for code in codes if code != self.default_language]]
        return codes

    @property
    def resolved_default_language(self) -> str:
        languages = self.available_languages
        if self.default_language in languages:
            return self.default_language
        return "es" if "es" in languages else languages[0]

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.oxidized_config_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

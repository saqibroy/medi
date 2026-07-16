"""Environment-driven application configuration with production safety checks."""

from __future__ import annotations

from dataclasses import dataclass
from os import environ
from urllib.parse import urlparse


DEVELOPMENT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
)
DEVELOPMENT_TOKEN_SECRET = "dev-token-secret-change-before-production"
DEVELOPMENT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/medical_annotations"


class ConfigurationError(RuntimeError):
    """Raised when an unsafe application configuration would be started."""


@dataclass(frozen=True)
class Settings:
    """Validated settings used by the API process and container entrypoint."""

    environment: str
    database_url: str
    token_secret: str
    cors_origins: tuple[str, ...]
    seed_demo_data: bool

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


def _read_boolean(value: str, variable_name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{variable_name} must be true or false")


def _read_origins(value: str) -> tuple[str, ...]:
    origins = tuple(origin.strip().rstrip("/") for origin in value.split(",") if origin.strip())
    if not origins:
        raise ConfigurationError("CORS_ORIGINS must contain at least one origin")
    if "*" in origins:
        raise ConfigurationError("CORS_ORIGINS must not contain '*' when credentials are enabled")
    for origin in origins:
        parsed = urlparse(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.params
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ConfigurationError("CORS_ORIGINS must be a comma-separated list of exact http(s) origins")
    return origins


def get_settings(environment: dict[str, str] | None = None) -> Settings:
    """Read settings without caching so focused tests can safely isolate env vars."""

    values = environ if environment is None else environment
    app_environment = values.get("APP_ENV", "development").strip().lower()
    if app_environment not in {"development", "test", "production"}:
        raise ConfigurationError("APP_ENV must be development, test, or production")

    database_url = values.get("DATABASE_URL", DEVELOPMENT_DATABASE_URL).strip()
    token_secret = values.get("TOKEN_SECRET", DEVELOPMENT_TOKEN_SECRET).strip()
    default_origins = ",".join(DEVELOPMENT_CORS_ORIGINS)
    cors_origins = _read_origins(values.get("CORS_ORIGINS", default_origins))
    seed_demo_data = _read_boolean(values.get("SEED_DEMO_DATA", "false" if app_environment == "production" else "true"), "SEED_DEMO_DATA")

    if app_environment == "production":
        if "DATABASE_URL" not in values or database_url == DEVELOPMENT_DATABASE_URL or "postgres:postgres@" in database_url:
            raise ConfigurationError("production requires a non-development DATABASE_URL")
        if "TOKEN_SECRET" not in values or token_secret == DEVELOPMENT_TOKEN_SECRET or len(token_secret) < 32:
            raise ConfigurationError("production requires a unique TOKEN_SECRET of at least 32 characters")
        if "CORS_ORIGINS" not in values:
            raise ConfigurationError("production requires explicit CORS_ORIGINS")
        if seed_demo_data:
            raise ConfigurationError("SEED_DEMO_DATA must be false in production")

    return Settings(
        environment=app_environment,
        database_url=database_url,
        token_secret=token_secret,
        cors_origins=cors_origins,
        seed_demo_data=seed_demo_data,
    )

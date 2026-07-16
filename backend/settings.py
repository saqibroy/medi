"""Environment-driven application configuration with production safety checks."""

from __future__ import annotations

from dataclasses import dataclass
from os import environ
from pathlib import Path
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
DEVELOPMENT_CSRF_SECRET = "dev-csrf-secret-change-before-production"
DEVELOPMENT_AUDIT_SIGNING_KEY = "dev-audit-signing-key-change-before-production"
DEVELOPMENT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/medical_annotations"


class ConfigurationError(RuntimeError):
    """Raised when an unsafe application configuration would be started."""


@dataclass(frozen=True)
class Settings:
    """Validated settings used by the API process and container entrypoint."""

    environment: str
    database_url: str
    token_secret: str
    csrf_secret: str
    audit_signing_key: str
    cors_origins: tuple[str, ...]
    seed_demo_data: bool
    session_ttl_minutes: int
    login_rate_limit_per_minute: int
    sensitive_rate_limit_per_minute: int
    session_cookie_secure: bool
    session_cookie_samesite: str
    rate_limit_backend: str
    rate_limit_redis_url: str | None
    scan_storage_backend: str
    scan_storage_root: Path
    scan_storage_bucket: str | None
    scan_storage_region: str | None
    scan_storage_endpoint_url: str | None
    scan_storage_signed_url_ttl_seconds: int
    scan_storage_sse: str
    scan_storage_kms_key_id: str | None
    data_deletion_operator_enabled: bool

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


def _read_integer(values: object, variable_name: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(str(values))
    except ValueError as error:
        raise ConfigurationError(f"{variable_name} must be an integer") from error
    if parsed < minimum or parsed > maximum:
        raise ConfigurationError(f"{variable_name} must be between {minimum} and {maximum}")
    return parsed


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
    csrf_secret = values.get("CSRF_SECRET", DEVELOPMENT_CSRF_SECRET).strip()
    audit_signing_key = values.get("AUDIT_SIGNING_KEY", DEVELOPMENT_AUDIT_SIGNING_KEY).strip()
    default_origins = ",".join(DEVELOPMENT_CORS_ORIGINS)
    cors_origins = _read_origins(values.get("CORS_ORIGINS", default_origins))
    seed_demo_data = _read_boolean(values.get("SEED_DEMO_DATA", "false" if app_environment == "production" else "true"), "SEED_DEMO_DATA")
    session_ttl_minutes = _read_integer(values.get("SESSION_TTL_MINUTES", "480"), "SESSION_TTL_MINUTES", 5, 1440)
    login_rate_limit = _read_integer(values.get("LOGIN_RATE_LIMIT_PER_MINUTE", "10"), "LOGIN_RATE_LIMIT_PER_MINUTE", 1, 1000)
    sensitive_rate_limit = _read_integer(values.get("SENSITIVE_RATE_LIMIT_PER_MINUTE", "60"), "SENSITIVE_RATE_LIMIT_PER_MINUTE", 1, 10000)
    session_cookie_secure = _read_boolean(values.get("SESSION_COOKIE_SECURE", "true" if app_environment == "production" else "false"), "SESSION_COOKIE_SECURE")
    session_cookie_samesite = values.get("SESSION_COOKIE_SAMESITE", "lax").strip().lower()
    if session_cookie_samesite not in {"lax", "strict"}:
        raise ConfigurationError("SESSION_COOKIE_SAMESITE must be lax or strict")
    rate_limit_backend = values.get("RATE_LIMIT_BACKEND", "memory").strip().lower()
    if rate_limit_backend not in {"memory", "redis"}:
        raise ConfigurationError("RATE_LIMIT_BACKEND must be memory or redis")
    rate_limit_redis_url = values.get("RATE_LIMIT_REDIS_URL", "").strip() or None
    if rate_limit_backend == "redis" and rate_limit_redis_url is None:
        raise ConfigurationError("RATE_LIMIT_REDIS_URL is required when RATE_LIMIT_BACKEND=redis")
    storage_backend = values.get("SCAN_STORAGE_BACKEND", "local").strip().lower()
    if storage_backend not in {"local", "s3"}:
        raise ConfigurationError("SCAN_STORAGE_BACKEND must be local or s3")
    storage_root = Path(values.get("SCAN_STORAGE_ROOT", "backend/data/sample_scan"))
    storage_bucket = values.get("SCAN_STORAGE_BUCKET", "").strip() or None
    storage_region = values.get("SCAN_STORAGE_REGION", "").strip() or None
    storage_endpoint_url = values.get("SCAN_STORAGE_ENDPOINT_URL", "").strip() or None
    signed_url_ttl = _read_integer(values.get("SCAN_STORAGE_SIGNED_URL_TTL_SECONDS", "300"), "SCAN_STORAGE_SIGNED_URL_TTL_SECONDS", 60, 900)
    storage_sse = values.get("SCAN_STORAGE_SSE", "AES256").strip()
    if storage_sse not in {"AES256", "aws:kms"}:
        raise ConfigurationError("SCAN_STORAGE_SSE must be AES256 or aws:kms")
    storage_kms_key_id = values.get("SCAN_STORAGE_KMS_KEY_ID", "").strip() or None
    deletion_operator_enabled = _read_boolean(
        values.get("DATA_DELETION_OPERATOR_ENABLED", "false"),
        "DATA_DELETION_OPERATOR_ENABLED",
    )
    if storage_backend == "s3" and (storage_bucket is None or storage_region is None):
        raise ConfigurationError("S3 storage requires SCAN_STORAGE_BUCKET and SCAN_STORAGE_REGION")
    if storage_sse == "aws:kms" and storage_kms_key_id is None:
        raise ConfigurationError("SCAN_STORAGE_KMS_KEY_ID is required for aws:kms")

    if app_environment == "production":
        if "DATABASE_URL" not in values or database_url == DEVELOPMENT_DATABASE_URL or "postgres:postgres@" in database_url:
            raise ConfigurationError("production requires a non-development DATABASE_URL")
        if "TOKEN_SECRET" not in values or token_secret == DEVELOPMENT_TOKEN_SECRET or len(token_secret) < 32:
            raise ConfigurationError("production requires a unique TOKEN_SECRET of at least 32 characters")
        if (
            "CSRF_SECRET" not in values
            or csrf_secret == DEVELOPMENT_CSRF_SECRET
            or len(csrf_secret) < 32
            or csrf_secret == token_secret
        ):
            raise ConfigurationError("production requires a distinct CSRF_SECRET of at least 32 characters")
        if (
            "AUDIT_SIGNING_KEY" not in values
            or audit_signing_key == DEVELOPMENT_AUDIT_SIGNING_KEY
            or len(audit_signing_key) < 32
            or audit_signing_key == token_secret
            or audit_signing_key == csrf_secret
        ):
            raise ConfigurationError("production requires a distinct AUDIT_SIGNING_KEY of at least 32 characters")
        if "CORS_ORIGINS" not in values:
            raise ConfigurationError("production requires explicit CORS_ORIGINS")
        if seed_demo_data:
            raise ConfigurationError("SEED_DEMO_DATA must be false in production")
        if not session_cookie_secure:
            raise ConfigurationError("SESSION_COOKIE_SECURE must be true in production")
        if rate_limit_backend != "redis":
            raise ConfigurationError("production requires RATE_LIMIT_BACKEND=redis")
        if rate_limit_redis_url is None or urlparse(rate_limit_redis_url).scheme != "rediss":
            raise ConfigurationError("production RATE_LIMIT_REDIS_URL must use rediss://")
        if storage_backend != "s3":
            raise ConfigurationError("production requires SCAN_STORAGE_BACKEND=s3")
        if storage_sse != "aws:kms" or storage_kms_key_id is None:
            raise ConfigurationError("production S3 storage requires SCAN_STORAGE_SSE=aws:kms and SCAN_STORAGE_KMS_KEY_ID")

    return Settings(
        environment=app_environment,
        database_url=database_url,
        token_secret=token_secret,
        csrf_secret=csrf_secret,
        audit_signing_key=audit_signing_key,
        cors_origins=cors_origins,
        seed_demo_data=seed_demo_data,
        session_ttl_minutes=session_ttl_minutes,
        login_rate_limit_per_minute=login_rate_limit,
        sensitive_rate_limit_per_minute=sensitive_rate_limit,
        session_cookie_secure=session_cookie_secure,
        session_cookie_samesite=session_cookie_samesite,
        rate_limit_backend=rate_limit_backend,
        rate_limit_redis_url=rate_limit_redis_url,
        scan_storage_backend=storage_backend,
        scan_storage_root=storage_root,
        scan_storage_bucket=storage_bucket,
        scan_storage_region=storage_region,
        scan_storage_endpoint_url=storage_endpoint_url,
        scan_storage_signed_url_ttl_seconds=signed_url_ttl,
        scan_storage_sse=storage_sse,
        scan_storage_kms_key_id=storage_kms_key_id,
        data_deletion_operator_enabled=deletion_operator_enabled,
    )

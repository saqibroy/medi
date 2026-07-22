"""Tests for the development/production configuration boundary."""

import pytest

from backend.settings import ConfigurationError, DEVELOPMENT_CORS_ORIGINS, get_settings


DATABASE_RUNTIME_ENV = {
    "DATABASE_POOL_SIZE": "5",
    "DATABASE_MAX_OVERFLOW": "5",
    "DATABASE_POOL_TIMEOUT_SECONDS": "5",
    "DATABASE_STATEMENT_TIMEOUT_MS": "30000",
    "DATABASE_SLOW_QUERY_THRESHOLD_MS": "500",
}


def test_development_defaults_are_local_and_seed_demo_data() -> None:
    settings = get_settings({})

    assert settings.environment == "development"
    assert settings.cors_origins == DEVELOPMENT_CORS_ORIGINS
    assert settings.seed_demo_data is True
    assert settings.database_pool_size == 5
    assert settings.database_max_overflow == 5
    assert settings.database_pool_timeout_seconds == 5
    assert settings.database_statement_timeout_ms == 30000
    assert settings.database_slow_query_threshold_ms == 500
    assert settings.session_idle_timeout_minutes == 60
    assert settings.data_deletion_operator_enabled is False
    assert settings.external_ai_enabled is False
    assert settings.external_ai_allowed_origins == ()
    assert settings.privacy_reference_key


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({}, "DATABASE_URL"),
        ({"DATABASE_URL": "postgresql+psycopg://app:strong-password@db:5432/medi"}, "TOKEN_SECRET"),
        (
            {
                "DATABASE_URL": "postgresql+psycopg://app:strong-password@db:5432/medi",
                "TOKEN_SECRET": "a-unique-production-token-secret-with-adequate-length",
            },
            "CSRF_SECRET",
        ),
        (
            {
                "DATABASE_URL": "postgresql+psycopg://app:strong-password@db:5432/medi",
                "TOKEN_SECRET": "a-unique-production-token-secret-with-adequate-length",
                "CSRF_SECRET": "a-distinct-production-csrf-secret-with-adequate-length",
            },
            "AUDIT_SIGNING_KEY",
        ),
        (
            {
                "DATABASE_URL": "postgresql+psycopg://app:strong-password@db:5432/medi",
                "TOKEN_SECRET": "a-unique-production-token-secret-with-adequate-length",
                "CSRF_SECRET": "a-distinct-production-csrf-secret-with-adequate-length",
                "AUDIT_SIGNING_KEY": "a-separate-production-audit-signing-key-with-length",
            },
            "PRIVACY_REFERENCE_KEY",
        ),
        (
            {
                "DATABASE_URL": "postgresql+psycopg://app:strong-password@db:5432/medi",
                "TOKEN_SECRET": "a-unique-production-token-secret-with-adequate-length",
                "CSRF_SECRET": "a-distinct-production-csrf-secret-with-adequate-length",
                "AUDIT_SIGNING_KEY": "a-separate-production-audit-signing-key-with-length",
                "PRIVACY_REFERENCE_KEY": "a-distinct-production-privacy-reference-key",
            },
            "CORS_ORIGINS",
        ),
        (
            {
                "DATABASE_URL": "postgresql+psycopg://app:strong-password@db:5432/medi",
                "TOKEN_SECRET": "a-unique-production-token-secret-with-adequate-length",
                "CSRF_SECRET": "a-distinct-production-csrf-secret-with-adequate-length",
                "AUDIT_SIGNING_KEY": "a-separate-production-audit-signing-key-with-length",
                "PRIVACY_REFERENCE_KEY": "a-distinct-production-privacy-reference-key",
                "CORS_ORIGINS": "https://medi.example.org",
            },
            "SESSION_IDLE_TIMEOUT_MINUTES",
        ),
        (
            {
                "DATABASE_URL": "postgresql+psycopg://app:strong-password@db:5432/medi",
                "TOKEN_SECRET": "a-unique-production-token-secret-with-adequate-length",
                "CSRF_SECRET": "a-distinct-production-csrf-secret-with-adequate-length",
                "AUDIT_SIGNING_KEY": "a-separate-production-audit-signing-key-with-length",
                "PRIVACY_REFERENCE_KEY": "a-distinct-production-privacy-reference-key",
                "CORS_ORIGINS": "https://medi.example.org",
                "SESSION_IDLE_TIMEOUT_MINUTES": "30",
                "SEED_DEMO_DATA": "true",
            },
            "SEED_DEMO_DATA",
        ),
    ],
)
def test_production_fails_closed_for_missing_or_unsafe_settings(changes: dict[str, str], message: str) -> None:
    environment = {"APP_ENV": "production", **changes}

    with pytest.raises(ConfigurationError, match=message):
        get_settings(environment)


def test_production_accepts_explicit_safe_settings() -> None:
    settings = get_settings(
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://medi_app:strong-password@db:5432/medi",
            "TOKEN_SECRET": "a-unique-production-token-secret-with-adequate-length",
            "CSRF_SECRET": "a-distinct-production-csrf-secret-with-adequate-length",
            "AUDIT_SIGNING_KEY": "a-separate-production-audit-signing-key-with-length",
            "PRIVACY_REFERENCE_KEY": "a-distinct-production-privacy-reference-key",
            "CORS_ORIGINS": "https://medi.example.org,https://review.medi.example.org",
            "SEED_DEMO_DATA": "false",
            "SESSION_IDLE_TIMEOUT_MINUTES": "30",
            "RATE_LIMIT_BACKEND": "redis",
            "RATE_LIMIT_REDIS_URL": "rediss://redis.example.org:6380/0",
            "SCAN_STORAGE_BACKEND": "s3",
            "SCAN_STORAGE_BUCKET": "medi-private-production",
            "SCAN_STORAGE_REGION": "eu-central-1",
            "SCAN_STORAGE_SSE": "aws:kms",
            "SCAN_STORAGE_KMS_KEY_ID": "arn:aws:kms:eu-central-1:123456789012:key/test-key",
            **DATABASE_RUNTIME_ENV,
        }
    )

    assert settings.is_production is True
    assert settings.seed_demo_data is False
    assert settings.cors_origins == ("https://medi.example.org", "https://review.medi.example.org")
    assert settings.scan_storage_backend == "s3"
    assert settings.scan_storage_sse == "aws:kms"
    assert settings.session_cookie_secure is True
    assert settings.session_idle_timeout_minutes == 30
    assert settings.rate_limit_backend == "redis"
    assert settings.data_deletion_operator_enabled is False
    assert settings.external_ai_enabled is False


def test_production_requires_the_supported_postgresql_driver() -> None:
    with pytest.raises(ConfigurationError, match=r"postgresql\+psycopg"):
        get_settings({"APP_ENV": "production", "DATABASE_URL": "mysql://app:secret@db/medi"})


def test_production_requires_explicit_database_runtime_controls() -> None:
    environment = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://medi_app:strong-password@db:5432/medi",
        "TOKEN_SECRET": "a-unique-production-token-secret-with-adequate-length",
        "CSRF_SECRET": "a-distinct-production-csrf-secret-with-adequate-length",
        "AUDIT_SIGNING_KEY": "a-separate-production-audit-signing-key-with-length",
        "PRIVACY_REFERENCE_KEY": "a-distinct-production-privacy-reference-key",
        "CORS_ORIGINS": "https://medi.example.org",
        "SEED_DEMO_DATA": "false",
        "SESSION_IDLE_TIMEOUT_MINUTES": "30",
        "RATE_LIMIT_BACKEND": "redis",
        "RATE_LIMIT_REDIS_URL": "rediss://redis.example.org:6380/0",
        "SCAN_STORAGE_BACKEND": "s3",
        "SCAN_STORAGE_BUCKET": "medi-private-production",
        "SCAN_STORAGE_REGION": "eu-central-1",
        "SCAN_STORAGE_SSE": "aws:kms",
        "SCAN_STORAGE_KMS_KEY_ID": "arn:aws:kms:eu-central-1:123456789012:key/test-key",
        **DATABASE_RUNTIME_ENV,
    }

    for variable_name in DATABASE_RUNTIME_ENV:
        incomplete = {key: value for key, value in environment.items() if key != variable_name}
        with pytest.raises(ConfigurationError, match=variable_name):
            get_settings(incomplete)


def test_production_rejects_local_or_unencrypted_storage() -> None:
    base = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://medi_app:strong-password@db:5432/medi",
        "TOKEN_SECRET": "a-unique-production-token-secret-with-adequate-length",
        "CSRF_SECRET": "a-distinct-production-csrf-secret-with-adequate-length",
        "AUDIT_SIGNING_KEY": "a-separate-production-audit-signing-key-with-length",
        "PRIVACY_REFERENCE_KEY": "a-distinct-production-privacy-reference-key",
        "CORS_ORIGINS": "https://medi.example.org",
        "SEED_DEMO_DATA": "false",
        "SESSION_IDLE_TIMEOUT_MINUTES": "30",
        "RATE_LIMIT_BACKEND": "redis",
        "RATE_LIMIT_REDIS_URL": "rediss://redis.example.org:6380/0",
    }
    with pytest.raises(ConfigurationError, match="SCAN_STORAGE_BACKEND=s3"):
        get_settings(base)

    with pytest.raises(ConfigurationError, match="SCAN_STORAGE_SSE=aws:kms"):
        get_settings(
            {
                **base,
                "SCAN_STORAGE_BACKEND": "s3",
                "SCAN_STORAGE_BUCKET": "medi-private-production",
                "SCAN_STORAGE_REGION": "eu-central-1",
                "SCAN_STORAGE_SSE": "AES256",
            }
        )


@pytest.mark.parametrize(
    "origins",
    ["*", "https://medi.example.org/path", "https://medi.example.org?preview=true", "ftp://medi.example.org"],
)
def test_cors_origins_must_be_exact_http_origins(origins: str) -> None:
    with pytest.raises(ConfigurationError, match="CORS_ORIGINS"):
        get_settings({"CORS_ORIGINS": origins})


@pytest.mark.parametrize(
    ("variable_name", "value"),
    [
        ("SESSION_TTL_MINUTES", "four"),
        ("SESSION_IDLE_TIMEOUT_MINUTES", "0"),
        ("DATABASE_POOL_SIZE", "0"),
        ("DATABASE_MAX_OVERFLOW", "51"),
        ("DATABASE_POOL_TIMEOUT_SECONDS", "0"),
        ("DATABASE_STATEMENT_TIMEOUT_MS", "99"),
        ("DATABASE_SLOW_QUERY_THRESHOLD_MS", "9"),
        ("LOGIN_RATE_LIMIT_PER_MINUTE", "0"),
        ("SENSITIVE_RATE_LIMIT_PER_MINUTE", "10001"),
        ("DATA_DELETION_OPERATOR_ENABLED", "sometimes"),
        ("EXTERNAL_AI_ENABLED", "sometimes"),
    ],
)
def test_session_and_rate_limit_settings_reject_invalid_values(variable_name: str, value: str) -> None:
    with pytest.raises(ConfigurationError, match=variable_name):
        get_settings({variable_name: value})


def test_idle_timeout_cannot_exceed_absolute_session_lifetime() -> None:
    with pytest.raises(ConfigurationError, match="SESSION_IDLE_TIMEOUT_MINUTES"):
        get_settings({"SESSION_TTL_MINUTES": "30", "SESSION_IDLE_TIMEOUT_MINUTES": "60"})


def test_slow_query_threshold_must_be_lower_than_statement_timeout() -> None:
    with pytest.raises(ConfigurationError, match="DATABASE_SLOW_QUERY_THRESHOLD_MS"):
        get_settings({"DATABASE_STATEMENT_TIMEOUT_MS": "500", "DATABASE_SLOW_QUERY_THRESHOLD_MS": "500"})


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"RATE_LIMIT_BACKEND": "redis"}, "RATE_LIMIT_REDIS_URL"),
        ({"SESSION_COOKIE_SAMESITE": "none"}, "SESSION_COOKIE_SAMESITE"),
        ({"RATE_LIMIT_BACKEND": "database"}, "RATE_LIMIT_BACKEND"),
    ],
)
def test_cookie_and_shared_rate_limit_settings_reject_unsafe_values(changes: dict[str, str], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        get_settings(changes)


@pytest.mark.parametrize(
    "origin",
    ["*", "http://gateway.example.org", "https://gateway.example.org/path", "https://user@gateway.example.org"],
)
def test_external_ai_origins_must_be_exact_https_origins(origin: str) -> None:
    with pytest.raises(ConfigurationError, match="EXTERNAL_AI_ALLOWED_ORIGINS"):
        get_settings({"EXTERNAL_AI_ALLOWED_ORIGINS": origin})


def test_external_ai_requires_an_explicit_allowlist_when_enabled() -> None:
    with pytest.raises(ConfigurationError, match="EXTERNAL_AI_ALLOWED_ORIGINS"):
        get_settings({"EXTERNAL_AI_ENABLED": "true"})

    settings = get_settings(
        {
            "EXTERNAL_AI_ENABLED": "true",
            "EXTERNAL_AI_ALLOWED_ORIGINS": "https://ai-gateway.example.org,https://ai-gateway.example.org/",
        }
    )
    assert settings.external_ai_enabled is True
    assert settings.external_ai_allowed_origins == ("https://ai-gateway.example.org",)

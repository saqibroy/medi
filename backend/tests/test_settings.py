"""Tests for the development/production configuration boundary."""

import pytest

from backend.settings import ConfigurationError, DEVELOPMENT_CORS_ORIGINS, get_settings


def test_development_defaults_are_local_and_seed_demo_data() -> None:
    settings = get_settings({})

    assert settings.environment == "development"
    assert settings.cors_origins == DEVELOPMENT_CORS_ORIGINS
    assert settings.seed_demo_data is True


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
            "CORS_ORIGINS",
        ),
        (
            {
                "DATABASE_URL": "postgresql+psycopg://app:strong-password@db:5432/medi",
                "TOKEN_SECRET": "a-unique-production-token-secret-with-adequate-length",
                "CORS_ORIGINS": "https://medi.example.org",
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
            "CORS_ORIGINS": "https://medi.example.org,https://review.medi.example.org",
            "SEED_DEMO_DATA": "false",
            "SCAN_STORAGE_BACKEND": "s3",
            "SCAN_STORAGE_BUCKET": "medi-private-production",
            "SCAN_STORAGE_REGION": "eu-central-1",
            "SCAN_STORAGE_SSE": "aws:kms",
            "SCAN_STORAGE_KMS_KEY_ID": "arn:aws:kms:eu-central-1:123456789012:key/test-key",
        }
    )

    assert settings.is_production is True
    assert settings.seed_demo_data is False
    assert settings.cors_origins == ("https://medi.example.org", "https://review.medi.example.org")
    assert settings.scan_storage_backend == "s3"
    assert settings.scan_storage_sse == "aws:kms"


def test_production_rejects_local_or_unencrypted_storage() -> None:
    base = {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql+psycopg://medi_app:strong-password@db:5432/medi",
        "TOKEN_SECRET": "a-unique-production-token-secret-with-adequate-length",
        "CORS_ORIGINS": "https://medi.example.org",
        "SEED_DEMO_DATA": "false",
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
    [("SESSION_TTL_MINUTES", "four"), ("LOGIN_RATE_LIMIT_PER_MINUTE", "0"), ("SENSITIVE_RATE_LIMIT_PER_MINUTE", "10001")],
)
def test_session_and_rate_limit_settings_reject_invalid_values(variable_name: str, value: str) -> None:
    with pytest.raises(ConfigurationError, match=variable_name):
        get_settings({variable_name: value})

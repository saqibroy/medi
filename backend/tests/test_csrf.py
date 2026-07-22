"""Focused proofs for signed CSRF binding and production cookie attributes."""

from datetime import datetime, timedelta, timezone

from starlette.responses import Response

from backend.csrf import create_csrf_token, csrf_cookie_name, session_cookie_name, set_csrf_cookie, set_session_cookie, verify_csrf_token
from backend.settings import get_settings


def production_settings():
    return get_settings(
        {
            "APP_ENV": "production",
            "DATABASE_URL": "postgresql+psycopg://medi:secret@db:5432/medi",
            "TOKEN_SECRET": "production-token-secret-longer-than-thirty-two",
            "CSRF_SECRET": "production-csrf-secret-distinct-and-long-enough",
            "AUDIT_SIGNING_KEY": "production-audit-key-distinct-and-long-enough",
            "PRIVACY_REFERENCE_KEY": "production-privacy-reference-key-distinct-and-long",
            "CORS_ORIGINS": "https://medi.example.org",
            "SEED_DEMO_DATA": "false",
            "SESSION_IDLE_TIMEOUT_MINUTES": "60",
            "RATE_LIMIT_BACKEND": "redis",
            "RATE_LIMIT_REDIS_URL": "rediss://redis.example.org:6380/0",
            "SCAN_STORAGE_BACKEND": "s3",
            "SCAN_STORAGE_BUCKET": "medi-private",
            "SCAN_STORAGE_REGION": "eu-central-1",
            "SCAN_STORAGE_SSE": "aws:kms",
            "SCAN_STORAGE_KMS_KEY_ID": "test-key",
        }
    )


def test_csrf_signature_is_bound_to_the_session() -> None:
    settings = get_settings({})
    token = create_csrf_token("session-one", settings)

    assert verify_csrf_token(token, "session-one", settings)
    assert not verify_csrf_token(token, "session-two", settings)
    assert not verify_csrf_token(f"{token}tampered", "session-one", settings)


def test_production_cookies_are_host_only_secure_and_session_is_http_only() -> None:
    settings = production_settings()
    response = Response()
    set_session_cookie(response, "opaque", datetime.now(timezone.utc) + timedelta(minutes=5), settings)
    set_csrf_cookie(response, "signed", settings)
    cookie_headers = response.headers.getlist("set-cookie")

    assert session_cookie_name(settings) == "__Host-medi_session"
    assert csrf_cookie_name(settings) == "__Host-medi_csrf"
    assert all("Secure" in header and "Path=/" in header and "SameSite=lax" in header for header in cookie_headers)
    assert "HttpOnly" in cookie_headers[0]
    assert "HttpOnly" not in cookie_headers[1]
    assert all("Domain=" not in header for header in cookie_headers)

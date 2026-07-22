"""Session idle-expiry and administrator inventory route coverage."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from backend.models import User, UserSession
from backend.tests.test_phase1_routes import auth_headers, build_test_app, login


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_admin_session_inventory_is_credential_free_and_tenant_scoped(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        first_annotator_token = await login(client, "annotator@test.local")
        await login(client, "annotator@test.local")
        outside_admin_token = await login(client, "outside-admin@test.local")

        denied = await client.get("/auth/sessions", headers=auth_headers(first_annotator_token))
        inventory = await client.get("/auth/sessions", headers=auth_headers(admin_token))
        outside_inventory = await client.get("/auth/sessions", headers=auth_headers(outside_admin_token))

        assert denied.status_code == 403
        assert inventory.status_code == 200
        assert {item["user_email"] for item in inventory.json()} == {"admin@test.local", "annotator@test.local"}
        assert sum(item["current_session"] for item in inventory.json()) == 1
        assert {item["user_email"] for item in outside_inventory.json()} == {"outside-admin@test.local"}
        serialized = json.dumps(inventory.json())
        for prohibited in ("token", "digest", "ip_address", "user_agent"):
            assert prohibited not in serialized


@pytest.mark.anyio
async def test_admin_can_revoke_another_session_but_not_current_or_cross_tenant(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        outside_admin_token = await login(client, "outside-admin@test.local")

        inventory = (await client.get("/auth/sessions", headers=auth_headers(admin_token))).json()
        target = next(item for item in inventory if item["user_email"] == "annotator@test.local")
        current = next(item for item in inventory if item["current_session"])
        outside = (await client.get("/auth/sessions", headers=auth_headers(outside_admin_token))).json()[0]

        self_revoke = await client.post(f"/auth/sessions/{current['id']}/revoke", headers=auth_headers(admin_token))
        cross_tenant = await client.post(f"/auth/sessions/{outside['id']}/revoke", headers=auth_headers(admin_token))
        revoked = await client.post(f"/auth/sessions/{target['id']}/revoke", headers=auth_headers(admin_token))

        assert self_revoke.status_code == 409
        assert cross_tenant.status_code == 404
        assert revoked.status_code == 204
        assert (await client.get("/auth/me", headers=auth_headers(annotator_token))).status_code == 401
        remaining = (await client.get("/auth/sessions", headers=auth_headers(admin_token))).json()
        assert target["id"] not in {item["id"] for item in remaining}

        audits = await client.get("/audit-events?action=session.revoke", headers=auth_headers(admin_token))
        assert audits.status_code == 200
        assert any(event["result"] == "succeeded" and event["target_id"] == target["id"] for event in audits.json())


@pytest.mark.anyio
async def test_idle_sessions_are_rejected_and_excluded_from_inventory(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        annotator_token = await login(client, "annotator@test.local")

        with app.state.test_session_factory() as db:
            annotator = db.scalar(select(User).where(User.email == "annotator@test.local"))
            assert annotator is not None
            user_session = db.scalar(select(UserSession).where(UserSession.user_id == annotator.id))
            assert user_session is not None
            user_session.last_seen_at = datetime.now(timezone.utc) - timedelta(minutes=61)
            db.commit()

        assert (await client.get("/auth/me", headers=auth_headers(annotator_token))).status_code == 401
        inventory = (await client.get("/auth/sessions", headers=auth_headers(admin_token))).json()
        assert "annotator@test.local" not in {item["user_email"] for item in inventory}

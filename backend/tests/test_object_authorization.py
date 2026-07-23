"""Complete role and cross-tenant object authorization proofs for API routes."""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.routing import APIRoute
from sqlalchemy import select

from backend.models import Annotation, Label, Project, Scan, User
from backend.routers import annotations, audit_events, auth, data_governance, external_ai_governance, health, privacy_governance, projects, scans, users
from backend.security import hash_password
from backend.tests.test_phase1_routes import auth_headers, build_test_app, login, make_png_bytes


ROUTERS = (
    auth.router,
    audit_events.router,
    data_governance.router,
    external_ai_governance.router,
    privacy_governance.router,
    health.router,
    projects.router,
    scans.router,
    annotations.router,
    users.router,
)

PUBLIC_ROUTES = {
    ("GET", "/auth/csrf"),
    ("POST", "/auth/login"),
    ("POST", "/auth/logout"),
    ("GET", "/health/live"),
    ("GET", "/health/ready"),
    ("GET", "/health"),
}

ADMIN_ROUTES = {
    ("GET", "/auth/sessions"),
    ("POST", "/auth/sessions/{session_id}/revoke"),
    ("GET", "/audit-events"),
    ("POST", "/projects"),
    ("POST", "/projects/{project_id}/releases"),
    ("POST", "/dataset-releases/{release_id}/artifact"),
    ("POST", "/dataset-releases/{release_id}/revoke"),
    ("PUT", "/projects/{project_id}"),
    ("POST", "/projects/{project_id}/labels"),
    ("PUT", "/labels/{label_id}"),
    ("DELETE", "/labels/{label_id}"),
    ("POST", "/scans"),
    ("POST", "/scans/upload"),
    ("POST", "/scans/{scan_id}/reprocess"),
    ("DELETE", "/annotations/{annotation_id}"),
}

ANNOTATOR_ROUTES = {
    ("POST", "/annotations"),
    ("PUT", "/annotations/{annotation_id}"),
    ("POST", "/annotations/{annotation_id}/mask"),
    ("DELETE", "/annotations/{annotation_id}/mask/{slice_index}"),
}

REVIEWER_ROUTES = {("PATCH", "/annotations/{annotation_id}/review")}

AUTHENTICATED_ROUTES = {
    ("GET", "/auth/me"),
    ("GET", "/projects"),
    ("GET", "/projects/{project_id}"),
    ("GET", "/projects/{project_id}/releases"),
    ("GET", "/dataset-releases/{release_id}"),
    ("GET", "/dataset-releases/{release_id}/artifact"),
    ("GET", "/projects/{project_id}/scans"),
    ("GET", "/projects/{project_id}/labels"),
    ("GET", "/projects/{project_id}/export"),
    ("GET", "/projects/{project_id}/stats"),
    ("GET", "/projects/{project_id}/export/coco"),
    ("GET", "/projects/{project_id}/export/csv"),
    ("GET", "/projects/{project_id}/export/yolo"),
    ("GET", "/projects/{project_id}/export/segmentation"),
    ("GET", "/scans"),
    ("GET", "/scans/{scan_id}"),
    ("GET", "/scans/{scan_id}/slice/{slice_index}"),
    ("GET", "/scans/{scan_id}/slice/{slice_index}/metadata"),
    ("GET", "/scans/{scan_id}/slice/{slice_index}/url"),
    ("GET", "/scans/{scan_id}/metadata"),
    ("GET", "/scans/{scan_id}/annotations"),
    ("GET", "/scans/{scan_id}/export"),
    ("GET", "/scans/{scan_id}/export/coco"),
    ("GET", "/scans/{scan_id}/export/csv"),
    ("GET", "/scans/{scan_id}/export/yolo"),
    ("GET", "/scans/{scan_id}/export/segmentation"),
    ("GET", "/scans/{scan_id}/stats"),
    ("GET", "/annotations"),
    ("GET", "/annotations/search"),
    ("GET", "/annotations/{annotation_id}"),
    ("GET", "/annotations/{annotation_id}/history"),
    ("GET", "/annotations/{annotation_id}/mask/{slice_index}"),
    ("GET", "/users"),
}

GOVERNANCE_ROUTES = {
    (method, route.path)
    for router in (data_governance.router, external_ai_governance.router, privacy_governance.router)
    for route in router.routes
    if isinstance(route, APIRoute)
    for method in route.methods
}

OBJECT_ROUTE_TEMPLATES = {
    (method, route.path)
    for router in ROUTERS
    for route in router.routes
    if isinstance(route, APIRoute) and "{" in route.path
    for method in route.methods
}


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


def _route_inventory() -> dict[tuple[str, str], APIRoute]:
    return {
        (method, route.path): route
        for router in ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }


def test_every_route_has_an_explicit_authentication_policy() -> None:
    """Fail closed when a route is added without extending the policy matrix."""

    expected = PUBLIC_ROUTES | ADMIN_ROUTES | ANNOTATOR_ROUTES | REVIEWER_ROUTES | AUTHENTICATED_ROUTES | GOVERNANCE_ROUTES
    inventory = _route_inventory()
    assert set(inventory) == expected

    expected_dependency = {
        **{route: None for route in PUBLIC_ROUTES},
        **{route: "get_current_user" for route in AUTHENTICATED_ROUTES},
        **{route: "require_admin" for route in ADMIN_ROUTES | GOVERNANCE_ROUTES},
        **{route: "require_annotator" for route in ANNOTATOR_ROUTES},
        **{route: "require_reviewer" for route in REVIEWER_ROUTES},
    }
    auth_dependencies = {"get_current_user", "require_admin", "require_annotator", "require_reviewer"}
    for route_key, route in inventory.items():
        actual = {
            dependency.call.__name__
            for dependency in route.dependant.dependencies
            if getattr(dependency.call, "__name__", None) in auth_dependencies
        }
        wanted = expected_dependency[route_key]
        assert actual == ({wanted} if wanted is not None else set()), route_key


def _policy_payload(reference: str) -> dict[str, object]:
    return {
        "approval_reference": reference,
        "original_minimum_days": 0,
        "mask_minimum_days": 0,
        "metadata_minimum_days": 0,
        "dataset_release_minimum_days": 0,
        "audit_minimum_days": 365,
        "backup_retention_days": 30,
        "rpo_hours": 4,
        "rto_hours": 8,
    }


def _provider_payload() -> dict[str, object]:
    return {
        "provider_key": "outside-approved-gateway",
        "display_name": "Outside Approved Gateway",
        "model_name": "Synthetic Model",
        "model_version": "2026-07-22",
        "purpose_code": "annotation_assistance",
        "endpoint_origin": "https://outside-ai.example.org",
        "region_code": "eu-central",
        "data_classes": ["label_taxonomy"],
        "retention_days": 0,
        "training_use_allowed": False,
        "subprocessors": ["SUBPROCESSOR-OUTSIDE-001"],
        "transfer_mechanism": "standard_contractual_clauses",
        "contract_owner_reference": "CONTRACT-OUTSIDE-001",
        "approval_reference": "AI-PROVIDER-OUTSIDE-001",
    }


def _processing_payload(policy_id: str) -> dict[str, object]:
    return {
        "activity_key": "outside-research-annotation",
        "organization_role": "processor",
        "purpose_code": "research_dataset_annotation",
        "lawful_basis": "contract",
        "health_data_processed": True,
        "article9_condition": "research_statistics",
        "data_subject_categories": ["research_participants"],
        "personal_data_categories": ["pseudonymized_medical_images", "annotation_data"],
        "recipient_categories": ["authorized_workspace_users"],
        "processor_references": ["PROCESSOR-OUTSIDE-001"],
        "processing_locations": ["eu-central-1"],
        "transfer_mechanism": "not_applicable",
        "transfer_safeguard_reference": None,
        "retention_policy_id": policy_id,
        "security_measure_references": ["SECURITY-BASELINE-001"],
        "dpia_required": True,
        "dpia_outcome": "approved",
        "dpia_reference": "DPIA-OUTSIDE-001",
        "dpo_review_reference": "DPO-OUTSIDE-001",
        "approval_reference": "ROPA-OUTSIDE-001",
    }


def _seed_outside_imaging_graph(app: object) -> dict[str, str]:
    session_factory = app.state.test_session_factory  # type: ignore[attr-defined]
    with session_factory() as db:
        project = db.scalar(select(Project).where(Project.name == "Outside CT"))
        inside_project = db.scalar(select(Project).where(Project.name == "Brain MRI"))
        outside_user = db.scalar(select(User).where(User.email == "outside-admin@test.local"))
        assert project is not None and inside_project is not None and outside_user is not None
        db.add(
            User(
                organization_id=inside_project.organization_id,
                email="privacy-admin@test.local",
                full_name="Privacy Admin",
                password_hash=hash_password("password"),
                role="admin",
            )
        )
        label = Label(project_id=project.id, name="outside-lesion", color="#334455")
        scan = Scan(project_id=project.id, name="Outside synthetic CT", file_path="outside-synthetic.nii.gz", modality="CT", num_slices=4)
        db.add_all([label, scan])
        db.flush()
        annotation = Annotation(
            project_id=project.id,
            scan_id=scan.id,
            label_id=label.id,
            label=label.name,
            annotation_type="bounding_box",
            coordinates={"x": 5, "y": 5, "width": 10, "height": 10},
            slice_index=0,
            created_by="Outside Admin",
            assigned_to_user_id=outside_user.id,
            review_status="approved",
        )
        db.add(annotation)
        db.commit()
        return {
            "project": str(project.id),
            "label": str(label.id),
            "scan": str(scan.id),
            "annotation": str(annotation.id),
            "user": str(outside_user.id),
            "organization": str(project.organization_id),
        }


async def _create_outside_objects(client: httpx.AsyncClient, token: str, seeded: dict[str, str]) -> dict[str, str]:
    headers = auth_headers(token)
    release = await client.post(f"/projects/{seeded['project']}/releases", headers=headers)
    policy = await client.post("/governance/retention-policies", json=_policy_payload("POLICY-OUTSIDE-001"), headers=headers)
    hold = await client.post(
        "/governance/legal-holds",
        json={"scope_type": "project", "scope_id": seeded["project"], "reason_code": "regulatory", "approval_reference": "HOLD-OUTSIDE-001"},
        headers=headers,
    )
    deletion = await client.post(
        "/governance/deletion-requests",
        json={"scope_type": "project", "scope_id": seeded["project"], "reason_code": "source_withdrawal", "approval_reference": "DELETE-OUTSIDE-001"},
        headers=headers,
    )
    provider = await client.post("/governance/external-ai/providers", json=_provider_payload(), headers=headers)
    flow = await client.post(
        "/governance/external-ai/data-flows",
        json={
            "project_id": seeded["project"],
            "provider_approval_id": provider.json()["id"],
            "purpose_code": "annotation_assistance",
            "data_classes": ["label_taxonomy"],
            "approval_reference": "AI-FLOW-OUTSIDE-001",
        },
        headers=headers,
    )
    decision = await client.post(
        "/governance/external-ai/evaluate",
        json={"data_flow_id": flow.json()["id"], "purpose_code": "annotation_assistance", "requested_data_classes": ["label_taxonomy"]},
        headers=headers,
    )
    processing = await client.post(
        "/governance/privacy/processing-records",
        json=_processing_payload(policy.json()["id"]),
        headers=headers,
    )
    privacy_request = await client.post(
        "/governance/privacy/requests",
        json={
            "case_reference": "PRIVACY-OUTSIDE-001",
            "external_subject_reference": "SYNTHETIC-OUTSIDE-SUBJECT",
            "request_type": "access",
            "scope_type": "project",
            "scope_id": seeded["project"],
        },
        headers=headers,
    )
    sessions = await client.get("/auth/sessions", headers=headers)
    responses = (release, policy, hold, deletion, provider, flow, decision, processing, privacy_request, sessions)
    assert all(response.status_code in {200, 201} for response in responses), [(response.status_code, response.text) for response in responses]
    return {
        **seeded,
        "release": release.json()["id"],
        "policy": policy.json()["id"],
        "hold": hold.json()["id"],
        "deletion": deletion.json()["id"],
        "provider": provider.json()["id"],
        "flow": flow.json()["id"],
        "decision": decision.json()["id"],
        "processing": processing.json()["id"],
        "privacy_request": privacy_request.json()["id"],
        "session": sessions.json()[0]["id"],
    }


def _object_route_cases(ids: dict[str, str]) -> list[tuple[str, str, str, dict[str, object]]]:
    project = ids["project"]
    scan = ids["scan"]
    annotation = ids["annotation"]
    cases = [
        ("POST", "/auth/sessions/{session_id}/revoke", f"/auth/sessions/{ids['session']}/revoke", {}),
        ("POST", "/governance/legal-holds/{hold_id}/release", f"/governance/legal-holds/{ids['hold']}/release", {}),
        ("GET", "/governance/deletion-requests/{request_id}", f"/governance/deletion-requests/{ids['deletion']}", {}),
        ("POST", "/governance/deletion-requests/{request_id}/approve", f"/governance/deletion-requests/{ids['deletion']}/approve", {}),
        ("POST", "/governance/deletion-requests/{request_id}/cancel", f"/governance/deletion-requests/{ids['deletion']}/cancel", {}),
        ("POST", "/governance/external-ai/providers/{provider_id}/revoke", f"/governance/external-ai/providers/{ids['provider']}/revoke", {}),
        ("POST", "/governance/external-ai/data-flows/{flow_id}/revoke", f"/governance/external-ai/data-flows/{ids['flow']}/revoke", {}),
        ("POST", "/governance/privacy/processing-records/{record_id}/revoke", f"/governance/privacy/processing-records/{ids['processing']}/revoke", {}),
        ("GET", "/governance/privacy/requests/{request_id}", f"/governance/privacy/requests/{ids['privacy_request']}", {}),
        ("POST", "/governance/privacy/requests/{request_id}/verify-identity", f"/governance/privacy/requests/{ids['privacy_request']}/verify-identity", {"json": {"evidence_reference": "IDENTITY-001"}}),
        ("POST", "/governance/privacy/requests/{request_id}/accept", f"/governance/privacy/requests/{ids['privacy_request']}/accept", {"json": {"evidence_reference": "RIGHTS-001"}}),
        ("POST", "/governance/privacy/requests/{request_id}/fulfill", f"/governance/privacy/requests/{ids['privacy_request']}/fulfill", {"json": {"evidence_reference": "DELIVERY-001", "outcome_code": "secure_delivery"}}),
        ("POST", "/governance/privacy/requests/{request_id}/deny", f"/governance/privacy/requests/{ids['privacy_request']}/deny", {"json": {"evidence_reference": "DENIAL-001", "reason_code": "identity_not_verified"}}),
        ("POST", "/governance/privacy/requests/{request_id}/cancel", f"/governance/privacy/requests/{ids['privacy_request']}/cancel", {"json": {"evidence_reference": "CANCEL-001", "reason_code": "requester_withdrew"}}),
        ("POST", "/governance/privacy/requests/{request_id}/extend", f"/governance/privacy/requests/{ids['privacy_request']}/extend", {"json": {"evidence_reference": "EXTEND-001", "reason_code": "complexity"}}),
        ("GET", "/projects/{project_id}", f"/projects/{project}", {}),
        ("GET", "/projects/{project_id}/releases", f"/projects/{project}/releases", {}),
        ("POST", "/projects/{project_id}/releases", f"/projects/{project}/releases", {}),
        ("GET", "/dataset-releases/{release_id}", f"/dataset-releases/{ids['release']}", {}),
        ("GET", "/dataset-releases/{release_id}/artifact", f"/dataset-releases/{ids['release']}/artifact", {}),
        ("POST", "/dataset-releases/{release_id}/artifact", f"/dataset-releases/{ids['release']}/artifact", {}),
        ("POST", "/dataset-releases/{release_id}/revoke", f"/dataset-releases/{ids['release']}/revoke", {"json": {"reason_code": "quality_issue"}}),
        ("PUT", "/projects/{project_id}", f"/projects/{project}", {"json": {"name": "Blocked update"}}),
        ("GET", "/projects/{project_id}/scans", f"/projects/{project}/scans", {}),
        ("GET", "/projects/{project_id}/labels", f"/projects/{project}/labels", {}),
        ("GET", "/projects/{project_id}/export", f"/projects/{project}/export", {}),
        ("GET", "/projects/{project_id}/stats", f"/projects/{project}/stats", {}),
        ("GET", "/projects/{project_id}/export/coco", f"/projects/{project}/export/coco", {}),
        ("GET", "/projects/{project_id}/export/csv", f"/projects/{project}/export/csv", {}),
        ("GET", "/projects/{project_id}/export/yolo", f"/projects/{project}/export/yolo", {}),
        ("GET", "/projects/{project_id}/export/segmentation", f"/projects/{project}/export/segmentation", {}),
        ("POST", "/projects/{project_id}/labels", f"/projects/{project}/labels", {"json": {"name": "blocked-label", "color": "#112233"}}),
        ("PUT", "/labels/{label_id}", f"/labels/{ids['label']}", {"json": {"name": "blocked-label"}}),
        ("DELETE", "/labels/{label_id}", f"/labels/{ids['label']}", {}),
        ("GET", "/scans/{scan_id}", f"/scans/{scan}", {}),
        ("GET", "/scans/{scan_id}/slice/{slice_index}", f"/scans/{scan}/slice/0", {}),
        ("GET", "/scans/{scan_id}/slice/{slice_index}/metadata", f"/scans/{scan}/slice/0/metadata", {}),
        ("GET", "/scans/{scan_id}/slice/{slice_index}/url", f"/scans/{scan}/slice/0/url", {}),
        ("GET", "/scans/{scan_id}/metadata", f"/scans/{scan}/metadata", {}),
        ("POST", "/scans/{scan_id}/reprocess", f"/scans/{scan}/reprocess", {}),
        ("GET", "/scans/{scan_id}/annotations", f"/scans/{scan}/annotations", {}),
        ("GET", "/scans/{scan_id}/export", f"/scans/{scan}/export", {}),
        ("GET", "/scans/{scan_id}/export/coco", f"/scans/{scan}/export/coco", {}),
        ("GET", "/scans/{scan_id}/export/csv", f"/scans/{scan}/export/csv", {}),
        ("GET", "/scans/{scan_id}/export/yolo", f"/scans/{scan}/export/yolo", {}),
        ("GET", "/scans/{scan_id}/export/segmentation", f"/scans/{scan}/export/segmentation", {}),
        ("GET", "/scans/{scan_id}/stats", f"/scans/{scan}/stats", {}),
        ("GET", "/annotations/{annotation_id}", f"/annotations/{annotation}", {}),
        ("GET", "/annotations/{annotation_id}/history", f"/annotations/{annotation}/history", {}),
        ("POST", "/annotations/{annotation_id}/mask", f"/annotations/{annotation}/mask", {"data": {"slice_index": "0"}, "files": {"file": ("mask.png", make_png_bytes(16, 16), "image/png")}}),
        ("GET", "/annotations/{annotation_id}/mask/{slice_index}", f"/annotations/{annotation}/mask/0", {}),
        ("DELETE", "/annotations/{annotation_id}/mask/{slice_index}", f"/annotations/{annotation}/mask/0", {}),
        ("PUT", "/annotations/{annotation_id}", f"/annotations/{annotation}", {"json": {"notes": "blocked update"}}),
        ("PATCH", "/annotations/{annotation_id}/review", f"/annotations/{annotation}/review", {"json": {"reviewer": "Admin User", "review_status": "approved", "notes": None}}),
        ("DELETE", "/annotations/{annotation_id}", f"/annotations/{annotation}", {}),
    ]
    return cases


@pytest.mark.anyio
async def test_every_object_path_is_cross_tenant_opaque_and_collections_are_scoped(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    outside_seeded = _seed_outside_imaging_graph(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        inside_token = await login(client, "admin@test.local")
        outside_token = await login(client, "outside-admin@test.local")
        outside = await _create_outside_objects(client, outside_token, outside_seeded)
        cases = _object_route_cases(outside)

        assert {(method, template) for method, template, _path, _kwargs in cases} == OBJECT_ROUTE_TEMPLATES
        for method, template, path, kwargs in cases:
            response = await client.request(method, path, headers=auth_headers(inside_token), **kwargs)
            assert response.status_code == 404, (method, template, response.status_code, response.text)

        collection_paths = (
            "/projects",
            "/scans",
            "/annotations",
            "/annotations/search",
            "/users",
            "/audit-events",
            "/auth/sessions",
            "/governance/retention-policies",
            "/governance/legal-holds",
            "/governance/deletion-requests",
            "/governance/external-ai/providers",
            "/governance/external-ai/data-flows",
            "/governance/external-ai/decisions",
            "/governance/privacy/processing-records",
            "/governance/privacy/requests",
        )
        outside_sentinels = set(outside.values()) | {"outside-admin@test.local", "Outside CT", "outside-lesion"}
        for path in collection_paths:
            response = await client.get(path, headers=auth_headers(inside_token))
            assert response.status_code == 200, (path, response.status_code, response.text)
            if path == "/audit-events":
                assert all(event["organization_id"] != outside["organization"] for event in response.json())
                assert all(event["actor_user_id"] != outside["user"] for event in response.json())
            else:
                serialized = json.dumps(response.json())
                assert not any(sentinel in serialized for sentinel in outside_sentinels), path


@pytest.mark.anyio
async def test_cross_tenant_body_references_are_opaque_and_cannot_reparent_annotations(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    outside_seeded = _seed_outside_imaging_graph(app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        admin_token = await login(client, "admin@test.local")
        privacy_admin_token = await login(client, "privacy-admin@test.local")
        annotator_token = await login(client, "annotator@test.local")
        outside_token = await login(client, "outside-admin@test.local")
        outside = await _create_outside_objects(client, outside_token, outside_seeded)
        own_project = (await client.get("/projects", headers=auth_headers(admin_token))).json()[0]
        own_scan = (await client.get(f"/projects/{own_project['id']}/scans", headers=auth_headers(admin_token))).json()[0]
        own_label = (await client.get(f"/projects/{own_project['id']}/labels", headers=auth_headers(admin_token))).json()[0]
        own_annotation = (await client.get("/annotations", headers=auth_headers(admin_token))).json()[0]
        own_policy = await client.post(
            "/governance/retention-policies",
            json=_policy_payload("POLICY-INSIDE-001"),
            headers=auth_headers(admin_token),
        )
        own_provider = await client.post(
            "/governance/external-ai/providers",
            json={**_provider_payload(), "provider_key": "inside-approved-gateway", "approval_reference": "AI-PROVIDER-INSIDE-001"},
            headers=auth_headers(admin_token),
        )
        own_privacy_request = await client.post(
            "/governance/privacy/requests",
            json={
                "case_reference": "PRIVACY-INSIDE-ERASURE-001",
                "external_subject_reference": "SYNTHETIC-INSIDE-SUBJECT",
                "request_type": "erasure",
                "scope_type": "project",
                "scope_id": own_project["id"],
            },
            headers=auth_headers(admin_token),
        )
        verified_privacy_request = await client.post(
            f"/governance/privacy/requests/{own_privacy_request.json()['id']}/verify-identity",
            json={"evidence_reference": "IDENTITY-INSIDE-001"},
            headers=auth_headers(privacy_admin_token),
        )
        assert own_policy.status_code == 201
        assert own_provider.status_code == 201
        assert own_privacy_request.status_code == 201
        assert verified_privacy_request.status_code == 200

        annotation_payload = {
            "project_id": own_project["id"],
            "scan_id": own_scan["id"],
            "label_id": own_label["id"],
            "label": own_label["name"],
            "annotation_type": "bounding_box",
            "coordinates": {"x": 1, "y": 1, "width": 5, "height": 5},
            "slice_index": 0,
            "created_by": "Annotator User",
        }
        requests = (
            ("POST", "/scans", auth_headers(admin_token), {"json": {"project_id": outside["project"], "name": "blocked", "modality": "CT", "num_slices": 1}}),
            ("POST", "/scans/upload", auth_headers(admin_token), {"data": {"project_id": outside["project"], "name": "blocked", "modality": "CT", "num_slices": "1"}, "files": {"file": ("synthetic.dcm", b"synthetic-only", "application/dicom")}}),
            ("POST", "/annotations", auth_headers(annotator_token), {"json": {**annotation_payload, "scan_id": outside["scan"]}}),
            ("POST", "/annotations", auth_headers(annotator_token), {"json": {**annotation_payload, "project_id": outside["project"]}}),
            ("POST", "/annotations", auth_headers(annotator_token), {"json": {**annotation_payload, "label_id": outside["label"]}}),
            ("POST", "/annotations", auth_headers(annotator_token), {"json": {**annotation_payload, "assigned_to_user_id": outside["user"]}}),
            ("PUT", f"/annotations/{own_annotation['id']}", auth_headers(annotator_token), {"json": {"project_id": outside["project"]}}),
            ("PUT", f"/annotations/{own_annotation['id']}", auth_headers(annotator_token), {"json": {"label_id": outside["label"]}}),
            ("PUT", f"/annotations/{own_annotation['id']}", auth_headers(annotator_token), {"json": {"assigned_to_user_id": outside["user"]}}),
            ("POST", "/governance/legal-holds", auth_headers(admin_token), {"json": {"scope_type": "project", "scope_id": outside["project"], "reason_code": "regulatory", "approval_reference": "HOLD-BLOCKED-001"}}),
            ("POST", "/governance/deletion-requests", auth_headers(admin_token), {"json": {"scope_type": "project", "scope_id": outside["project"], "reason_code": "source_withdrawal", "approval_reference": "DELETE-BLOCKED-001"}}),
            ("POST", "/governance/privacy/processing-records", auth_headers(admin_token), {"json": _processing_payload(outside["policy"])}),
            ("POST", "/governance/privacy/requests", auth_headers(admin_token), {"json": {"case_reference": "PRIVACY-BLOCKED-001", "external_subject_reference": "SYNTHETIC-BLOCKED-SUBJECT", "request_type": "access", "scope_type": "project", "scope_id": outside["project"]}}),
            ("POST", f"/governance/privacy/requests/{own_privacy_request.json()['id']}/accept", auth_headers(admin_token), {"json": {"evidence_reference": "RIGHTS-INSIDE-001", "linked_deletion_request_id": outside["deletion"]}}),
            ("POST", "/governance/external-ai/data-flows", auth_headers(admin_token), {"json": {"project_id": own_project["id"], "provider_approval_id": outside["provider"], "purpose_code": "annotation_assistance", "data_classes": ["label_taxonomy"], "approval_reference": "AI-FLOW-BLOCKED-PROVIDER"}}),
            ("POST", "/governance/external-ai/data-flows", auth_headers(admin_token), {"json": {"project_id": outside["project"], "provider_approval_id": own_provider.json()["id"], "purpose_code": "annotation_assistance", "data_classes": ["label_taxonomy"], "approval_reference": "AI-FLOW-BLOCKED-PROJECT"}}),
            ("POST", "/governance/external-ai/evaluate", auth_headers(admin_token), {"json": {"data_flow_id": outside["flow"], "purpose_code": "annotation_assistance", "requested_data_classes": ["label_taxonomy"]}}),
        )
        for method, path, headers, kwargs in requests:
            response = await client.request(method, path, headers=headers, **kwargs)
            assert response.status_code == 404, (method, path, response.status_code, response.text)

        scoped_annotation_filter = await client.get(
            f"/annotations?scan_id={outside['scan']}",
            headers=auth_headers(admin_token),
        )
        assert scoped_annotation_filter.status_code == 200 and scoped_annotation_filter.json() == []

        unchanged = await client.get(f"/annotations/{own_annotation['id']}", headers=auth_headers(admin_token))
        assert unchanged.status_code == 200
        assert unchanged.json()["project_id"] == own_project["id"]
        assert unchanged.json()["label_id"] == own_label["id"]

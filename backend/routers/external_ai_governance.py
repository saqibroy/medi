"""Administrator-only external AI registry and deny-by-default decision APIs."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import (
    ExternalAIDataFlowCreate,
    ExternalAIDataFlowRead,
    ExternalAIEgressDecisionRead,
    ExternalAIEgressEvaluate,
    ExternalAIProviderCreate,
    ExternalAIProviderRead,
    ExternalAIStatusRead,
)
from ..security import require_admin
from ..services import external_ai_governance_service
from ..services.audit_service import mark_request_target


router = APIRouter(prefix="/governance/external-ai", tags=["external-ai-governance"])


@router.get("/status", response_model=ExternalAIStatusRead)
async def get_external_ai_status(current_user: User = Depends(require_admin)) -> ExternalAIStatusRead:
    del current_user
    return external_ai_governance_service.external_ai_status()


@router.get("/providers", response_model=list[ExternalAIProviderRead])
async def list_external_ai_providers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[ExternalAIProviderRead]:
    return external_ai_governance_service.list_providers(db, current_user)


@router.post("/providers", response_model=ExternalAIProviderRead, status_code=201)
async def create_external_ai_provider(
    request: Request,
    payload: ExternalAIProviderCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ExternalAIProviderRead:
    provider = external_ai_governance_service.create_provider(db, payload, current_user)
    mark_request_target(request, provider["id"], provider_version=provider["version"], purpose_code=provider["purpose_code"])
    return provider


@router.post("/providers/{provider_id}/revoke", response_model=ExternalAIProviderRead)
async def revoke_external_ai_provider(
    request: Request,
    provider_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ExternalAIProviderRead:
    provider = external_ai_governance_service.revoke_provider(db, provider_id, current_user)
    mark_request_target(request, provider["id"], provider_version=provider["version"], purpose_code=provider["purpose_code"])
    return provider


@router.get("/data-flows", response_model=list[ExternalAIDataFlowRead])
async def list_external_ai_data_flows(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[ExternalAIDataFlowRead]:
    return external_ai_governance_service.list_data_flows(db, current_user)


@router.post("/data-flows", response_model=ExternalAIDataFlowRead, status_code=201)
async def create_external_ai_data_flow(
    request: Request,
    payload: ExternalAIDataFlowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ExternalAIDataFlowRead:
    flow = external_ai_governance_service.create_data_flow(db, payload, current_user)
    mark_request_target(request, flow["id"], purpose_code=flow["purpose_code"], data_class_count=len(flow["data_classes"]))
    return flow


@router.post("/data-flows/{flow_id}/revoke", response_model=ExternalAIDataFlowRead)
async def revoke_external_ai_data_flow(
    request: Request,
    flow_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ExternalAIDataFlowRead:
    flow = external_ai_governance_service.revoke_data_flow(db, flow_id, current_user)
    mark_request_target(request, flow["id"], purpose_code=flow["purpose_code"], data_class_count=len(flow["data_classes"]))
    return flow


@router.post("/evaluate", response_model=ExternalAIEgressDecisionRead)
async def evaluate_external_ai_egress(
    request: Request,
    payload: ExternalAIEgressEvaluate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ExternalAIEgressDecisionRead:
    decision = external_ai_governance_service.evaluate_egress(db, payload, current_user)
    mark_request_target(
        request,
        decision.id,
        decision_result=decision.result,
        reason_code=decision.reason_code,
        purpose_code=decision.purpose_code,
        data_class_count=len(decision.requested_data_classes),
    )
    return decision


@router.get("/decisions", response_model=list[ExternalAIEgressDecisionRead])
async def list_external_ai_decisions(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> list[ExternalAIEgressDecisionRead]:
    return external_ai_governance_service.list_decisions(db, current_user, limit)

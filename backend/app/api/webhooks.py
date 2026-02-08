"""Webhook subscription API endpoints."""

import httpx
from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.db.repositories import WebhookRepository
from app.schemas.webhook import (
    WebhookCreateRequest,
    WebhookListResponse,
    WebhookResponse,
    WebhookTestRequest,
    WebhookTestResponse,
    WebhookUpdateRequest,
)

router = APIRouter()


@router.get("", response_model=WebhookListResponse)
async def list_webhooks(
    current_user: CurrentUser,
    db: DbSession,
) -> WebhookListResponse:
    """Get list of webhook subscriptions."""
    webhook_repo = WebhookRepository(db)
    webhooks = await webhook_repo.get_by_user_id(current_user.id)
    return WebhookListResponse(
        webhooks=[WebhookResponse.model_validate(w) for w in webhooks]
    )


@router.post("", response_model=WebhookResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    data: WebhookCreateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> WebhookResponse:
    """Create a new webhook subscription."""
    webhook_repo = WebhookRepository(db)
    webhook = await webhook_repo.create_webhook(
        user_id=current_user.id,
        name=data.name,
        url=str(data.url),
        event_types=[e.value for e in data.event_types],
    )
    return WebhookResponse.model_validate(webhook)


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> WebhookResponse:
    """Get a webhook subscription by ID."""
    webhook_repo = WebhookRepository(db)
    webhook = await webhook_repo.get(webhook_id)

    if not webhook or webhook.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    return WebhookResponse.model_validate(webhook)


@router.put("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: str,
    data: WebhookUpdateRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> WebhookResponse:
    """Update a webhook subscription."""
    webhook_repo = WebhookRepository(db)
    webhook = await webhook_repo.get(webhook_id)

    if not webhook or webhook.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    updates = {}
    if data.name is not None:
        updates["name"] = data.name
    if data.url is not None:
        updates["url"] = str(data.url)
    if data.enabled is not None:
        updates["enabled"] = data.enabled
    if data.event_types is not None:
        updates["event_types"] = [e.value for e in data.event_types]

    if updates:
        webhook = await webhook_repo.update(webhook, **updates)

    return WebhookResponse.model_validate(webhook)


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Delete a webhook subscription."""
    webhook_repo = WebhookRepository(db)
    webhook = await webhook_repo.get(webhook_id)

    if not webhook or webhook.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    await webhook_repo.delete(webhook)


@router.post("/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    webhook_id: str,
    data: WebhookTestRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> WebhookTestResponse:
    """Send a test event to a webhook."""
    webhook_repo = WebhookRepository(db)
    webhook = await webhook_repo.get(webhook_id)

    if not webhook or webhook.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    # Send test request
    test_payload = {
        "type": data.event_type.value,
        "test": True,
        "user_id": current_user.id,
        "data": {"message": "This is a test event from Alfred"},
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                webhook.url,
                json=test_payload,
                headers={"Content-Type": "application/json"},
            )
            return WebhookTestResponse(
                success=response.is_success,
                status_code=response.status_code,
            )
    except httpx.RequestError as e:
        return WebhookTestResponse(
            success=False,
            error=str(e),
        )

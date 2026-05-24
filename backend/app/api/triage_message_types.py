"""Message Types API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, DbSession
from app.db.models.triage import ChannelTypeRule, MessageType
from app.db.repositories import FeatureAccessRepository
from app.schemas.triage import (
    ChannelTypeRuleCreate,
    ChannelTypeRuleResponse,
    MessageTypeCreate,
    MessageTypeResponse,
    MessageTypeSuggestion,
    MessageTypeUpdate,
)

router = APIRouter()


async def _check_triage_access(user_id: str, db: AsyncSession, role: str) -> None:
    """Check if user has triage feature access."""
    repo = FeatureAccessRepository(db)
    if role != "admin" and not await repo.is_enabled(user_id, "card:triage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Triage feature not enabled",
        )


# Message Types CRUD


@router.get("/message-types", response_model=list[MessageTypeResponse])
async def list_message_types(
    include_archived: bool = False,
    current_user: CurrentUser = None,
    db: DbSession = None,
) -> list[MessageType]:
    """List all user's message types."""
    await _check_triage_access(current_user.id, db, current_user.role)
    query = select(MessageType).where(MessageType.user_id == current_user.id)
    if not include_archived:
        query = query.where(MessageType.is_archived == False)  # noqa: E712
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post(
    "/message-types", response_model=MessageTypeResponse, status_code=status.HTTP_201_CREATED
)
async def create_message_type(
    data: MessageTypeCreate,
    current_user: CurrentUser = None,
    db: DbSession = None,
) -> MessageType:
    """Create a new message type."""
    await _check_triage_access(current_user.id, db, current_user.role)
    message_type = MessageType(
        user_id=current_user.id,
        type_name=data.type_name,
        type_definition=data.type_definition,
        source="user",
    )
    db.add(message_type)
    await db.commit()
    await db.refresh(message_type)
    return message_type


@router.put("/message-types/{type_id}", response_model=MessageTypeResponse)
async def update_message_type(
    type_id: UUID,
    data: MessageTypeUpdate,
    current_user: CurrentUser = None,
    db: DbSession = None,
) -> MessageType:
    """Update a message type."""
    await _check_triage_access(current_user.id, db, current_user.role)
    result = await db.execute(
        select(MessageType).where(
            MessageType.id == type_id, MessageType.user_id == current_user.id
        )
    )
    message_type = result.scalars().first()

    if not message_type:
        raise HTTPException(status_code=404, detail="Message type not found")

    if data.type_name is not None:
        message_type.type_name = data.type_name
    if data.type_definition is not None:
        message_type.type_definition = data.type_definition

    await db.commit()
    await db.refresh(message_type)
    return message_type


@router.delete("/message-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_message_type(
    type_id: UUID,
    current_user: CurrentUser = None,
    db: DbSession = None,
) -> None:
    """Archive (soft delete) a message type."""
    await _check_triage_access(current_user.id, db, current_user.role)
    result = await db.execute(
        select(MessageType).where(
            MessageType.id == type_id, MessageType.user_id == current_user.id
        )
    )
    message_type = result.scalars().first()

    if not message_type:
        raise HTTPException(status_code=404, detail="Message type not found")

    message_type.is_archived = True
    await db.commit()


@router.get("/message-types/suggestions", response_model=list[MessageTypeSuggestion])
async def get_message_type_suggestions(
    role: str,
    current_user: CurrentUser = None,
    db: DbSession = None,
) -> list[MessageTypeSuggestion]:
    """Get AI-suggested message types based on user role."""
    import json
    import logging

    from app.core.llm import LLMMessage, get_llm_provider

    logger = logging.getLogger(__name__)

    await _check_triage_access(current_user.id, db, current_user.role)
    llm = get_llm_provider()
    prompt = f"""Given a user with role "{role}", suggest 5 message types that would be useful for triaging Slack messages.

Return JSON array:
[
  {{"type_name": "Incidents", "type_definition": "...", "confidence": 0.9}},
  ...
]

Only return the JSON array, no other text."""

    response = await llm.generate(
        [LLMMessage(role="user", content=prompt)],
        temperature=0.7,
        max_tokens=2048,
    )

    try:
        suggestions = json.loads(response.strip())
        return [MessageTypeSuggestion(**s) for s in suggestions]
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning(f"Failed to parse LLM suggestions: {e}")
        return []


# Channel Type Rules CRUD


@router.get(
    "/channels/{channel_id}/type-rules", response_model=list[ChannelTypeRuleResponse]
)
async def list_channel_type_rules(
    channel_id: str,
    current_user: CurrentUser = None,
    db: DbSession = None,
) -> list[ChannelTypeRule]:
    """List all type rules for a channel."""
    await _check_triage_access(current_user.id, db, current_user.role)
    result = await db.execute(
        select(ChannelTypeRule).where(
            ChannelTypeRule.user_id == current_user.id,
            ChannelTypeRule.channel_id == channel_id,
        )
    )
    rules = list(result.scalars().all())

    for rule in rules:
        await db.refresh(rule, ["message_type"])

    return rules


@router.post(
    "/channels/{channel_id}/type-rules",
    response_model=ChannelTypeRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel_type_rule(
    channel_id: str,
    data: ChannelTypeRuleCreate,
    current_user: CurrentUser = None,
    db: DbSession = None,
) -> ChannelTypeRule:
    """Create a type rule for a channel."""
    await _check_triage_access(current_user.id, db, current_user.role)
    type_result = await db.execute(
        select(MessageType).where(
            MessageType.id == data.message_type_id, MessageType.user_id == current_user.id
        )
    )
    if not type_result.scalars().first():
        raise HTTPException(status_code=404, detail="Message type not found")

    rule = ChannelTypeRule(
        user_id=current_user.id,
        channel_id=channel_id,
        message_type_id=data.message_type_id,
        action=data.action,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule, ["message_type"])
    return rule


@router.delete(
    "/channels/{channel_id}/type-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_channel_type_rule(
    channel_id: str,
    rule_id: UUID,
    current_user: CurrentUser = None,
    db: DbSession = None,
) -> None:
    """Delete a channel type rule."""
    await _check_triage_access(current_user.id, db, current_user.role)
    result = await db.execute(
        select(ChannelTypeRule).where(
            ChannelTypeRule.id == rule_id,
            ChannelTypeRule.user_id == current_user.id,
            ChannelTypeRule.channel_id == channel_id,
        )
    )
    rule = result.scalars().first()

    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    await db.delete(rule)
    await db.commit()

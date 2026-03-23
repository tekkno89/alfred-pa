"""Triage system API endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Query, status
from slack_sdk.errors import SlackApiError

from app.api.deps import CurrentUser, DbSession
from app.db.models.triage import (
    ChannelKeywordRule,
    ChannelSourceExclusion,
    MonitoredChannel,
)
from app.db.repositories import FeatureAccessRepository
from app.db.repositories.triage import (
    ChannelKeywordRuleRepository,
    ChannelSourceExclusionRepository,
    MonitoredChannelRepository,
    SlackChannelCacheRepository,
    TriageClassificationRepository,
    TriageFeedbackRepository,
    TriageUserSettingsRepository,
)
from app.schemas.triage import (
    ClassificationList,
    ClassificationResponse,
    DigestResponse,
    KeywordRuleCreate,
    KeywordRuleResponse,
    KeywordRuleUpdate,
    MarkReviewedRequest,
    MonitoredChannelCreate,
    MonitoredChannelList,
    MonitoredChannelResponse,
    MonitoredChannelUpdate,
    SlackChannelInfo,
    SourceExclusionCreate,
    SourceExclusionResponse,
    TriageFeedbackCreate,
    TriageSettingsResponse,
    TriageSettingsUpdate,
)
from app.services.triage_cache import TriageCacheService

logger = logging.getLogger(__name__)

router = APIRouter()


async def _check_triage_access(user_id: str, db, role: str) -> None:
    """Check if user has triage feature access."""
    repo = FeatureAccessRepository(db)
    if role != "admin" and not await repo.is_enabled(user_id, "card:triage"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Triage feature not enabled",
        )


# --- Settings ---


@router.get("/settings", response_model=TriageSettingsResponse)
async def get_triage_settings(
    current_user: CurrentUser,
    db: DbSession,
) -> TriageSettingsResponse:
    """Get triage settings for the current user."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = TriageUserSettingsRepository(db)
    settings = await repo.get_or_create(current_user.id)
    return TriageSettingsResponse.model_validate(settings)


@router.patch("/settings", response_model=TriageSettingsResponse)
async def update_triage_settings(
    data: TriageSettingsUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> TriageSettingsResponse:
    """Update triage settings."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = TriageUserSettingsRepository(db)
    settings = await repo.get_or_create(current_user.id)
    updates = data.model_dump(exclude_unset=True)
    if updates:
        settings = await repo.update(settings, **updates)
    return TriageSettingsResponse.model_validate(settings)


# --- Monitored Channels ---


@router.get("/channels", response_model=MonitoredChannelList)
async def list_monitored_channels(
    current_user: CurrentUser,
    db: DbSession,
) -> MonitoredChannelList:
    """List all monitored channels for the current user."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = MonitoredChannelRepository(db)
    channels = await repo.get_by_user(current_user.id, active_only=False)
    return MonitoredChannelList(
        channels=[MonitoredChannelResponse.model_validate(c) for c in channels]
    )


@router.post(
    "/channels",
    response_model=MonitoredChannelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_monitored_channel(
    data: MonitoredChannelCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> MonitoredChannelResponse:
    """Add a channel to monitor."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = MonitoredChannelRepository(db)

    existing = await repo.get_by_user_and_channel(
        current_user.id, data.slack_channel_id
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Channel is already monitored",
        )

    channel = MonitoredChannel(
        user_id=current_user.id,
        slack_channel_id=data.slack_channel_id,
        channel_name=data.channel_name,
        channel_type=data.channel_type,
        priority=data.priority,
    )
    channel = await repo.create(channel)

    # Update Redis set
    cache = TriageCacheService()
    await cache.add_channel(data.slack_channel_id)

    return MonitoredChannelResponse.model_validate(channel)


@router.patch("/channels/{channel_id}", response_model=MonitoredChannelResponse)
async def update_monitored_channel(
    channel_id: str,
    data: MonitoredChannelUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> MonitoredChannelResponse:
    """Update a monitored channel."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = MonitoredChannelRepository(db)
    channel = await repo.get(channel_id)
    if not channel or channel.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )
    updates = data.model_dump(exclude_unset=True)
    if updates:
        channel = await repo.update(channel, **updates)
    return MonitoredChannelResponse.model_validate(channel)


@router.delete(
    "/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_monitored_channel(
    channel_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Remove a monitored channel."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = MonitoredChannelRepository(db)
    channel = await repo.get(channel_id)
    if not channel or channel.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )
    slack_channel_id = channel.slack_channel_id
    await repo.delete(channel)

    # Check if any other user monitors this channel
    remaining = await repo.get_users_for_channel(slack_channel_id)
    if not remaining:
        cache = TriageCacheService()
        await cache.remove_channel(slack_channel_id)


# --- Keyword Rules ---


@router.get(
    "/channels/{channel_id}/rules", response_model=list[KeywordRuleResponse]
)
async def list_keyword_rules(
    channel_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> list[KeywordRuleResponse]:
    """List keyword rules for a monitored channel."""
    await _check_triage_access(current_user.id, db, current_user.role)
    # Verify channel ownership
    ch_repo = MonitoredChannelRepository(db)
    channel = await ch_repo.get(channel_id)
    if not channel or channel.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )
    repo = ChannelKeywordRuleRepository(db)
    rules = await repo.get_by_channel(channel_id, current_user.id)
    return [KeywordRuleResponse.model_validate(r) for r in rules]


@router.post(
    "/channels/{channel_id}/rules",
    response_model=KeywordRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_keyword_rule(
    channel_id: str,
    data: KeywordRuleCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> KeywordRuleResponse:
    """Add a keyword rule to a monitored channel."""
    await _check_triage_access(current_user.id, db, current_user.role)
    ch_repo = MonitoredChannelRepository(db)
    channel = await ch_repo.get(channel_id)
    if not channel or channel.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )
    repo = ChannelKeywordRuleRepository(db)
    rule = ChannelKeywordRule(
        monitored_channel_id=channel_id,
        user_id=current_user.id,
        keyword_pattern=data.keyword_pattern,
        match_type=data.match_type,
        urgency_override=data.urgency_override,
    )
    rule = await repo.create(rule)
    return KeywordRuleResponse.model_validate(rule)


@router.patch(
    "/channels/{channel_id}/rules/{rule_id}",
    response_model=KeywordRuleResponse,
)
async def update_keyword_rule(
    channel_id: str,
    rule_id: str,
    data: KeywordRuleUpdate,
    current_user: CurrentUser,
    db: DbSession,
) -> KeywordRuleResponse:
    """Update a keyword rule."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = ChannelKeywordRuleRepository(db)
    rule = await repo.get(rule_id)
    if (
        not rule
        or rule.user_id != current_user.id
        or rule.monitored_channel_id != channel_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )
    updates = data.model_dump(exclude_unset=True)
    if updates:
        rule = await repo.update(rule, **updates)
    return KeywordRuleResponse.model_validate(rule)


@router.delete(
    "/channels/{channel_id}/rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_keyword_rule(
    channel_id: str,
    rule_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Remove a keyword rule."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = ChannelKeywordRuleRepository(db)
    rule = await repo.get(rule_id)
    if (
        not rule
        or rule.user_id != current_user.id
        or rule.monitored_channel_id != channel_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found",
        )
    await repo.delete(rule)


# --- Source Exclusions ---


@router.get(
    "/channels/{channel_id}/exclusions",
    response_model=list[SourceExclusionResponse],
)
async def list_source_exclusions(
    channel_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> list[SourceExclusionResponse]:
    """List source exclusions for a monitored channel."""
    await _check_triage_access(current_user.id, db, current_user.role)
    ch_repo = MonitoredChannelRepository(db)
    channel = await ch_repo.get(channel_id)
    if not channel or channel.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )
    repo = ChannelSourceExclusionRepository(db)
    exclusions = await repo.get_by_channel(channel_id, current_user.id)
    return [SourceExclusionResponse.model_validate(e) for e in exclusions]


@router.post(
    "/channels/{channel_id}/exclusions",
    response_model=SourceExclusionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_source_exclusion(
    channel_id: str,
    data: SourceExclusionCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> SourceExclusionResponse:
    """Add a source exclusion to a monitored channel."""
    await _check_triage_access(current_user.id, db, current_user.role)
    ch_repo = MonitoredChannelRepository(db)
    channel = await ch_repo.get(channel_id)
    if not channel or channel.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )
    repo = ChannelSourceExclusionRepository(db)
    exclusion = ChannelSourceExclusion(
        monitored_channel_id=channel_id,
        user_id=current_user.id,
        slack_entity_id=data.slack_entity_id,
        entity_type=data.entity_type,
        action=data.action,
        display_name=data.display_name,
    )
    exclusion = await repo.create(exclusion)
    return SourceExclusionResponse.model_validate(exclusion)


@router.delete(
    "/channels/{channel_id}/exclusions/{exclusion_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_source_exclusion(
    channel_id: str,
    exclusion_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    """Remove a source exclusion."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = ChannelSourceExclusionRepository(db)
    exclusion = await repo.get(exclusion_id)
    if (
        not exclusion
        or exclusion.user_id != current_user.id
        or exclusion.monitored_channel_id != channel_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exclusion not found",
        )
    await repo.delete(exclusion)


# --- Available Slack Channels ---


@router.get("/slack-channels", response_model=list[SlackChannelInfo])
async def list_available_slack_channels(
    current_user: CurrentUser,
    db: DbSession,
    search: str = Query("", description="Filter channels by name"),
) -> list[SlackChannelInfo]:
    """List available Slack channels.

    Public channels come from the persistent DB cache.
    Private channels are fetched per-user via their Slack token so users
    only see private channels they belong to.
    """
    await _check_triage_access(current_user.id, db, current_user.role)

    cache_repo = SlackChannelCacheRepository(db)

    # If cache is empty (first deploy), populate synchronously from Slack
    if await cache_repo.count() == 0:
        try:
            from app.services.slack import fetch_all_slack_channels

            raw_channels = await fetch_all_slack_channels()  # bot token
            await cache_repo.upsert_batch(raw_channels)
            await db.commit()
        except SlackApiError as e:
            logger.error(f"Error listing Slack channels: {e.response['error']}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Failed to list Slack channels",
            ) from e

    search_term = search.strip() or None

    # 1. Public channels from DB cache
    rows = await cache_repo.get_all(search=search_term)
    results: list[SlackChannelInfo] = [
        SlackChannelInfo(
            id=r.slack_channel_id,
            name=r.name,
            is_private=r.is_private,
            num_members=r.num_members,
        )
        for r in rows
    ]

    # 2. Private channels fetched per-user via their Slack token
    try:
        from app.services.slack_user import SlackUserService

        user_svc = SlackUserService(db)
        user_token = await user_svc.get_raw_token(current_user.id)
        if user_token:
            from app.services.slack import _paginate_conversations
            from slack_sdk.web.async_client import AsyncWebClient

            client = AsyncWebClient(token=user_token)
            try:
                private_channels = await _paginate_conversations(
                    client, "private_channel", max_retries=3
                )
            except SlackApiError:
                private_channels = []

            seen_ids = {r.id for r in results}
            for ch in private_channels:
                if ch["id"] in seen_ids:
                    continue
                name = ch.get("name", "")
                if search_term and search_term.lower() not in name.lower():
                    continue
                results.append(
                    SlackChannelInfo(
                        id=ch["id"],
                        name=name,
                        is_private=True,
                        num_members=ch.get("num_members", 0),
                    )
                )
    except Exception:
        logger.exception("Failed to fetch user's private channels")

    results.sort(key=lambda c: c.name.lower())
    return results


@router.post(
    "/slack-channels/refresh",
    status_code=status.HTTP_202_ACCEPTED,
)
async def refresh_slack_channels(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Enqueue a background refresh of the Slack channel cache."""
    await _check_triage_access(current_user.id, db, current_user.role)

    from app.core.redis import get_redis

    redis_client = await get_redis()
    from arq.connections import ArqRedis

    pool = ArqRedis(redis_client.connection_pool)
    import uuid as _uuid

    await pool.enqueue_job(
        "refresh_slack_channel_cache",
        current_user.id,
        _job_id=f"refresh_slack_channel_cache:{_uuid.uuid4().hex[:8]}",
    )
    return {"status": "queued"}


# --- Classifications ---


@router.get("/classifications", response_model=ClassificationList)
async def list_classifications(
    current_user: CurrentUser,
    db: DbSession,
    urgency: str | None = Query(None, pattern="^(urgent|digest|noise|review|digest_summary|reviewable|needs_attention)$"),
    channel_id: str | None = Query(None),
    reviewed: bool | None = Query(None),
    hide_active_digest: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ClassificationList:
    """List recent classifications."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = TriageClassificationRepository(db)

    # Translate "reviewable"/"needs_attention" pseudo-filter into a list of urgency levels
    urgency_filter: str | list[str] | None = urgency
    if urgency in ("reviewable", "needs_attention"):
        urgency_filter = ["urgent", "review", "digest_summary"]

    items = await repo.get_recent(
        current_user.id,
        limit=limit,
        offset=offset,
        urgency_level=urgency_filter,
        channel_id=channel_id,
        reviewed=reviewed,
        exclude_active_session_digest=hide_active_digest,
    )
    total = await repo.count_filtered(
        current_user.id,
        urgency_level=urgency_filter,
        channel_id=channel_id,
        reviewed=reviewed,
        exclude_active_session_digest=hide_active_digest,
    )
    return ClassificationList(
        items=[ClassificationResponse.model_validate(i) for i in items],
        total=total,
    )


@router.patch("/classifications/reviewed")
async def mark_classifications_reviewed(
    data: MarkReviewedRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Bulk mark classifications as reviewed or unreviewed."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = TriageClassificationRepository(db)
    if data.reviewed:
        count = await repo.mark_reviewed(data.classification_ids, current_user.id)
    else:
        count = await repo.mark_unreviewed(data.classification_ids, current_user.id)
    # Commit before returning so the refetch triggered by onSuccess sees the update
    await db.commit()
    return {"updated": count}


@router.get(
    "/classifications/{classification_id}/digest-children",
    response_model=list[ClassificationResponse],
)
async def get_digest_children(
    classification_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> list[ClassificationResponse]:
    """Get individual items consolidated into a digest summary."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = TriageClassificationRepository(db)
    classification = await repo.get(classification_id)
    if not classification or classification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Classification not found",
        )
    if classification.urgency_level != "digest_summary":
        return []
    children = await repo.get_digest_children(
        classification_id, current_user.id
    )
    return [ClassificationResponse.model_validate(c) for c in children]


@router.get("/digest/{session_id}", response_model=DigestResponse)
async def get_session_digest(
    session_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> DigestResponse:
    """Get a structured digest for a focus session."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = TriageClassificationRepository(db)
    items = await repo.get_by_session(current_user.id, session_id)
    return DigestResponse(
        session_id=session_id,
        urgent_count=sum(1 for i in items if i.urgency_level == "urgent"),
        review_count=sum(1 for i in items if i.urgency_level == "review"),
        noise_count=sum(1 for i in items if i.urgency_level == "noise"),
        digest_count=sum(
            1 for i in items if i.urgency_level in ("digest", "digest_summary")
        ),
        items=[ClassificationResponse.model_validate(i) for i in items],
    )


@router.get("/digest/latest", response_model=DigestResponse)
async def get_latest_digest(
    current_user: CurrentUser,
    db: DbSession,
) -> DigestResponse:
    """Get the most recent digest (last 50 classifications)."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = TriageClassificationRepository(db)
    items = await repo.get_recent(current_user.id, limit=50)
    return DigestResponse(
        urgent_count=sum(1 for i in items if i.urgency_level == "urgent"),
        review_count=sum(1 for i in items if i.urgency_level == "review"),
        noise_count=sum(1 for i in items if i.urgency_level == "noise"),
        digest_count=sum(
            1 for i in items if i.urgency_level in ("digest", "digest_summary")
        ),
        items=[ClassificationResponse.model_validate(i) for i in items],
    )


# --- Feedback ---


@router.post(
    "/analytics/feedback",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
)
async def submit_feedback(
    data: TriageFeedbackCreate,
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Submit feedback on a classification."""
    await _check_triage_access(current_user.id, db, current_user.role)
    # Verify classification exists and belongs to user
    class_repo = TriageClassificationRepository(db)
    classification = await class_repo.get(data.classification_id)
    if not classification or classification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Classification not found",
        )
    feedback_repo = TriageFeedbackRepository(db)
    await feedback_repo.create_feedback(
        classification_id=data.classification_id,
        user_id=current_user.id,
        was_correct=data.was_correct,
        correct_urgency=data.correct_urgency,
    )
    return {"status": "ok"}


# --- Analytics ---


@router.get("/analytics/session-stats")
async def get_session_stats(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Get classification stats for the current user."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = TriageClassificationRepository(db)
    urgent = await repo.count_filtered(
        current_user.id, urgency_level="urgent", reviewed=False,
    )
    review = await repo.count_filtered(
        current_user.id, urgency_level="review", reviewed=False,
    )
    noise = await repo.count_filtered(
        current_user.id, urgency_level="noise", reviewed=False,
    )
    digest = await repo.count_filtered(
        current_user.id, urgency_level="digest", reviewed=False,
    )
    digest_summary = await repo.count_filtered(
        current_user.id, urgency_level="digest_summary", reviewed=False,
    )
    return {
        "urgent": urgent,
        "review": review,
        "noise": noise,
        "digest": digest,
        "digest_summary": digest_summary,
        "total": urgent + review + noise + digest + digest_summary,
    }

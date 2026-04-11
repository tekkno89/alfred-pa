"""Triage system API endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Query, status
from slack_sdk.errors import SlackApiError

from app.api.deps import CurrentUser, DbSession
from app.db.models.triage import (
    ChannelSourceExclusion,
    MonitoredChannel,
)
from app.db.repositories import FeatureAccessRepository
from app.db.repositories.triage import (
    ChannelSourceExclusionRepository,
    MonitoredChannelRepository,
    TriageClassificationRepository,
    TriageFeedbackRepository,
    TriageUserSettingsRepository,
)
from app.schemas.triage import (
    ChannelMemberInfo,
    ClassificationList,
    ClassificationResponse,
    DigestResponse,
    GenerateDefinitionsRequest,
    GenerateDefinitionsResponse,
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


@router.post("/channels/auto-enroll")
async def auto_enroll_channels(
    current_user: CurrentUser,
    db: DbSession,
) -> dict:
    """Manually sync all user's Slack channels to monitored channels.

    Adds channels the user is a member of but not yet monitoring.
    Removes channels the user is no longer a member of.
    Sets default priority: private=high, public=medium.
    """
    await _check_triage_access(current_user.id, db, current_user.role)

    # Fetch channels user belongs to using their OAuth token
    from app.services.slack import fetch_user_channels
    from app.services.slack_user import SlackUserService

    user_svc = SlackUserService(db)
    user_token = await user_svc.get_raw_token(current_user.id)

    if not user_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No Slack token found. Please connect your Slack account.",
        )

    try:
        slack_channels = await fetch_user_channels(user_token)
    except SlackApiError as e:
        logger.error(f"Error fetching user channels: {e.response['error']}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to fetch channels from Slack",
        ) from e

    # Get current Slack channel IDs the user is a member of
    slack_channel_ids = {ch["id"] for ch in slack_channels}

    # Get existing monitored channels
    ch_repo = MonitoredChannelRepository(db)
    existing = await ch_repo.get_by_user(current_user.id, active_only=False)
    existing_ids = {c.slack_channel_id for c in existing}

    # Create new monitored channels for channels the user joined
    new_channels = []
    for ch in slack_channels:
        ch_id = ch["id"]
        if ch_id not in existing_ids:
            mc = MonitoredChannel(
                user_id=current_user.id,
                slack_channel_id=ch_id,
                channel_name=ch.get("name", ch_id),
                channel_type="private" if ch.get("is_private") else "public",
                priority="high" if ch.get("is_private") else "medium",
            )
            new_channels.append(mc)

    # Remove monitored channels for channels the user left
    removed_channels = []
    cache = TriageCacheService()
    for monitored_channel in existing:
        if monitored_channel.slack_channel_id not in slack_channel_ids:
            removed_channels.append(monitored_channel)
            await ch_repo.delete(monitored_channel)

            # Check if any other user monitors this channel
            remaining = await ch_repo.get_users_for_channel(
                monitored_channel.slack_channel_id
            )
            if not remaining:
                await cache.remove_channel(monitored_channel.slack_channel_id)

    # Bulk create new channels
    if new_channels:
        db.add_all(new_channels)

    if new_channels or removed_channels:
        await db.commit()

        # Update Redis set for new channels
        for mc in new_channels:
            await cache.add_channel(mc.slack_channel_id)

    return {
        "enrolled_count": len(new_channels),
        "removed_count": len(removed_channels),
        "total_monitored": len(existing) - len(removed_channels) + len(new_channels),
    }


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
    """List available Slack channels the user is a member of.

    Fetches all channels (public and private) that the user belongs to
    via their Slack OAuth token.
    """
    await _check_triage_access(current_user.id, db, current_user.role)

    from app.services.slack import fetch_user_channels
    from app.services.slack_user import SlackUserService

    user_svc = SlackUserService(db)
    user_token = await user_svc.get_raw_token(current_user.id)

    if not user_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No Slack token found. Please connect your Slack account.",
        )

    try:
        # Fetch channels user belongs to (public and private)
        slack_channels = await fetch_user_channels(user_token)
    except SlackApiError as e:
        logger.error(f"Error listing Slack channels: {e.response['error']}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to list Slack channels",
        ) from e

    search_term = search.strip().lower() if search.strip() else None

    results: list[SlackChannelInfo] = []
    for ch in slack_channels:
        name = ch.get("name", "")
        # Filter by search term if provided
        if search_term and search_term not in name.lower():
            continue
        results.append(
            SlackChannelInfo(
                id=ch["id"],
                name=name,
                is_private=ch.get("is_private", False),
                num_members=ch.get("num_members", 0),
            )
        )

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


@router.get(
    "/channels/{channel_id}/members",
    response_model=list[ChannelMemberInfo],
)
async def get_channel_members(
    channel_id: str,
    current_user: CurrentUser,
    db: DbSession,
) -> list[ChannelMemberInfo]:
    """Fetch members of a Slack channel (users, bots, apps).

    Used for populating exclusion multiselect dropdown.
    Results are cached in Redis for 1 hour.
    """
    await _check_triage_access(current_user.id, db, current_user.role)

    # Verify user has access to this channel
    ch_repo = MonitoredChannelRepository(db)
    channel = await ch_repo.get_by_user_and_channel(current_user.id, channel_id)
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found in your monitored channels",
        )

    # Check Redis cache first
    from app.core.redis import get_redis

    redis_client = await get_redis()
    cache_key = f"triage:channel_members:{channel_id}"
    cached = await redis_client.get(cache_key)

    if cached:
        import json
        members_data = json.loads(cached)
        return [ChannelMemberInfo(**m) for m in members_data]

    # Fetch from Slack API
    try:
        from app.services.slack import SlackService
        from app.services.slack_user import SlackUserService

        slack_service = SlackService()
        user_svc = SlackUserService(db)
        user_token = await user_svc.get_raw_token(current_user.id)

        if not user_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No Slack user token available",
            )

        from slack_sdk.web.async_client import AsyncWebClient

        client = AsyncWebClient(token=user_token)
        members = []
        cursor = None

        # Paginate through all members
        while True:
            resp = await client.conversations_members(
                channel=channel_id,
                limit=100,
                cursor=cursor,
            )

            if not resp["ok"]:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to fetch channel members: {resp.get('error', 'Unknown error')}",
                )

            member_ids = resp.get("members", [])

            # Fetch user info for each member
            for user_id in member_ids:
                try:
                    user_info = await slack_service.get_user_info(user_id)
                    is_bot = user_info.get("is_bot", False)
                    is_app = user_info.get("is_app", False)

                    # Get display name
                    profile = user_info.get("profile", {})
                    display_name = (
                        profile.get("display_name")
                        or profile.get("real_name")
                        or user_info.get("real_name")
                        or user_info.get("name")
                        or user_id
                    )

                    members.append(
                        ChannelMemberInfo(
                            slack_user_id=user_id,
                            display_name=display_name,
                            is_bot=is_bot,
                            is_app=is_app,
                        )
                    )
                except SlackApiError:
                    # Skip users we can't fetch info for
                    continue

            # Check for next page
            cursor = resp.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        # Sort by name
        members.sort(key=lambda m: m.display_name.lower())

        # Cache for 1 hour
        import json
        await redis_client.set(
            cache_key,
            json.dumps([m.model_dump() for m in members]),
            ex=3600,
        )

        return members

    except SlackApiError as e:
        logger.error(f"Failed to fetch channel members: {e.response['error']}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch channel members: {e.response['error']}",
        )


# --- Classifications ---


@router.get("/classifications", response_model=ClassificationList)
async def list_classifications(
    current_user: CurrentUser,
    db: DbSession,
    priority: str | None = Query(None, pattern="^(p0|p1|p2|p3|review|digest_summary|needs_attention)$"),
    channel_id: str | None = Query(None),
    reviewed: bool | None = Query(None),
    hide_active_digest: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ClassificationList:
    """List recent classifications."""
    await _check_triage_access(current_user.id, db, current_user.role)
    repo = TriageClassificationRepository(db)

    # Translate "needs_attention" pseudo-filter into a list of priority levels
    priority_filter: str | list[str] | None = priority
    if priority == "needs_attention":
        priority_filter = ["p0", "review", "digest_summary"]

    items = await repo.get_recent(
        current_user.id,
        limit=limit,
        offset=offset,
        priority_level=priority_filter,
        channel_id=channel_id,
        reviewed=reviewed,
        exclude_active_session_digest=hide_active_digest,
    )
    total = await repo.count_filtered(
        current_user.id,
        priority_level=priority_filter,
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
    if classification.priority_level != "digest_summary":
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
        p0_count=sum(1 for i in items if i.priority_level == "p0"),
        p1_count=sum(1 for i in items if i.priority_level == "p1"),
        p2_count=sum(1 for i in items if i.priority_level == "p2"),
        p3_count=sum(1 for i in items if i.priority_level == "p3"),
        review_count=sum(1 for i in items if i.priority_level == "review"),
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
        p0_count=sum(1 for i in items if i.priority_level == "p0"),
        p1_count=sum(1 for i in items if i.priority_level == "p1"),
        p2_count=sum(1 for i in items if i.priority_level == "p2"),
        p3_count=sum(1 for i in items if i.priority_level == "p3"),
        review_count=sum(1 for i in items if i.priority_level == "review"),
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
        correct_priority=data.correct_priority,
        feedback_text=data.feedback_text,
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
    p0 = await repo.count_filtered(
        current_user.id, priority_level="p0", reviewed=False,
    )
    p1 = await repo.count_filtered(
        current_user.id, priority_level="p1", reviewed=False,
    )
    p2 = await repo.count_filtered(
        current_user.id, priority_level="p2", reviewed=False,
    )
    p3 = await repo.count_filtered(
        current_user.id, priority_level="p3", reviewed=False,
    )
    review = await repo.count_filtered(
        current_user.id, priority_level="review", reviewed=False,
    )
    digest_summary = await repo.count_filtered(
        current_user.id, priority_level="digest_summary", reviewed=False,
    )
    return {
        "p0": p0,
        "p1": p1,
        "p2": p2,
        "p3": p3,
        "review": review,
        "digest_summary": digest_summary,
        "total": p0 + p1 + p2 + p3 + review + digest_summary,
    }


# --- AI Wizard ---


@router.post("/settings/detect-workspace", response_model=TriageSettingsResponse)
async def detect_workspace(
    current_user: CurrentUser,
    db: DbSession,
) -> TriageSettingsResponse:
    """Detect Slack workspace domain via team.info API and save it."""
    await _check_triage_access(current_user.id, db, current_user.role)

    from app.services.slack import SlackService

    try:
        slack_service = SlackService()
        team_info = await slack_service.client.team_info()
    except SlackApiError as e:
        logger.error(f"Slack API error detecting workspace: {e.response['error']}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to contact Slack API",
        ) from e
    except Exception as e:
        logger.error(f"Error detecting workspace: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to contact Slack API",
        ) from e

    domain = None
    if team_info.get("ok"):
        domain = team_info["team"].get("domain")

    if not domain:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not determine workspace domain from Slack",
        )

    repo = TriageUserSettingsRepository(db)
    settings = await repo.get_or_create(current_user.id)
    settings = await repo.update(settings, slack_workspace_domain=domain)
    return TriageSettingsResponse.model_validate(settings)


@router.post(
    "/settings/generate-definitions",
    response_model=GenerateDefinitionsResponse,
)
async def generate_definitions(
    data: GenerateDefinitionsRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> GenerateDefinitionsResponse:
    """Generate priority definitions using AI based on user answers."""
    await _check_triage_access(current_user.id, db, current_user.role)
    from app.services.triage_wizard import TriageWizardService

    wizard = TriageWizardService()
    result = await wizard.generate_definitions(
        role=data.role,
        critical_messages=data.critical_messages,
        can_wait=data.can_wait,
        priority_senders=data.priority_senders,
    )
    return GenerateDefinitionsResponse(**result)

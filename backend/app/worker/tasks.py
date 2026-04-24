"""Background tasks for the ARQ worker."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from app.db.repositories import FocusModeStateRepository
from app.db.session import async_session_maker

logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_db_session():
    """Get a database session with proper commit/rollback handling."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def expire_focus_session(ctx: dict, user_id: str | None = None) -> dict:
    """
    Expire focus sessions that have passed their end time.

    Can be called with a specific user_id (scheduled job) or without
    to check all users (cron job).
    """
    async with get_db_session() as db:
        state_repo = FocusModeStateRepository(db)

        if user_id:
            # Specific user - scheduled expiration
            logger.info(f"Checking focus expiration for user {user_id}")
            state = await state_repo.get_by_user_id(user_id)

            if not state or not state.is_active:
                logger.info(f"User {user_id} focus session already inactive")
                return {"status": "already_inactive", "user_id": user_id}

            # Skip pomodoro sessions - they should be handled by transition jobs
            if state.mode == "pomodoro":
                logger.info(f"Skipping pomodoro session expiration for user {user_id}")
                return {"status": "skipped_pomodoro", "user_id": user_id}

            if state.ends_at and state.ends_at <= datetime.utcnow():
                from app.services.focus_orchestrator import FocusModeOrchestrator

                orchestrator = FocusModeOrchestrator(db)
                await orchestrator.disable(user_id)
                await db.commit()
                logger.info(f"Expired focus session for user {user_id}")
                return {"status": "expired", "user_id": user_id}
            else:
                logger.info(f"User {user_id} focus session not yet expired")
                return {"status": "not_expired", "user_id": user_id}
        else:
            # Cron job - check all active sessions
            logger.info("Running focus expiration cron job")
            now = datetime.utcnow()
            expired_states = await state_repo.get_active_expired(now)

            expired_count = 0
            for state in expired_states:
                # Skip pomodoro sessions - they should be handled by transition jobs
                if state.mode == "pomodoro":
                    logger.info(f"Skipping pomodoro session for user {state.user_id}")
                    continue
                try:
                    from app.services.focus_orchestrator import FocusModeOrchestrator

                    orchestrator = FocusModeOrchestrator(db)
                    await orchestrator.disable(state.user_id)
                    expired_count += 1
                except Exception as e:
                    logger.error(f"Error expiring session for {state.user_id}: {e}")

            await db.commit()
            logger.info(f"Expired {expired_count} focus sessions")
            return {"status": "cron_complete", "expired_count": expired_count}


async def send_todo_reminder(ctx: dict, todo_id: str, user_id: str) -> dict:
    """
    Send notifications for a todo that has reached its due time.

    Dispatches to all configured channels (Slack, SSE, webhooks) via
    TodoNotificationService.
    """
    # Acquire a Redis lock to prevent duplicate notifications
    # (race between scheduled job and cron backup job)
    from app.core.redis import get_redis

    redis_client = await get_redis()
    lock_key = f"todo_reminder_lock:{todo_id}"
    acquired = await redis_client.set(lock_key, "1", nx=True, ex=300)  # 5-min TTL
    if not acquired:
        logger.info(f"Todo {todo_id} reminder already in progress, skipping (dedup)")
        return {"status": "skipped", "reason": "dedup_lock"}

    async with get_db_session() as db:
        from app.services.todo_notifications import TodoNotificationService

        service = TodoNotificationService(db)
        result = await service.send_due_reminder(todo_id, user_id)
        await db.commit()
        logger.info(f"Todo reminder result for {todo_id}: {result.get('status')}")
        return result


async def check_due_todo_reminders(ctx: dict) -> dict:
    """
    Cron backup: find todos past due with no reminder sent and send reminders.
    """
    async with get_db_session() as db:
        from app.db.repositories.todo import TodoRepository

        todo_repo = TodoRepository(db)
        now = datetime.utcnow()
        due_todos = await todo_repo.get_due_reminders(now)

        sent_count = 0
        for todo in due_todos:
            try:
                result = await send_todo_reminder(ctx, todo.id, todo.user_id)
                if result.get("status") == "sent":
                    sent_count += 1
            except Exception as e:
                logger.error(f"Error sending reminder for todo {todo.id}: {e}")

        logger.info(f"Cron: sent {sent_count} todo reminders")
        return {"status": "cron_complete", "sent_count": sent_count}


async def process_triage_job(
    ctx: dict,
    user_id: str,
    event_type: str,
    channel_id: str,
    sender_slack_id: str,
    message_ts: str,
    thread_ts: str | None = None,
    message_text: str = "",
) -> dict:
    """
    Process a message through the triage pipeline.

    message_text is used in-memory only and never persisted.
    """
    async with get_db_session() as db:
        from app.services.triage_pipeline import TriagePipeline

        pipeline = TriagePipeline(db)
        await pipeline.process(
            user_id=user_id,
            event_type=event_type,
            channel_id=channel_id,
            sender_slack_id=sender_slack_id,
            message_ts=message_ts,
            thread_ts=thread_ts,
            message_text=message_text,
        )
        logger.info(f"Triage pipeline complete for user={user_id} channel={channel_id}")
        return {"status": "processed", "user_id": user_id}


async def cleanup_expired_classifications(ctx: dict) -> dict:
    """
    Cron job: delete triage classifications older than the user's retention period.
    Runs daily at 3 AM.
    """
    async with get_db_session() as db:
        from app.db.repositories.triage import TriageClassificationRepository

        class_repo = TriageClassificationRepository(db)

        # Get all users with triage settings
        from sqlalchemy import select

        from app.db.models.triage import TriageUserSettings

        result = await db.execute(select(TriageUserSettings))
        all_settings = list(result.scalars().all())

        deleted_total = 0
        for settings in all_settings:
            try:
                deleted = await class_repo.delete_expired(
                    settings.user_id, settings.classification_retention_days
                )
                deleted_total += deleted
            except Exception as e:
                logger.error(
                    f"Error cleaning up classifications for user {settings.user_id}: {e}"
                )

        await db.commit()
        logger.info(f"Cleaned up {deleted_total} expired triage classifications")
        return {"status": "complete", "deleted_count": deleted_total}


async def refresh_slack_channel_cache(ctx: dict, user_id: str | None = None) -> dict:
    """Refresh the persistent Slack channel cache from the Slack API.

    Only public channels are stored in the global cache.  Private channels
    are fetched per-user at query time for security.
    """
    from app.db.repositories.triage import SlackChannelCacheRepository
    from app.services.slack import fetch_all_slack_channels

    logger.info("Refreshing Slack channel cache (public channels only)")
    try:
        raw_channels = await fetch_all_slack_channels()  # bot token
    except Exception:
        logger.exception("Failed to fetch Slack channels for cache refresh")
        # Publish SSE so the frontend knows the refresh failed
        if user_id:
            try:
                from app.services.notifications import NotificationService

                await NotificationService.publish_to_sse(
                    user_id, "slack_channels.refreshed", {"status": "error"}
                )
            except Exception:
                pass
        return {"status": "error"}

    async with get_db_session() as db:
        repo = SlackChannelCacheRepository(db)
        count = await repo.upsert_batch(raw_channels)

    logger.info(f"Slack channel cache refreshed: {count} public channels")

    # Notify the frontend that the refresh is complete
    if user_id:
        try:
            from app.services.notifications import NotificationService

            await NotificationService.publish_to_sse(
                user_id, "slack_channels.refreshed", {"status": "ok", "count": count}
            )
        except Exception:
            logger.debug("Failed to publish SSE for channel refresh completion")

    return {"status": "ok", "count": count}


async def auto_enroll_user_channels(ctx: dict) -> dict:
    """
    Cron job: auto-enroll user's Slack channels to monitored channels.

    Runs every 5 minutes to:
    - Add new channels user has joined
    - Remove channels user has left
    - Set default priority (private=high, public=medium)
    """
    from app.db.models.triage import MonitoredChannel, TriageUserSettings
    from app.db.repositories.triage import MonitoredChannelRepository
    from app.services.slack_user import SlackUserService
    from app.services.triage_cache import TriageCacheService
    from sqlalchemy import select

    async with get_db_session() as db:
        # Get all users with triage enabled
        result = await db.execute(
            select(TriageUserSettings.user_id).where(
                TriageUserSettings.is_always_on == True
            )
        )
        user_ids = list(result.scalars().all())

    enrolled_total = 0
    removed_total = 0

    for user_id in user_ids:
        try:
            async with get_db_session() as db:
                # Get user's Slack token
                user_svc = SlackUserService(db)
                user_token = await user_svc.get_raw_token(user_id)

                if not user_token:
                    continue

                # Fetch user's channels (public + private)
                from app.services.slack import _paginate_conversations
                from slack_sdk.web.async_client import AsyncWebClient

                client = AsyncWebClient(token=user_token)

                # Public channels
                public_channels = await _paginate_conversations(
                    client, "public_channel", max_retries=3
                )

                # Private channels
                private_channels = await _paginate_conversations(
                    client, "private_channel", max_retries=3
                )

                all_channel_ids = {
                    ch["id"] for ch in public_channels + private_channels
                }

                # Get existing monitored channels
                ch_repo = MonitoredChannelRepository(db)
                existing = await ch_repo.get_by_user(user_id, active_only=False)
                existing_ids = {c.slack_channel_id: c for c in existing}

                # Remove channels user no longer belongs to
                for mc in existing:
                    if mc.slack_channel_id not in all_channel_ids:
                        await db.delete(mc)
                        removed_total += 1

                # Add new channels
                for ch in public_channels:
                    ch_id = ch["id"]
                    if ch_id not in existing_ids:
                        mc = MonitoredChannel(
                            user_id=user_id,
                            slack_channel_id=ch_id,
                            channel_name=ch.get("name", ch_id),
                            channel_type="public",
                            priority="medium",
                        )
                        db.add(mc)
                        enrolled_total += 1

                for ch in private_channels:
                    ch_id = ch["id"]
                    if ch_id not in existing_ids:
                        mc = MonitoredChannel(
                            user_id=user_id,
                            slack_channel_id=ch_id,
                            channel_name=ch.get("name", ch_id),
                            channel_type="private",
                            priority="high",
                        )
                        db.add(mc)
                        enrolled_total += 1

                await db.commit()

                # Update Redis cache
                cache = TriageCacheService()
                for mc in await ch_repo.get_by_user(user_id, active_only=False):
                    await cache.add_channel(mc.slack_channel_id)

        except Exception as e:
            logger.error(f"Error auto-enrolling channels for user {user_id}: {e}")

    logger.info(
        f"Auto-enrolled {enrolled_total} new channels, removed {removed_total} channels "
        f"for {len(user_ids)} users"
    )
    return {
        "status": "complete",
        "enrolled_count": enrolled_total,
        "removed_count": removed_total,
        "users_processed": len(user_ids),
    }


async def update_user_channel_participation(ctx: dict) -> dict:
    """
    Daily cron: update channel participation data for all Slack-connected users.
    """
    from app.db.models.oauth_token import UserOAuthToken
    from app.services.channel_intelligence import ChannelIntelligenceService
    from sqlalchemy import select

    async with get_db_session() as db:
        result = await db.execute(
            select(UserOAuthToken.user_id).where(UserOAuthToken.provider == "slack")
        )
        user_ids = list(result.scalars().all())

    updated_count = 0
    for uid in user_ids:
        try:
            async with get_db_session() as db:
                service = ChannelIntelligenceService(db)
                count = await service.update_participation(uid)
                if count > 0:
                    updated_count += 1
        except Exception as e:
            logger.error(f"Error updating participation for user {uid}: {e}")

    logger.info(
        f"Updated channel participation for {updated_count}/{len(user_ids)} users"
    )
    return {
        "status": "complete",
        "updated_count": updated_count,
        "total_users": len(user_ids),
    }


async def update_channel_summaries(ctx: dict) -> dict:
    """
    Weekly cron: generate LLM summaries for channels across all users.
    """
    from app.services.channel_intelligence import ChannelIntelligenceService

    async with get_db_session() as db:
        service = ChannelIntelligenceService(db)
        count = await service.update_summaries()

    logger.info(f"Generated {count} channel summaries")
    return {"status": "complete", "summarized_count": count}


async def cleanup_orphaned_focus_items(ctx: dict) -> dict:
    """
    Cron: Clean up triage items stuck with focus_session_id from completed sessions.

    This handles edge cases where:
    - Focus session ended but digest failed to send
    - Focus session was deleted
    - Server crashed during session end

    Items are cleared of focus_session_id so they'll be included in scheduled digests.
    """
    from app.db.repositories.triage import TriageClassificationRepository

    async with get_db_session() as db:
        repo = TriageClassificationRepository(db)
        count = await repo.cleanup_orphaned_focus_session_items()

    logger.info(f"Cleaned up {count} orphaned focus session items")
    return {"status": "complete", "cleaned_count": count}


async def transition_pomodoro(ctx: dict, user_id: str) -> dict:
    """
    Transition pomodoro to the next phase (work -> break or break -> work).
    Called when a pomodoro phase timer ends.
    """
    async with get_db_session() as db:
        from app.services.focus_orchestrator import FocusModeOrchestrator

        logger.info(f"Transitioning pomodoro phase for user {user_id}")
        orchestrator = FocusModeOrchestrator(db)
        return await orchestrator.transition_pomodoro_phase(user_id)


async def send_digest(
    ctx: dict,
    user_id: str,
    priority: str,
    digest_type: str,
    use_conversation_grouping: bool = True,
) -> dict:
    """
    Send a digest for a specific priority level.

    Called by scheduled jobs from DigestScheduler.
    Uses conversation-aware grouping and response detection.

    Args:
        ctx: ARQ context
        user_id: User ID
        priority: Priority level (p1, p2, or p3)
        digest_type: Type of digest (scheduled, interval, daily)
        use_conversation_grouping: Whether to use conversation-aware grouping

    Returns:
        Dict with status and item count
    """
    async with get_db_session() as db:
        from app.db.repositories import UserRepository
        from app.db.repositories.triage import TriageClassificationRepository
        from app.services.substance_filter import is_substantive
        from app.services.triage_delivery import TriageDeliveryService

        delivery = TriageDeliveryService(db)
        class_repo = TriageClassificationRepository(db)
        user_repo = UserRepository(db)

        items = await class_repo.get_unalerted_scheduled_items(user_id, priority)

        if not items:
            logger.info(f"No {priority} items to digest for user {user_id}")
            return {"status": "no_items", "user_id": user_id, "priority": priority}

        logger.info(
            f"Sending {priority} {digest_type} digest to user {user_id}: {len(items)} items"
        )

        user = await user_repo.get(user_id)
        user_slack_id = user.slack_user_id if user else None

        standalone_items = []
        threaded_items = []

        for item in items:
            if item.thread_ts:
                threaded_items.append(item)
            else:
                standalone_items.append(item)

        non_substantive_ids = []
        substantive_standalone = []

        for item in standalone_items:
            if not is_substantive(item):
                non_substantive_ids.append(item.id)
            else:
                substantive_standalone.append(item)

        if non_substantive_ids:
            await class_repo.mark_processed(
                non_substantive_ids, "filtered_nonsubstantive"
            )
            logger.info(
                f"Filtered {len(non_substantive_ids)} non-substantive standalone messages"
            )

        items_for_digest = threaded_items + substantive_standalone

        if not items_for_digest:
            await db.commit()
            logger.info(f"All items filtered as non-substantive for user {user_id}")
            return {
                "status": "all_filtered",
                "user_id": user_id,
                "priority": priority,
                "original_count": len(items),
                "filtered_count": len(non_substantive_ids),
            }

        if use_conversation_grouping and user_slack_id:
            conversations = await delivery.prepare_conversation_digest(
                user_id, user_slack_id, items_for_digest
            )

            if not conversations:
                logger.info(
                    f"All {len(items_for_digest)} items filtered as responded for user {user_id}"
                )
                responded_ids = [item.id for item in items_for_digest]
                await class_repo.mark_processed(responded_ids, "summarized")
                await db.commit()
                return {
                    "status": "all_filtered",
                    "user_id": user_id,
                    "priority": priority,
                    "original_count": len(items),
                    "filtered_count": len(non_substantive_ids),
                }

            unresponded_items = []
            for conv in conversations:
                unresponded_items.extend(conv.messages)

            await delivery.send_conversation_digest_dm(
                user_id, conversations, priority, digest_type
            )

            summary_text = f"{len(conversations)} conversation{'s' if len(conversations) != 1 else ''} to review"
            summary_record = await delivery.create_scheduled_digest_summary(
                user_id=user_id,
                items=unresponded_items,
                intelligent_summary=summary_text,
            )

            summarized_ids = [item.id for item in unresponded_items]
            await class_repo.mark_processed(summarized_ids, "summarized")

            absorbed_ids = []
            for item in items_for_digest:
                if item.id not in summarized_ids:
                    absorbed_ids.append(item.id)
            if absorbed_ids:
                await class_repo.mark_processed(absorbed_ids, "absorbed_in_thread")

            await db.commit()

            logger.info(
                f"Sent {priority} {digest_type} digest to user {user_id}: "
                f"{len(conversations)} conversations from {len(items)} original items, "
                f"summary_id={summary_record.id}"
            )
            return {
                "status": "sent",
                "user_id": user_id,
                "priority": priority,
                "digest_type": digest_type,
                "conversation_count": len(conversations),
                "original_item_count": len(items),
                "unresponded_item_count": len(unresponded_items),
                "summary_id": summary_record.id,
            }
        else:
            messages = await delivery.refetch_messages_for_digest(items_for_digest)
            intelligent_summary = await delivery.create_intelligent_summary(
                messages, priority
            )
            summary_record = await delivery.create_scheduled_digest_summary(
                user_id=user_id,
                items=items_for_digest,
                intelligent_summary=intelligent_summary,
            )
            await delivery.send_priority_digest_dm(
                user_id, intelligent_summary, items_for_digest, priority, digest_type
            )

            summarized_ids = [item.id for item in items_for_digest]
            await class_repo.mark_processed(summarized_ids, "summarized")

            await db.commit()
            logger.info(
                f"Sent {priority} {digest_type} digest to user {user_id}: {len(items_for_digest)} items, "
                f"summary_id={summary_record.id}"
            )
            return {
                "status": "sent",
                "user_id": user_id,
                "priority": priority,
                "digest_type": digest_type,
                "item_count": len(items_for_digest),
                "summary_id": summary_record.id,
            }

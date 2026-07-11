"""Background tasks for the ARQ worker."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from app.core.config import get_settings
from app.db.repositories import FocusModeStateRepository
from app.db.repositories.triage import TriageUserSettingsRepository
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
    bot_id: str | None = None,
) -> dict:
    """
    Process a message through the triage pipeline.

    message_text is used in-memory only and never persisted.
    bot_id is set for messages from bots/apps, used for short-circuit logic.
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
            bot_id=bot_id,
        )
        logger.info(f"Triage pipeline complete for user={user_id} channel={channel_id}")
        return {"status": "processed", "user_id": user_id}


async def prefilter_triage_message(
    ctx: dict,
    channel_id: str,
    channel_type: str,
    sender_slack_id: str,
    message_ts: str,
    thread_ts: str | None = None,
    event_type: str = "message",
    bot_id: str | None = None,
    subtype: str | None = None,
    authorizations: list[dict] | None = None,
    message_text: str = "",  # Passed during transition for old pipeline compatibility
) -> dict:
    """
    Pre-filter a Slack message and fan out to per-user triage jobs.

    Stage 2 of the agent-driven triage pipeline.
    No message content is stored — only references are passed through.
    """
    from app.services.triage_prefilter import TriagePrefilter

    async with get_db_session() as db:
        prefilter = TriagePrefilter(db)
        applicable_users = await prefilter.get_applicable_users(
            channel_id=channel_id,
            channel_type=channel_type,
            sender_slack_id=sender_slack_id,
            authorizations=authorizations,
        )

    if not applicable_users:
        return {
            "status": "no_applicable_users",
            "channel_id": channel_id,
            "message_ts": message_ts,
        }

    # Fan out: enqueue one triage job per applicable user
    # Route to agent or legacy pipeline based on per-user feature flag
    from app.worker.scheduler import get_redis_pool

    pool = await get_redis_pool()

    async with get_db_session() as settings_db:
        settings_repo = TriageUserSettingsRepository(settings_db)

        for user_id in applicable_users:
            settings = await settings_repo.get_by_user_id(user_id)
            use_agent = settings.use_agent_triage if settings else False

            if use_agent:
                await pool.enqueue_job(
                    "run_triage_agent",
                    user_id=user_id,
                    event_type=event_type,
                    channel_id=channel_id,
                    sender_slack_id=sender_slack_id,
                    message_ts=message_ts,
                    thread_ts=thread_ts,
                    bot_id=bot_id,
                )
            else:
                await pool.enqueue_job(
                    "process_triage_job",
                    user_id=user_id,
                    event_type=event_type,
                    channel_id=channel_id,
                    sender_slack_id=sender_slack_id,
                    message_ts=message_ts,
                    thread_ts=thread_ts,
                    message_text=message_text,
                    bot_id=bot_id,
                )

    logger.info(
        f"Pre-filter: message {message_ts} in {channel_id} "
        f"queued for {len(applicable_users)} users"
    )

    return {
        "status": "queued",
        "channel_id": channel_id,
        "message_ts": message_ts,
        "user_count": len(applicable_users),
    }


async def run_triage_agent(
    ctx: dict,
    user_id: str,
    event_type: str,
    channel_id: str,
    sender_slack_id: str,
    message_ts: str,
    thread_ts: str | None = None,
    bot_id: str | None = None,
) -> dict:
    """Run the triage agent to classify a message.

    This replaces process_triage_job for users with use_agent_triage=True.
    """
    from app.agents.triage.agent import TriageAgent

    async with get_db_session() as db:
        settings_repo = TriageUserSettingsRepository(db)
        settings = await settings_repo.get_by_user_id(user_id)

        agent = TriageAgent(db)
        result = await agent.classify(
            user_id=user_id,
            channel_id=channel_id,
            message_ts=message_ts,
            sender_slack_id=sender_slack_id,
            event_type=event_type,
            thread_ts=thread_ts,
            bot_id=bot_id,
            sensitivity=settings.sensitivity if settings else "medium",
            custom_rules=settings.custom_classification_rules if settings else None,
            p0_definition=settings.p0_definition if settings else None,
            p1_definition=settings.p1_definition if settings else None,
            p2_definition=settings.p2_definition if settings else None,
            p3_definition=settings.p3_definition if settings else None,
            p1_max_wait_minutes=settings.p1_max_wait_minutes if settings else 60,
            p1_settled_threshold_minutes=settings.p1_settled_threshold_minutes if settings else 30,
            eod_review_time=settings.eod_review_time if settings else "17:30",
        )

        # Check for failure: explicit error OR no action taken
        agent_failed = result.get("error") and not result.get("action_taken")
        no_action = not result.get("action_taken") and not result.get("error")

        if agent_failed or no_action:
            retry_count = ctx.get("job_try", 1)
            failure_reason = result.get("error") or "Agent completed without taking an action"

            if retry_count >= 3 or no_action:
                # After 3 retries or if agent simply didn't act, create fallback
                from app.db.models.triage import TriageClassification
                from app.db.repositories.triage import TriageClassificationRepository

                repo = TriageClassificationRepository(db)
                classification = TriageClassification(
                    user_id=user_id,
                    sender_slack_id=sender_slack_id,
                    channel_id=channel_id,
                    message_ts=message_ts,
                    thread_ts=thread_ts,
                    action="summarize_eod",
                    confidence=0.0,
                    classification_reason=f"Agent fallback: {failure_reason}",
                    abstract="Message pending review (agent classification incomplete)",
                    classification_path=event_type,
                    queued_for_digest=True,
                    needs_review=True,
                    retry_count=retry_count,
                )
                await repo.create(classification)
                await db.commit()
                logger.warning(
                    f"Triage agent fallback for user {user_id}, message {message_ts}: {failure_reason}"
                )
                return {"status": "fallback", "reason": failure_reason}
            else:
                raise Exception(f"Triage agent failed (attempt {retry_count}): {failure_reason}")

        await db.commit()
        logger.info(
            f"Triage agent classified message {message_ts} for user {user_id}: "
            f"action={result.get('action_taken')}, tools={result.get('tool_call_count')}"
        )
        return {
            "status": "classified",
            "action_taken": result.get("action_taken"),
            "classification_id": result.get("classification_id"),
            "tool_iterations": result.get("tool_iterations"),
        }


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
    from sqlalchemy import select

    from app.db.models.triage import MonitoredChannel, TriageUserSettings
    from app.db.repositories.triage import MonitoredChannelRepository
    from app.services.slack_user import SlackUserService
    from app.services.triage_cache import TriageCacheService

    async with get_db_session() as db:
        # Get all users with triage enabled
        result = await db.execute(
            select(TriageUserSettings.user_id).where(
                TriageUserSettings.is_always_on.is_(True)
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
                from slack_sdk.web.async_client import AsyncWebClient

                from app.services.slack import _paginate_conversations

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
    from sqlalchemy import select

    from app.db.models.oauth_token import UserOAuthToken
    from app.services.channel_intelligence import ChannelIntelligenceService

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

    Called by DigestDeliveryOrchestrator via check_delivery_triggers.
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

        if priority == "all":
            items = await class_repo.get_unalerted_all_priorities(user_id)
        else:
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

            if priority == "all":
                await delivery.send_end_of_day_digest_dm(user_id, conversations)
            else:
                await delivery.send_conversation_digest_dm(
                    user_id, conversations, priority, digest_type
                )

            summary_text = f"{len(conversations)} conversation{'s' if len(conversations) != 1 else ''} to review"
            summary_record = await delivery.create_scheduled_digest_summary(
                user_id=user_id,
                items=unresponded_items,
                intelligent_summary=summary_text,
            )

            await delivery.persist_conversations_to_summary(
                conversations=conversations,
                digest_summary_id=summary_record.id,
                user_id=user_id,
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


async def cleanup_slack_message_cache(ctx: dict) -> dict:
    """
    Cron job: delete Slack message cache rows older than retention period.
    Runs daily at 2 AM UTC.

    Uses batching (1000 rows per batch) for operational safety to avoid
    long-running transactions and table locks.
    """
    from sqlalchemy import text

    settings = get_settings()
    retention_days = settings.slack_message_cache_retention_days
    batch_size = 1000

    logger.info(
        f"Starting Slack message cache cleanup (retention={retention_days} days)"
    )

    cutoff = datetime.utcnow() - timedelta(days=retention_days)

    async with get_db_session() as db:
        total_deleted = 0
        while True:
            try:
                result = await db.execute(
                    text(
                        "DELETE FROM slack_message_cache "
                        "WHERE cached_at < :cutoff "
                        "LIMIT :batch_size"
                    ),
                    {"cutoff": cutoff, "batch_size": batch_size},
                )
                deleted = result.rowcount

                if deleted == 0:
                    break

                total_deleted += deleted
                logger.debug(f"Deleted batch of {deleted} cache rows")
                await db.commit()

            except Exception as e:
                logger.error(f"Error deleting cache batch: {e}")
                return {"status": "error", "deleted_count": total_deleted, "error": str(e)}

        logger.info(f"Deleted {total_deleted} expired Slack message cache rows")
        return {"status": "complete", "deleted_count": total_deleted}


async def check_escalations(ctx: dict, user_id: str) -> dict:
    """
    Check for escalation patterns and promote summarize_next → notify_now.

    Patterns detected:
    - Multi-ping: Same sender messages 2+ times within 5 minutes
    - Thread acceleration: ≥5 new messages in 10 minutes (Phase 3 placeholder)

    Runs every 5 minutes per user with active triage.
    """
    async with get_db_session() as db:
        from app.services.escalation_detector import EscalationDetector
        from app.services.slack import SlackService

        detector = EscalationDetector(db)
        slack = SlackService()
        since = datetime.utcnow() - timedelta(minutes=30)

        triggers = await detector.detect_escalations(user_id, since)

        if not triggers:
            return {"status": "no_escalations", "user_id": user_id}

        promoted_count = 0
        for trigger in triggers[:5]:
            if await detector.evaluate_escalation(trigger, slack):
                promoted = await detector.promote_to_notify_now(
                    trigger.classification_id,
                    trigger.reason,
                )
                if promoted:
                    promoted_count += 1

        logger.info(f"Escalation check for {user_id}: {promoted_count}/{len(triggers)} promoted")
        return {
            "status": "complete",
            "user_id": user_id,
            "triggers_found": len(triggers),
            "promoted_count": promoted_count,
        }


async def check_delivery_triggers(ctx: dict) -> dict:
    """
    Cron job: Check delivery triggers for all users with pending items.

    Runs every 5 minutes to check:
    - Calendar end triggers (meeting just ended)
    - Stale queue triggers (items > 30 min old)
    - Idle detection (placeholder)
    """
    from app.services.digest_delivery_orchestrator import DigestDeliveryOrchestrator

    async with get_db_session() as db:
        orchestrator = DigestDeliveryOrchestrator(db)
        user_ids = await orchestrator.get_users_with_pending_items()

    triggered_count = 0
    delivered_count = 0

    for user_id in user_ids:
        try:
            async with get_db_session() as db:
                orchestrator = DigestDeliveryOrchestrator(db)
                trigger = await orchestrator.check_triggers(user_id)

                if trigger:
                    triggered_count += 1
                    result = await orchestrator.deliver_summarize_next(
                        user_id, trigger
                    )
                    if result.get("status") == "enqueued":
                        delivered_count += 1

        except Exception as e:
            logger.error(f"Error checking delivery triggers for user {user_id}: {e}")

    logger.info(
        f"Delivery trigger check complete: {triggered_count} triggered, "
        f"{delivered_count} delivered for {len(user_ids)} users"
    )
    return {
        "status": "complete",
        "users_checked": len(user_ids),
        "triggered_count": triggered_count,
        "delivered_count": delivered_count,
    }


async def check_delivery_readiness(ctx: dict) -> dict:
    """Check if any message groups are ready for delivery (agent-driven triage only).

    Runs every 3 minutes. For users with use_agent_triage=True:
    - Checks P1 groups for settle/TTL readiness
    - Checks EOD time for P2 digest delivery
    - Dispatches digest subagent for ready batches
    """
    from app.services.delivery_checker import DeliveryChecker
    from app.worker.scheduler import get_redis_pool

    async with get_db_session() as db:
        checker = DeliveryChecker(db)
        settings_repo = TriageUserSettingsRepository(db)
        pool = await get_redis_pool()

        # Check P1 groups
        users_with_p1 = await checker.get_users_with_queued_p1()
        p1_dispatched = 0

        for user_id in users_with_p1:
            settings = await settings_repo.get_by_user_id(user_id)
            if not settings or not settings.use_agent_triage:
                continue

            ready_groups = await checker.get_ready_p1_groups(user_id)
            if ready_groups:
                await pool.enqueue_job(
                    "run_digest_agent",
                    user_id=user_id,
                    digest_type="p1",
                    group_data=ready_groups,
                    p3_count=0,
                )
                p1_dispatched += 1

        # Check EOD digests
        eod_dispatched = 0
        all_settings = await settings_repo.get_all_always_on()

        for settings in all_settings:
            if not settings.use_agent_triage:
                continue
            if not settings.eod_review_time:
                continue

            try:
                from app.services.timezone import get_current_time_in_tz, get_user_timezone

                user_tz = await get_user_timezone(db, str(settings.user_id))
                current_time = get_current_time_in_tz(user_tz)
                current_hhmm = current_time.strftime("%H:%M")

                if checker.is_eod_time(settings.eod_review_time, current_hhmm):
                    p2_messages = await checker.get_queued_p2_messages(str(settings.user_id))
                    p3_count = await checker.count_p3_messages(str(settings.user_id))

                    if p2_messages or p3_count > 0:
                        p2_groups = []
                        for msg in p2_messages:
                            p2_groups.append({
                                "group_id": msg.group_id or str(msg.id),
                                "message_ids": [str(msg.id)],
                            })

                        await pool.enqueue_job(
                            "run_digest_agent",
                            user_id=str(settings.user_id),
                            digest_type="eod",
                            group_data=p2_groups,
                            p3_count=p3_count,
                        )
                        eod_dispatched += 1
            except Exception:
                logger.exception(f"Error checking EOD for user {settings.user_id}")

    logger.info(f"Delivery readiness check: p1={p1_dispatched}, eod={eod_dispatched}")
    return {"p1_dispatched": p1_dispatched, "eod_dispatched": eod_dispatched}


async def run_digest_agent(
    ctx: dict,
    user_id: str,
    digest_type: str,
    group_data: list[dict],
    p3_count: int = 0,
) -> dict:
    """Run the digest subagent to compose and deliver a digest."""
    from app.agents.digest.agent import DigestAgent
    from app.db.repositories.triage import TriageClassificationRepository

    async with get_db_session() as db:
        repo = TriageClassificationRepository(db)

        # Hydrate groups with message data from DB
        groups = []
        for group in group_data:
            messages = []
            for msg_id in group["message_ids"]:
                item = await repo.get(msg_id)
                if item:
                    messages.append({
                        "id": str(item.id),
                        "sender_name": item.sender_name or "",
                        "channel_name": item.channel_name or "",
                        "abstract": item.abstract or "",
                        "action": item.action,
                        "message_ts": item.message_ts,
                        "thread_ts": item.thread_ts,
                        "slack_permalink": item.slack_permalink or "",
                    })
            if messages:
                groups.append({
                    "group_id": group["group_id"],
                    "messages": messages,
                })

        if not groups:
            return {"status": "no_messages"}

        agent = DigestAgent(db)
        result = await agent.compose_and_deliver(
            user_id=user_id,
            digest_type=digest_type,
            groups=groups,
            p3_count=p3_count,
        )

        await db.commit()

        logger.info(
            f"Digest agent completed for user {user_id}: "
            f"type={digest_type}, sent={result.get('digest_sent')}"
        )
        return result


async def deliver_eod_digests(ctx: dict) -> dict:
    """
    Cron job: Deliver EOD digests at configured times.

    Runs every 5 minutes to check each user's EOD review time
    and deliver if it matches current time in their timezone.
    """
    from app.services.digest_delivery_orchestrator import DigestDeliveryOrchestrator
    from app.services.timezone import get_current_time_in_tz, get_user_timezone

    async with get_db_session() as db:
        settings_repo = TriageUserSettingsRepository(db)
        all_settings = await settings_repo.get_all_always_on()

    delivered_count = 0

    for settings in all_settings:
        try:
            user_id = settings.user_id
            if not settings.eod_review_time:
                logger.debug(f"Skipping user {user_id}: no EOD review time configured")
                continue

            # Create a fresh session for each user's timezone lookup
            async with get_db_session() as db:
                user_tz = await get_user_timezone(db, user_id)
                now_local = get_current_time_in_tz(user_tz)
                current_time = now_local.strftime("%H:%M")

                logger.debug(
                    f"EOD check for user {user_id}: "
                    f"current_time={current_time}, eod_review_time={settings.eod_review_time}, tz={user_tz}"
                )

                if current_time == settings.eod_review_time:
                    orchestrator = DigestDeliveryOrchestrator(db)
                    result = await orchestrator.deliver_eod_digest(user_id)
                    logger.info(f"EOD digest result for user {user_id}: {result}")
                    if result.get("status") == "enqueued":
                        delivered_count += 1

        except Exception as e:
            logger.error(f"Error delivering EOD digest for user {settings.user_id}: {e}", exc_info=True)

    logger.info(f"EOD digest check complete: {delivered_count} delivered")
    return {
        "status": "complete",
        "delivered_count": delivered_count,
        "users_checked": len(all_settings),
    }


async def degrade_stale_notify_now(ctx: dict) -> dict:
    """
    Cron job: Degrade notify_now items not engaged with after timeout.

    Default timeout: 4 hours (configurable per user via notify_now_degrade_minutes).
    Degrades to summarize_next for inclusion in next digest.

    Runs every 5 minutes.
    """
    from sqlalchemy import and_, select

    from app.db.models.triage import TriageClassification, TriageUserSettings

    async with get_db_session() as db:
        result = await db.execute(
            select(TriageUserSettings).where(
                TriageUserSettings.is_always_on == True  # noqa: E712
            )
        )
        all_settings = list(result.scalars().all())

    degraded_total = 0

    for settings in all_settings:
        user_id = settings.user_id
        timeout_minutes = settings.notify_now_degrade_minutes or 240
        cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)

        async with get_db_session() as db:
            result = await db.execute(
                select(TriageClassification).where(
                    and_(
                        TriageClassification.user_id == user_id,
                        TriageClassification.action == "notify_now",
                        TriageClassification.created_at < cutoff,
                        TriageClassification.reviewed_at.is_(None),
                    )
                )
            )
            stale = list(result.scalars().all())

            for item in stale:
                item.action = "summarize_next"
                if item.classification_reason:
                    item.classification_reason = (
                        f"[AUTO-DEGRADED] {item.classification_reason}"
                    )
                else:
                    item.classification_reason = "[AUTO-DEGRADED] No reason provided"
                degraded_total += 1

            if stale:
                await db.commit()
                logger.info(
                    f"Degraded {len(stale)} stale notify_now items for user {user_id}"
                )

    logger.info(f"Notify_now auto-degrade complete: {degraded_total} items degraded")
    return {
        "status": "complete",
        "degraded_count": degraded_total,
        "users_checked": len(all_settings),
    }

"""
Scheduled memory extraction task.

This task reviews conversation sessions and extracts memorable facts about users.
Run it periodically via cron, Cloud Scheduler, or similar.

Usage:
    python -m app.tasks.extract_memories
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.embeddings import get_embedding_provider
from app.core.llm import LLMMessage, get_llm_provider
from app.db.models import Message, Session, User
from app.db.repositories import MemoryRepository
from app.db.session import async_session_maker

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """Review these conversation sessions and extract memorable facts about the user.

Categories:
- preference: Things they like/dislike, communication style, settings preferences
- knowledge: Personal facts (job, location, projects, relationships, skills)
- summary: Key decisions or outcomes from substantial conversations

Return a JSON array of objects with "type" and "content" fields.
Be selective - only extract genuinely useful information that would help personalize future interactions.
Avoid duplicating information already in the existing memories list.

Existing memories (do not duplicate):
{existing_memories}

Conversation messages:
{messages}

Return ONLY valid JSON array, no explanation. Example format:
[
  {{"type": "preference", "content": "Prefers concise responses without excessive formality"}},
  {{"type": "knowledge", "content": "Works as a software engineer at Acme Corp"}}
]

If there are no new memories to extract, return an empty array: []
"""


async def get_users_for_extraction(db: AsyncSession) -> list[User]:
    """Get all users who may need memory extraction."""
    result = await db.execute(select(User))
    return list(result.scalars().all())


async def get_sessions_since(
    db: AsyncSession,
    user_id: str,
    since: datetime | None,
) -> list[Session]:
    """Get sessions with messages since the given timestamp."""
    query = (
        select(Session)
        .options(selectinload(Session.messages))
        .where(Session.user_id == user_id)
    )

    if since:
        # Get sessions updated since the last extraction
        query = query.where(Session.updated_at > since)
    else:
        # First extraction - get recent sessions (last 7 days)
        week_ago = datetime.utcnow() - timedelta(days=7)
        query = query.where(Session.created_at > week_ago)

    query = query.order_by(Session.created_at.asc())
    result = await db.execute(query)
    return list(result.scalars().all())


def format_messages_for_extraction(sessions: list[Session]) -> str:
    """Format session messages for the LLM prompt."""
    lines = []
    for session in sessions:
        if not session.messages:
            continue
        lines.append(f"\n--- Session: {session.title or 'Untitled'} ---")
        for msg in sorted(session.messages, key=lambda m: m.created_at):
            lines.append(f"{msg.role.upper()}: {msg.content}")
    return "\n".join(lines)


def format_existing_memories(memories: list[str]) -> str:
    """Format existing memories for the prompt."""
    if not memories:
        return "(none)"
    return "\n".join(f"- {m}" for m in memories)


async def extract_memories_from_sessions(
    sessions: list[Session],
    existing_memories: list[str],
) -> list[dict[str, str]]:
    """Use LLM to extract memories from conversation sessions."""
    if not sessions:
        return []

    messages_text = format_messages_for_extraction(sessions)
    if not messages_text.strip():
        return []

    existing_text = format_existing_memories(existing_memories)

    prompt = EXTRACTION_PROMPT.format(
        existing_memories=existing_text,
        messages=messages_text,
    )

    llm_provider = get_llm_provider()
    messages = [
        LLMMessage(role="system", content="You are a memory extraction assistant."),
        LLMMessage(role="user", content=prompt),
    ]

    try:
        response = await llm_provider.generate(messages)

        # Parse JSON response
        # Handle markdown code blocks if present
        response = response.strip()
        if response.startswith("```"):
            # Remove markdown code block
            lines = response.split("\n")
            response = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        memories = json.loads(response)
        if not isinstance(memories, list):
            logger.warning("LLM returned non-list response: %s", response)
            return []

        # Validate each memory
        valid_memories = []
        for mem in memories:
            if isinstance(mem, dict) and "type" in mem and "content" in mem:
                if mem["type"] in ("preference", "knowledge", "summary"):
                    valid_memories.append(mem)
                else:
                    logger.warning("Invalid memory type: %s", mem["type"])

        return valid_memories

    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM response as JSON: %s", e)
        return []
    except Exception as e:
        logger.error("Error during memory extraction: %s", e)
        return []


async def save_extracted_memories(
    db: AsyncSession,
    user_id: str,
    memories: list[dict[str, str]],
    source_session_id: str | None = None,
) -> int:
    """
    Save extracted memories, checking for duplicates.

    Returns the number of new memories saved.
    """
    if not memories:
        return 0

    settings = get_settings()
    memory_repo = MemoryRepository(db)
    embedding_provider = get_embedding_provider()

    saved_count = 0
    for mem in memories:
        content = mem["content"]
        memory_type = mem["type"]

        # Generate embedding
        embedding = embedding_provider.embed(content)

        # Check for duplicates
        existing = await memory_repo.find_duplicate(
            user_id=user_id,
            embedding=embedding,
            threshold=settings.memory_similarity_threshold,
        )

        if existing:
            logger.debug("Skipping duplicate memory: %s", content[:50])
            continue

        # Save new memory
        await memory_repo.create_memory(
            user_id=user_id,
            type=memory_type,
            content=content,
            embedding=embedding,
            source_session_id=source_session_id,
        )
        saved_count += 1
        logger.info("Saved new memory for user %s: %s", user_id, content[:50])

    return saved_count


async def extract_user_memories(db: AsyncSession, user: User) -> int:
    """Extract memories for a single user."""
    memory_repo = MemoryRepository(db)

    # Get last extraction time
    last_extraction = await memory_repo.get_last_extraction_time(user.id)
    logger.info(
        "Processing user %s, last extraction: %s",
        user.email,
        last_extraction or "never",
    )

    # Get sessions to process
    sessions = await get_sessions_since(db, user.id, last_extraction)
    if not sessions:
        logger.info("No new sessions for user %s", user.email)
        return 0

    logger.info("Found %d sessions for user %s", len(sessions), user.email)

    # Get existing memories for deduplication
    existing = await memory_repo.get_user_memories(user.id, limit=100)
    existing_contents = [m.content for m in existing]

    # Extract memories
    extracted = await extract_memories_from_sessions(sessions, existing_contents)
    logger.info("Extracted %d potential memories", len(extracted))

    # Save memories (with deduplication)
    # Use the most recent session as the source
    source_session_id = sessions[-1].id if sessions else None
    saved = await save_extracted_memories(
        db, user.id, extracted, source_session_id
    )

    await db.commit()
    return saved


async def run_extraction() -> dict[str, int]:
    """
    Run memory extraction for all users.

    Returns a dict mapping user_id to number of memories saved.
    """
    results: dict[str, int] = {}

    async with async_session_maker() as db:
        users = await get_users_for_extraction(db)
        logger.info("Processing %d users for memory extraction", len(users))

        for user in users:
            try:
                saved = await extract_user_memories(db, user)
                results[user.id] = saved
            except Exception as e:
                logger.error("Error processing user %s: %s", user.email, e)
                results[user.id] = 0

    return results


def main() -> None:
    """Entry point for running the extraction task."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting memory extraction task")
    results = asyncio.run(run_extraction())

    total_saved = sum(results.values())
    logger.info(
        "Memory extraction complete. Processed %d users, saved %d total memories",
        len(results),
        total_saved,
    )


if __name__ == "__main__":
    main()

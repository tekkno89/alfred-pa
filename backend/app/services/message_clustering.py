"""Message clustering — LLM-based clustering for unthreaded channel messages."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.db.models.triage import TriageClassification

logger = logging.getLogger(__name__)

MAX_CLUSTERING_BATCH_SIZE = 40
CONVERSATION_GAP_THRESHOLD_MINUTES = 10


@dataclass
class MessageCluster:
    """A cluster of related messages identified by LLM."""

    cluster_id: str
    message_ids: list[str]
    messages: list["TriageClassification"]


def parse_ts(ts: str) -> datetime:
    """Parse Slack timestamp (seconds.microseconds) to datetime."""
    seconds = float(ts.split(".")[0])
    microseconds = float(f"0.{ts.split('.')[1]}") if "." in ts else 0
    return datetime.utcfromtimestamp(seconds + microseconds)


def find_split_point(
    messages: list["TriageClassification"],
    gap_threshold_minutes: int = CONVERSATION_GAP_THRESHOLD_MINUTES,
) -> int:
    """Find best split point for a batch of messages.

    1. Find all gaps >= gap_threshold_minutes between consecutive messages
    2. If gaps exist, pick one closest to midpoint (len(messages) // 2)
    3. Otherwise, split at midpoint by count

    Args:
        messages: List of messages sorted by timestamp
        gap_threshold_minutes: Minimum gap to consider as conversation boundary

    Returns:
        Index at which to split the list
    """
    if len(messages) <= 1:
        return len(messages)

    midpoint = len(messages) // 2

    gaps = []
    for i in range(1, len(messages)):
        try:
            time_diff = parse_ts(messages[i].message_ts) - parse_ts(
                messages[i - 1].message_ts
            )
            if time_diff >= timedelta(minutes=gap_threshold_minutes):
                gaps.append((i, abs(i - midpoint)))
        except (ValueError, IndexError):
            continue

    if gaps:
        best_gap = min(gaps, key=lambda x: x[1])
        return best_gap[0]

    return midpoint


def partition_messages(
    messages: list["TriageClassification"],
    max_batch_size: int = MAX_CLUSTERING_BATCH_SIZE,
) -> list[list["TriageClassification"]]:
    """Partition messages into batches for clustering.

    Uses gap detection to find natural conversation boundaries.
    Never returns a batch larger than max_batch_size.

    Args:
        messages: List of messages to partition
        max_batch_size: Maximum messages per batch

    Returns:
        List of message batches
    """
    if not messages:
        return []

    sorted_messages = sorted(messages, key=lambda m: m.message_ts)

    if len(sorted_messages) <= max_batch_size:
        return [sorted_messages]

    batches = []
    remaining = sorted_messages

    while len(remaining) > max_batch_size:
        split_idx = find_split_point(remaining[: max_batch_size + 10])
        split_idx = min(split_idx, max_batch_size)
        if split_idx == 0:
            split_idx = max_batch_size

        batches.append(remaining[:split_idx])
        remaining = remaining[split_idx:]

    if remaining:
        batches.append(remaining)

    return batches


async def cluster_messages_with_llm(
    messages: list["TriageClassification"],
    user_name_resolver: dict[str, str] | None = None,
) -> list[MessageCluster]:
    """Cluster messages using LLM to identify conversation boundaries.

    Args:
        messages: List of messages to cluster (already partitioned)
        user_name_resolver: Optional dict mapping user_id -> display_name

    Returns:
        List of MessageCluster objects
    """
    if not messages:
        return []

    if len(messages) == 1:
        return [
            MessageCluster(
                cluster_id="c1",
                message_ids=[messages[0].id],
                messages=[messages[0]],
            )
        ]

    from app.core.config import get_settings
    from app.core.llm import LLMMessage, get_llm_provider

    settings = get_settings()
    provider = get_llm_provider(
        settings.web_search_synthesis_model or "gemini-2.5-flash-lite"
    )

    payload = []
    for msg in messages:
        user_id = msg.sender_slack_id
        user_name = (
            user_name_resolver.get(user_id, user_id)
            if user_name_resolver
            else (msg.sender_name or user_id)
        )
        preview = (msg.abstract or "")[:200]
        payload.append(
            {
                "id": msg.id,
                "user": user_name,
                "ts": msg.message_ts,
                "preview": preview,
            }
        )

    system_prompt = f"""You are analyzing Slack messages to identify distinct conversations.

Messages (JSON array):
{json.dumps(payload, indent=2)}

Task: Group these messages into clusters based on conversation topic.

Rules:
- Messages in the same cluster should be about the same topic or related topics
- Users responding to each other should be in the same cluster
- Singleton clusters are OK for standalone announcements, off-topic messages, or one-liners
- DO NOT over-merge unrelated messages

Output JSON format (temperature 0, strict schema):
{{
  "clusters": [
    {{"cluster_id": "c1", "message_ids": ["msg_id_1", "msg_id_2"]}},
    {{"cluster_id": "c2", "message_ids": ["msg_id_3"]}}
  ]
}}

IMPORTANT:
- cluster_id should be "c1", "c2", etc.
- message_ids must match the "id" field from input
- Each message should appear in exactly ONE cluster
- Output ONLY the JSON, no other text"""

    try:
        response = await provider.generate(
            messages=[LLMMessage(role="user", content=system_prompt)],
            temperature=0,
            max_tokens=1000,
        )

        response_text = response.strip()
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        result = json.loads(response_text)
        clusters_data = result.get("clusters", [])

        if not clusters_data:
            return _fallback_singleton_clusters(messages)

        clusters = []
        msg_by_id = {m.id: m for m in messages}

        for cluster_data in clusters_data:
            cluster_id = cluster_data.get("cluster_id", f"c{len(clusters) + 1}")
            message_ids = cluster_data.get("message_ids", [])

            cluster_messages = [
                msg_by_id[mid] for mid in message_ids if mid in msg_by_id
            ]

            if cluster_messages:
                clusters.append(
                    MessageCluster(
                        cluster_id=cluster_id,
                        message_ids=[m.id for m in cluster_messages],
                        messages=cluster_messages,
                    )
                )

        covered_ids = set()
        for c in clusters:
            covered_ids.update(c.message_ids)

        for msg in messages:
            if msg.id not in covered_ids:
                clusters.append(
                    MessageCluster(
                        cluster_id=f"c_orphan_{msg.id[:8]}",
                        message_ids=[msg.id],
                        messages=[msg],
                    )
                )

        logger.info(
            f"LLM clustered {len(messages)} messages into {len(clusters)} clusters"
        )
        return clusters

    except json.JSONDecodeError as e:
        logger.warning(f"Malformed JSON from clustering LLM: {e}")
        return _fallback_singleton_clusters(messages)
    except Exception as e:
        logger.warning(f"Clustering failed, using singleton fallback: {e}")
        return _fallback_singleton_clusters(messages)


def _fallback_singleton_clusters(
    messages: list["TriageClassification"],
) -> list[MessageCluster]:
    """Create singleton clusters for each message (fallback on error)."""
    return [
        MessageCluster(
            cluster_id=f"c{i + 1}",
            message_ids=[m.id],
            messages=[m],
        )
        for i, m in enumerate(messages)
    ]

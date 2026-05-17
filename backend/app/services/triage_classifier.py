"""Triage classifier — LLM-based message classification."""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.config import get_settings
from app.core.llm import LLMMessage, get_llm_provider
from app.services.triage_enrichment import EnrichedTriagePayload

if TYPE_CHECKING:
    from app.services.learned_example_retriever import LearnedExample

logger = logging.getLogger(__name__)

DEFAULT_NOTIFY_NOW = (
    "Needs immediate attention RIGHT NOW. Production incidents, emergencies, "
    "someone explicitly saying something is urgent/critical. Direct questions "
    "that require an immediate response."
)

DEFAULT_SUMMARIZE_NEXT = (
    "Time-sensitive requests that need action soon. Direct asks requiring a response, "
    "important questions needing input, meaningful requests with a deadline. "
    "Should be included in the next available digest window."
)

DEFAULT_SUMMARIZE_EOD = (
    "Noteworthy but not time-sensitive. Project updates, FYI items, relevant "
    "discussions, informational messages worth reviewing in the end-of-day digest."
)

DEFAULT_IGNORE = (
    "Low priority. General chatter, memes, social messages, non-work banter, "
    "automated notifications that need no action. @here, @channel, @everyone "
    "broadcasts that are not specifically relevant to the user."
)


def _parse_json_response(response: str) -> dict:
    """Extract and parse JSON from an LLM response.

    Handles markdown code fences, single quotes, extra text around JSON,
    and truncated responses (e.g. from thinking models exceeding token budget).
    """
    text = response.strip()
    # Strip markdown code fences (```json ... ```)
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    elif text.startswith("```"):
        # Opening fence without closing — likely truncated response
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting JSON object with regex
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            # Try replacing single quotes with double quotes
            fixed = match.group().replace("'", '"')
            return json.loads(fixed)
    # Last resort: extract individual fields from truncated JSON
    result = _extract_fields_from_truncated(text)
    if result:
        return result
    raise json.JSONDecodeError("No JSON object found in response", text, 0)


def _extract_fields_from_truncated(text: str) -> dict | None:
    """Best-effort field extraction from truncated JSON."""
    action_m = re.search(r'"action"\s*:\s*"(\w+)"', text)
    if not action_m:
        priority_m = re.search(r'"priority"\s*:\s*"(\w+)"', text)
        if priority_m:
            old_to_new = {
                "p0": "notify_now",
                "p1": "summarize_next",
                "p2": "summarize_eod",
                "p3": "ignore",
                "review": "notify_now",
            }
            action_m = type("Match", (), {"group": lambda self, i: old_to_new.get(priority_m.group(1), "summarize_eod")})()
    if not action_m:
        return None
    confidence_m = re.search(r'"confidence"\s*:\s*([\d.]+)', text)
    reason_m = re.search(r'"reason"\s*:\s*"((?:[^"\\]|\\.)*)"?', text, re.DOTALL)
    abstract_m = re.search(r'"abstract"\s*:\s*"((?:[^"\\]|\\.)*)"?', text, re.DOTALL)
    return {
        "action": action_m.group(1),
        "confidence": float(confidence_m.group(1)) if confidence_m else 0.5,
        "reason": reason_m.group(1)
        if reason_m
        else "LLM classification (truncated response)",
        "abstract": abstract_m.group(1) if abstract_m else "Message classified by AI",
    }


@dataclass
class ReasoningSignals:
    """Structured reasoning behind classification."""

    few_shot_examples: list["LearnedExample"] = field(default_factory=list)
    sender_distribution: dict | None = None
    topic_bias: list[str] = field(default_factory=list)
    channel_rule: str | None = None
    vip_sender: bool = False
    confidence_threshold_met: bool = True


@dataclass
class ClassificationResult:
    """Result of classifying a message."""

    action: str  # notify_now | summarize_next | summarize_eod | ignore
    confidence: float
    reason: str
    abstract: str
    review: bool = False
    keyword_matches: list[str] = field(default_factory=list)
    reasoning_signals: ReasoningSignals = field(default_factory=ReasoningSignals)

    @property
    def priority(self) -> str:
        """Map action to priority for backward compatibility."""
        mapping = {
            "notify_now": "p0",
            "summarize_next": "p1",
            "summarize_eod": "p2",
            "ignore": "p3",
        }
        return mapping.get(self.action, "p2")


class TriageClassifier:
    """Classifies messages into action labels."""

    def __init__(
        self,
        sensitivity: str = "medium",
        custom_classification_rules: str | None = None,
        notify_now_definition: str | None = None,
        summarize_next_definition: str | None = None,
        summarize_eod_definition: str | None = None,
        ignore_definition: str | None = None,
        p0_definition: str | None = None,
        p1_definition: str | None = None,
        p2_definition: str | None = None,
        p3_definition: str | None = None,
    ) -> None:
        self.sensitivity = sensitivity
        self.custom_classification_rules = custom_classification_rules
        self.notify_now_definition = notify_now_definition or p0_definition or DEFAULT_NOTIFY_NOW
        self.summarize_next_definition = summarize_next_definition or p1_definition or DEFAULT_SUMMARIZE_NEXT
        self.summarize_eod_definition = summarize_eod_definition or p2_definition or DEFAULT_SUMMARIZE_EOD
        self.ignore_definition = ignore_definition or p3_definition or DEFAULT_IGNORE

    async def classify(self, payload: EnrichedTriagePayload) -> ClassificationResult:
        """Classify a message based on enriched context."""
        if payload.event_type == "dm":
            return await self._classify_dm(payload)
        return await self._classify_channel(payload)

    async def _classify_dm(
        self, payload: EnrichedTriagePayload
    ) -> ClassificationResult:
        """
        Classify a DM with content-aware VIP handling.

        VIP status influences classification but doesn't auto-P0.
        Instead, VIP context is passed to LLM for higher priority consideration.
        VIP senders are floored at summarize_next (never ignored).
        """
        result = await self._llm_classify(payload, path="dm", vip_boost=payload.is_vip)
        return self._apply_vip_floor(result, payload.is_vip)

    async def _classify_channel(
        self, payload: EnrichedTriagePayload
    ) -> ClassificationResult:
        """Classify a channel message."""
        if payload.channel_priority == "critical":
            reasoning_signals = ReasoningSignals(
                channel_rule="critical_channel",
                vip_sender=payload.is_vip,
                confidence_threshold_met=True,
            )
            return ClassificationResult(
                action="notify_now",
                confidence=0.9,
                reason=f"Channel #{payload.channel_name} is set to critical priority",
                abstract=f"Message in critical channel #{payload.channel_name}",
                reasoning_signals=reasoning_signals,
            )

        result = await self._llm_classify(payload, path="channel")
        return self._apply_vip_floor(result, payload.is_vip)

    def _apply_vip_floor(
        self, result: ClassificationResult, is_vip: bool
    ) -> ClassificationResult:
        """Floor VIP senders at summarize_next (never ignore).

        If a VIP sender's message would be classified as "ignore",
        upgrade it to "summarize_next" to ensure guaranteed attention.

        Returns a new ClassificationResult (does not mutate input).
        """
        if is_vip and result.action == "ignore":
            return ClassificationResult(
                action="summarize_next",
                confidence=max(result.confidence, 0.7),
                reason=f"[VIP sender] {result.reason}",
                abstract=result.abstract,
                review=result.review,
                keyword_matches=result.keyword_matches,
                reasoning_signals=result.reasoning_signals,
            )
        return result

    async def _llm_classify(
        self, payload: EnrichedTriagePayload, path: str, vip_boost: bool = False
    ) -> ClassificationResult:
        """Use LLM to classify the message."""
        settings = get_settings()
        location = settings.triage_vertex_location or None
        provider = get_llm_provider(
            settings.triage_classification_model, location=location
        )

        sensitivity_guidance = {
            "low": "Only classify as notify_now if there is a genuine emergency or the sender explicitly says it's urgent.",
            "medium": "Classify as notify_now if the message appears to need immediate attention. Use summarize_next for time-sensitive requests.",
            "high": "Be liberal with notify_now/summarize_next classification. Any message that could be important should be marked accordingly.",
        }

        # Build VIP context
        vip_context = ""
        if vip_boost:
            vip_context = "\n\nIMPORTANT: This message is from a VIP contact. Prioritize higher if content warrants attention."

        # Build thread context
        thread_context = ""
        if payload.thread_context_summary:
            thread_context = f"\n\n{payload.thread_context_summary}"

        # Build DM conversation context
        dm_context = ""
        if payload.dm_conversation_context:
            dm_context = f"\n\n{payload.dm_conversation_context}"

        # Build few-shot examples from learned corrections
        few_shot_context = ""
        if payload.few_shot_examples:
            examples_text = []
            for ex in payload.few_shot_examples[:3]:
                reason_text = f" (User said: {ex.feedback_reason})" if ex.feedback_reason else ""
                examples_text.append(
                    f'- Similar message: "{ex.original_abstract}" → {ex.correct_action}{reason_text}'
                )
            few_shot_context = "\n\n**Similar past corrections** (learn from these):\n" + "\n".join(examples_text)

        # Build sender distribution context
        sender_dist_context = ""
        if payload.sender_action_distribution:
            dist = payload.sender_action_distribution
            if dist.get("sample_count", 0) >= 2:
                sender_dist_context = f"\n\n**Sender's past messages in this channel** typically classified as: {dist}"

        # Build topic bias context
        topic_bias_context = ""
        if payload.topic_biases:
            positive_topics = [t for t in payload.topic_biases if t.get("weight", 0) > 0.1]
            if positive_topics:
                topic_bias_context = f"\n\n**Topics you care about**: {', '.join(t['keyword'] for t in positive_topics[:5])}"

        system_prompt = f"""You are a message triage classifier. Classify a Slack message into one of the following ACTIONS.

Actions (what Alfred should DO with this message):
- notify_now: {self.notify_now_definition}
- summarize_next: {self.summarize_next_definition}
- summarize_eod: {self.summarize_eod_definition}
- ignore: {self.ignore_definition}

**Display Layer:** Users see P0/P1/P2/P3 in the UI where:
- P0 = notify_now
- P1 = summarize_next
- P2 = summarize_eod
- P3 = ignore

Do NOT use "review" as an action - instead set review=true if confidence is low.

DMs and @mentions raise the likelihood a message is notify_now or summarize_next — but still evaluate the actual message content before classifying.

**How to use conversation context:**
When provided with thread or DM conversation context (previous messages), use it to understand:
1. Is this part of an active, ongoing conversation? (messages within hours, same topic)
2. Is this a new/stale conversation? (messages days apart, different topics)
3. Does the context clarify the current message's urgency or topic?

DO NOT summarize all previous messages. ONLY use context that is directly relevant to understanding the current message's priority. If previous messages are stale or unrelated, ignore them.

**Examples:**
- Active thread with urgent topic → Context matters, may increase priority
- DM from 3 days ago, new unrelated message today → Ignore old context
- Conversation with ongoing issue → Context shows escalation, may increase priority

Sensitivity: {self.sensitivity}
{sensitivity_guidance.get(self.sensitivity, sensitivity_guidance["medium"])}
{vip_context}{thread_context}{dm_context}{few_shot_context}{sender_dist_context}{topic_bias_context}

Context:
- Message type: {path}
- Sender: {payload.sender_name or payload.sender_slack_id}
- Channel: {payload.channel_name or "DM"}
- Channel priority: {payload.channel_priority}
- Sender is VIP: {payload.is_vip}
- Thread reply: {bool(payload.thread_ts)}

Respond with valid JSON only:
{{"action": "notify_now|summarize_next|summarize_eod|ignore", "confidence": 0.0-1.0, "review": true|false, "reason": "brief explanation", "abstract": "1-sentence summary of the message topic without quoting the message"}}

IMPORTANT: The "abstract" must be a brief topic summary of the CURRENT message only. Do NOT reproduce the original message text."""

        if self.custom_classification_rules:
            system_prompt += f"""

User-defined classification rules (follow these):
{self.custom_classification_rules}"""

        # Add channel-specific triage instructions
        if payload.channel_triage_instructions:
            system_prompt += f"""

Channel-specific triage instructions (follow these):
{payload.channel_triage_instructions}"""

        user_prompt = f"Classify this message:\n\n{payload.message_text}"

        try:
            response = await provider.generate(
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ],
                temperature=0.1,
                max_tokens=8192,
            )

            result = _parse_json_response(response)
            action = result.get("action", "")
            if action not in ("notify_now", "summarize_next", "summarize_eod", "ignore"):
                old_priority = result.get("priority", "")
                priority_to_action = {
                    "p0": "notify_now",
                    "p1": "summarize_next",
                    "p2": "summarize_eod",
                    "p3": "ignore",
                    "review": "notify_now",
                }
                action = priority_to_action.get(old_priority, "summarize_eod")

            review_flag = result.get("review", False)
            if result.get("confidence"):
                conf = float(result.get("confidence", 0.5))
                if conf < 0.6:
                    review_flag = True

            reasoning_signals = ReasoningSignals(
                few_shot_examples=payload.few_shot_examples,
                sender_distribution=payload.sender_action_distribution,
                topic_bias=payload.topic_biases,
                vip_sender=payload.is_vip,
                confidence_threshold_met=conf >= 0.6 if result.get("confidence") else True,
            )

            return ClassificationResult(
                action=action,
                confidence=min(1.0, max(0.0, float(result.get("confidence", 0.5)))),
                reason=result.get("reason", "LLM classification"),
                abstract=result.get("abstract", "Message classified by AI"),
                review=review_flag,
                reasoning_signals=reasoning_signals,
            )

        except Exception:
            logger.exception(
                "LLM classification failed (raw response: %r), defaulting to summarize_eod",
                response if "response" in dir() else "N/A",
            )
            reasoning_signals = ReasoningSignals(
                few_shot_examples=payload.few_shot_examples,
                sender_distribution=payload.sender_action_distribution,
                topic_bias=payload.topic_biases,
                vip_sender=payload.is_vip,
                confidence_threshold_met=False,
            )
            return ClassificationResult(
                action="summarize_eod",
                confidence=0.3,
                reason="LLM classification failed, defaulting to summarize_eod",
                abstract="Message pending review (classification error)",
                review=True,
                reasoning_signals=reasoning_signals,
            )

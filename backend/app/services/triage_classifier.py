"""Triage classifier — LLM-based message classification."""

import json
import logging
import re
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.llm import LLMMessage, get_llm_provider
from app.services.triage_enrichment import EnrichedTriagePayload

logger = logging.getLogger(__name__)

# Default priority level definitions
DEFAULT_P0 = (
    "Needs immediate attention RIGHT NOW. Production incidents, emergencies, "
    "someone explicitly saying something is urgent/critical. Casual requests "
    "or favors (e.g. borrowing something, quick questions) are NOT P0."
)
DEFAULT_P1 = (
    "Time-sensitive requests that need action soon. Direct asks requiring a response, "
    "important questions needing input, meaningful requests with a deadline."
)
DEFAULT_P2 = (
    "Noteworthy but not time-sensitive. Project updates, FYI items, relevant "
    "discussions, informational messages worth reviewing later."
)
DEFAULT_P3 = (
    "Low priority. General chatter, memes, social messages, non-work banter, "
    "automated notifications that need no action. When in doubt between P2 and P3, "
    "lean toward P3."
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
    """Best-effort field extraction from truncated JSON.

    When thinking models (e.g. gemini-2.5-flash) exhaust their token budget,
    the JSON response may be cut off mid-field.  We can still salvage the
    classification if priority and confidence were emitted before truncation.
    """
    priority_m = re.search(r'"priority"\s*:\s*"(\w+)"', text)
    if not priority_m:
        return None
    confidence_m = re.search(r'"confidence"\s*:\s*([\d.]+)', text)
    reason_m = re.search(r'"reason"\s*:\s*"((?:[^"\\]|\\.)*)"?', text, re.DOTALL)
    abstract_m = re.search(r'"abstract"\s*:\s*"((?:[^"\\]|\\.)*)"?', text, re.DOTALL)
    return {
        "priority": priority_m.group(1),
        "confidence": float(confidence_m.group(1)) if confidence_m else 0.5,
        "reason": reason_m.group(1) if reason_m else "LLM classification (truncated response)",
        "abstract": abstract_m.group(1) if abstract_m else "Message classified by AI",
    }


@dataclass
class ClassificationResult:
    """Result of classifying a message."""

    priority: str  # p0 | p1 | p2 | p3 | review
    confidence: float
    reason: str
    abstract: str  # brief summary, never raw message text
    keyword_matches: list[str] = field(default_factory=list)


class TriageClassifier:
    """Classifies messages into priority levels."""

    def __init__(
        self,
        sensitivity: str = "medium",
        custom_classification_rules: str | None = None,
        p0_definition: str | None = None,
        p1_definition: str | None = None,
        p2_definition: str | None = None,
        p3_definition: str | None = None,
    ) -> None:
        self.sensitivity = sensitivity
        self.custom_classification_rules = custom_classification_rules
        self.p0_definition = p0_definition or DEFAULT_P0
        self.p1_definition = p1_definition or DEFAULT_P1
        self.p2_definition = p2_definition or DEFAULT_P2
        self.p3_definition = p3_definition or DEFAULT_P3

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
        """
        # VIP status is passed to LLM as context, not auto-P0
        return await self._llm_classify(payload, path="dm", vip_boost=payload.is_vip)

    async def _classify_channel(
        self, payload: EnrichedTriagePayload
    ) -> ClassificationResult:
        """Classify a channel message."""
        # Check keyword rules before LLM
        keyword_result = self._check_keyword_rules(
            payload.message_text, payload.keyword_rules
        )
        if keyword_result:
            return keyword_result

        # Critical channel priority auto-escalates
        if payload.channel_priority == "critical":
            return ClassificationResult(
                priority="p0",
                confidence=0.9,
                reason=f"Channel #{payload.channel_name} is set to critical priority",
                abstract=f"Message in critical channel #{payload.channel_name}",
            )

        return await self._llm_classify(payload, path="channel")

    def _check_keyword_rules(
        self, text: str, rules: list
    ) -> ClassificationResult | None:
        """Pre-LLM keyword matching. Returns result if any rule matches."""
        if not rules or not text:
            return None

        text_lower = text.lower()
        matched_keywords = []

        for rule in rules:
            pattern = rule.keyword_pattern.lower()
            if rule.match_type == "exact":
                # Word-boundary match
                words = text_lower.split()
                if pattern in words:
                    matched_keywords.append(rule.keyword_pattern)
                    if rule.priority_override:
                        return ClassificationResult(
                            priority=rule.priority_override,
                            confidence=1.0,
                            reason=f"Keyword match: '{rule.keyword_pattern}' (exact)",
                            abstract=f"Message contains keyword '{rule.keyword_pattern}'",
                            keyword_matches=[rule.keyword_pattern],
                        )
            elif rule.match_type == "contains":
                if pattern in text_lower:
                    matched_keywords.append(rule.keyword_pattern)
                    if rule.priority_override:
                        return ClassificationResult(
                            priority=rule.priority_override,
                            confidence=1.0,
                            reason=f"Keyword match: '{rule.keyword_pattern}' (contains)",
                            abstract=f"Message contains keyword '{rule.keyword_pattern}'",
                            keyword_matches=[rule.keyword_pattern],
                        )

        return None

    async def _llm_classify(
        self, payload: EnrichedTriagePayload, path: str, vip_boost: bool = False
    ) -> ClassificationResult:
        """Use LLM to classify the message."""
        settings = get_settings()
        location = settings.triage_vertex_location or None
        provider = get_llm_provider(settings.triage_classification_model, location=location)

        sensitivity_guidance = {
            "low": "Only classify as P0 if there is a genuine emergency or the sender explicitly says it's urgent.",
            "medium": "Classify as P0 if the message appears to need immediate attention. Use P1 for time-sensitive requests.",
            "high": "Be liberal with P0/P1 classification. Any message that could be important should be marked P0 or P1.",
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

        system_prompt = f"""You are a message triage classifier. Classify a Slack message into one of the following priority levels.

Priority levels:
- p0: {self.p0_definition}
- p1: {self.p1_definition}
- p2: {self.p2_definition}
- p3: {self.p3_definition}
- review: ONLY use when you genuinely cannot decide between the other levels. This flags the message for manual review.

DMs and @mentions raise the likelihood a message is P0 or P1 — but still evaluate the actual message content before classifying.

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
{sensitivity_guidance.get(self.sensitivity, sensitivity_guidance['medium'])}
{vip_context}{thread_context}{dm_context}

Context:
- Message type: {path}
- Sender: {payload.sender_name or payload.sender_slack_id}
- Channel: {payload.channel_name or 'DM'}
- Channel priority: {payload.channel_priority}
- Sender is VIP: {payload.is_vip}
- Thread reply: {bool(payload.thread_ts)}

Respond with valid JSON only:
{{"priority": "p0|p1|p2|p3|review", "confidence": 0.0-1.0, "reason": "brief explanation", "abstract": "1-sentence summary of the message topic without quoting the message"}}

IMPORTANT: The "abstract" must be a brief topic summary of the CURRENT message only. Do NOT reproduce the original message text."""

        if self.custom_classification_rules:
            system_prompt += f"""

User-defined classification rules (follow these):
{self.custom_classification_rules}"""

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
            priority = result.get("priority", "review")
            if priority not in ("p0", "p1", "p2", "p3", "review"):
                priority = "review"

            return ClassificationResult(
                priority=priority,
                confidence=min(1.0, max(0.0, float(result.get("confidence", 0.5)))),
                reason=result.get("reason", "LLM classification"),
                abstract=result.get("abstract", "Message classified by AI"),
            )

        except Exception:
            logger.exception("LLM classification failed (raw response: %r), defaulting to review", response if 'response' in dir() else 'N/A')
            return ClassificationResult(
                priority="review",
                confidence=0.3,
                reason="LLM classification failed, defaulting to review",
                abstract="Message pending review (classification error)",
            )

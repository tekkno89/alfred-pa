"""Triage classifier — LLM-based message classification."""

import json
import logging
import re
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.llm import LLMMessage, get_llm_provider
from app.services.triage_enrichment import EnrichedTriagePayload

logger = logging.getLogger(__name__)


def _parse_json_response(response: str) -> dict:
    """Extract and parse JSON from an LLM response.

    Handles markdown code fences, single quotes, and extra text around JSON.
    """
    text = response.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
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
    raise json.JSONDecodeError("No JSON object found in response", text, 0)


@dataclass
class ClassificationResult:
    """Result of classifying a message."""

    urgency: str  # urgent | digest | noise | review
    confidence: float
    reason: str
    abstract: str  # brief summary, never raw message text
    keyword_matches: list[str] = field(default_factory=list)


class TriageClassifier:
    """Classifies messages into urgency levels."""

    def __init__(
        self, sensitivity: str = "medium", custom_classification_rules: str | None = None
    ) -> None:
        self.sensitivity = sensitivity
        self.custom_classification_rules = custom_classification_rules

    async def classify(self, payload: EnrichedTriagePayload) -> ClassificationResult:
        """Classify a message based on enriched context."""
        if payload.event_type == "dm":
            return await self._classify_dm(payload)
        return await self._classify_channel(payload)

    async def _classify_dm(
        self, payload: EnrichedTriagePayload
    ) -> ClassificationResult:
        """Classify a DM."""
        # VIP senders are always urgent
        if payload.is_vip:
            return ClassificationResult(
                urgency="urgent",
                confidence=1.0,
                reason="Sender is on VIP list",
                abstract=f"DM from VIP {payload.sender_name or payload.sender_slack_id}",
            )

        return await self._llm_classify(payload, path="dm")

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
                urgency="urgent",
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
                    if rule.urgency_override:
                        return ClassificationResult(
                            urgency=rule.urgency_override,
                            confidence=1.0,
                            reason=f"Keyword match: '{rule.keyword_pattern}' (exact)",
                            abstract=f"Message contains keyword '{rule.keyword_pattern}'",
                            keyword_matches=[rule.keyword_pattern],
                        )
            elif rule.match_type == "contains":
                if pattern in text_lower:
                    matched_keywords.append(rule.keyword_pattern)
                    if rule.urgency_override:
                        return ClassificationResult(
                            urgency=rule.urgency_override,
                            confidence=1.0,
                            reason=f"Keyword match: '{rule.keyword_pattern}' (contains)",
                            abstract=f"Message contains keyword '{rule.keyword_pattern}'",
                            keyword_matches=[rule.keyword_pattern],
                        )

        return None

    async def _llm_classify(
        self, payload: EnrichedTriagePayload, path: str
    ) -> ClassificationResult:
        """Use LLM to classify the message."""
        settings = get_settings()
        location = settings.triage_vertex_location or None
        provider = get_llm_provider(settings.triage_classification_model, location=location)

        sensitivity_guidance = {
            "low": "Only classify as urgent if there is a genuine emergency or the sender explicitly says it's urgent.",
            "medium": "Classify as urgent if the message appears time-sensitive or requires immediate attention.",
            "high": "Be liberal with urgent classification. Any message that could be important should be marked urgent.",
        }

        system_prompt = f"""You are a message triage classifier. Classify a Slack message into one of the following levels.

Classification levels:
- urgent: Needs immediate attention RIGHT NOW. Production incidents, emergencies, someone explicitly saying something is urgent/critical. Casual requests or favors (e.g. borrowing something, quick questions) are NOT urgent.
- digest: Noteworthy work-related messages the user should review after their focus session. Questions needing their input, meaningful requests, project discussions, important updates. Only include messages that are genuinely worth the user's attention — be selective.
- noise: Not noteworthy. Memes, casual chatter, social messages, non-work banter, automated notifications that need no action. When in doubt between digest and noise, lean toward noise.
- review: ONLY use when you genuinely cannot decide between the other levels. This flags the message for manual review.

DMs and @mentions raise the likelihood a message is urgent — but still evaluate the actual message content for urgency signals before classifying as urgent.

Sensitivity: {self.sensitivity}
{sensitivity_guidance.get(self.sensitivity, sensitivity_guidance['medium'])}

Context:
- Message type: {path}
- Sender: {payload.sender_name or payload.sender_slack_id}
- Channel: {payload.channel_name or 'DM'}
- Channel priority: {payload.channel_priority}
- Sender is VIP: {payload.is_vip}
- Thread reply: {bool(payload.thread_ts)}

Respond with valid JSON only:
{{"urgency": "urgent|digest|noise|review", "confidence": 0.0-1.0, "reason": "brief explanation", "abstract": "1-sentence summary of the message topic without quoting the message"}}

IMPORTANT: The "abstract" must be a brief topic summary. Do NOT reproduce the original message text."""

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
                max_tokens=1024,
            )

            result = _parse_json_response(response)
            urgency = result.get("urgency", "review")
            if urgency not in ("urgent", "digest", "noise", "review"):
                urgency = "review"

            return ClassificationResult(
                urgency=urgency,
                confidence=min(1.0, max(0.0, float(result.get("confidence", 0.5)))),
                reason=result.get("reason", "LLM classification"),
                abstract=result.get("abstract", "Message classified by AI"),
            )

        except Exception:
            logger.exception("LLM classification failed (raw response: %r), defaulting to review", response if 'response' in dir() else 'N/A')
            return ClassificationResult(
                urgency="review",
                confidence=0.3,
                reason="LLM classification failed, defaulting to review",
                abstract="Message pending review (classification error)",
            )

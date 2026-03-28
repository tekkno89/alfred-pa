"""Triage wizard — AI-powered priority definition generator."""

import json
import logging

from app.core.config import get_settings
from app.core.llm import LLMMessage, get_llm_provider
from app.services.triage_classifier import DEFAULT_P0, DEFAULT_P1, DEFAULT_P2, DEFAULT_P3

logger = logging.getLogger(__name__)


class TriageWizardService:
    """Generates personalized priority definitions via LLM."""

    async def generate_definitions(
        self,
        role: str,
        critical_messages: str,
        can_wait: str,
        priority_senders: str = "",
    ) -> dict[str, str]:
        """Generate P0-P3 definitions based on user answers.

        Returns dict with keys: p0_definition, p1_definition, p2_definition, p3_definition.
        """
        settings = get_settings()
        location = settings.triage_vertex_location or None
        provider = get_llm_provider(
            settings.triage_classification_model, location=location
        )

        system_prompt = """You are an AI assistant helping a user customize their Slack message triage system.

Based on their answers about their role and communication priorities, generate four priority level definitions that will be used by an AI classifier to sort incoming Slack messages.

Each definition should be 1-3 sentences, written as instructions for the classifier. Be specific to the user's context.

Priority levels:
- P0: Immediate attention required — the user gets notified right away, even during focus time
- P1: Important and time-sensitive — delivered in the next digest/break
- P2: Noteworthy but can wait — included in session digest
- P3: Low priority — stored but no notification

Respond with valid JSON only:
{"p0_definition": "...", "p1_definition": "...", "p2_definition": "...", "p3_definition": "..."}"""

        user_prompt = f"""Here are the user's answers:

Role: {role}

What messages are critical and need immediate attention?
{critical_messages}

What messages can safely wait?
{can_wait}"""

        if priority_senders.strip():
            user_prompt += f"""

High-priority senders or channels:
{priority_senders}"""

        try:
            response = await provider.generate(
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=user_prompt),
                ],
                temperature=0.3,
                max_tokens=2048,
            )

            from app.services.triage_classifier import _parse_json_response

            result = _parse_json_response(response)

            return {
                "p0_definition": result.get("p0_definition", DEFAULT_P0),
                "p1_definition": result.get("p1_definition", DEFAULT_P1),
                "p2_definition": result.get("p2_definition", DEFAULT_P2),
                "p3_definition": result.get("p3_definition", DEFAULT_P3),
            }
        except Exception:
            logger.exception("Wizard definition generation failed")
            return {
                "p0_definition": DEFAULT_P0,
                "p1_definition": DEFAULT_P1,
                "p2_definition": DEFAULT_P2,
                "p3_definition": DEFAULT_P3,
            }

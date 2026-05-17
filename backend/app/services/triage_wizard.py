"""Triage wizard — AI-powered priority definition generator."""

import logging

from app.core.config import get_settings
from app.core.llm import LLMMessage, get_llm_provider
from app.services.triage_classifier import (
    DEFAULT_IGNORE,
    DEFAULT_NOTIFY_NOW,
    DEFAULT_SUMMARIZE_EOD,
    DEFAULT_SUMMARIZE_NEXT,
)

logger = logging.getLogger(__name__)

ROLE_STARTER_TYPES: dict[str, list[tuple[str, str]]] = {
    "engineering": [
        ("pr_review_request", "Pull request review requests requiring your input"),
        ("incident_alert", "Production incidents or alerts requiring immediate attention"),
        ("deploy_notification", "Deployment notifications and status updates"),
        ("bug_report", "Bug reports and issues requiring investigation"),
    ],
    "sales": [
        ("deal_update", "Updates on active deals and opportunities"),
        ("customer_escalation", "Customer issues requiring urgent response"),
        ("meeting_request", "Meeting requests from prospects or customers"),
        ("contract_review", "Contract review requests"),
    ],
    "management": [
        ("team_update", "Team updates and status reports"),
        ("decision_needed", "Decisions requiring your approval"),
        ("escalation", "Issues escalated to you for resolution"),
        ("calendar_conflict", "Calendar conflicts and scheduling issues"),
    ],
    "design": [
        ("design_review", "Design review requests and feedback"),
        ("design_critique", "Design critiques and iteration requests"),
        ("brand_request", "Brand asset or design requests"),
    ],
    "product": [
        ("feature_request", "Feature requests and product feedback"),
        ("roadmap_update", "Roadmap updates and changes"),
        ("bug_report", "Bug reports and issues"),
        ("release_notes", "Release notes and announcements"),
    ],
    "operations": [
        ("system_alert", "System alerts and notifications"),
        ("process_request", "Process improvement requests"),
        ("vendor_update", "Vendor and partner updates"),
    ],
}


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
- P2: Notable messages — included in session digest
- P3: Low priority — included in daily digest

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
                "p0_definition": result.get("p0_definition", DEFAULT_NOTIFY_NOW),
                "p1_definition": result.get("p1_definition", DEFAULT_SUMMARIZE_NEXT),
                "p2_definition": result.get("p2_definition", DEFAULT_SUMMARIZE_EOD),
                "p3_definition": result.get("p3_definition", DEFAULT_IGNORE),
            }
        except Exception:
            logger.exception("Wizard definition generation failed")
            return {
                "p0_definition": DEFAULT_NOTIFY_NOW,
                "p1_definition": DEFAULT_SUMMARIZE_NEXT,
                "p2_definition": DEFAULT_SUMMARIZE_EOD,
                "p3_definition": DEFAULT_IGNORE,
            }

    async def generate_definitions_from_calibration(
        self,
        role: str,
        critical_messages: str,
        can_wait: str,
        priority_senders: str,
        ratings: list[dict],
    ) -> dict[str, str]:
        """Generate P0-P3 definitions based on calibration ratings.

        Args:
            role: User's role
            critical_messages: What they consider critical
            can_wait: What can wait
            priority_senders: High-priority senders/channels
            ratings: List of calibration ratings with message_text, priority, and optional explanation

        Returns:
            Dict with p0_definition, p1_definition, p2_definition, p3_definition
        """
        settings = get_settings()
        location = settings.triage_vertex_location or None
        provider = get_llm_provider(
            settings.triage_classification_model, location=location
        )

        # Format calibration examples
        examples_by_priority = {"p0": [], "p1": [], "p2": [], "p3": []}

        for rating in ratings:
            priority = rating.get("priority", "p3")
            message_text = rating.get("message_text", "")
            explanation = rating.get("explanation", "")
            sender = rating.get("sender_name", "Someone")
            channel = rating.get("channel_name", "a channel")

            example = f"- From {sender} in #{channel}: \"{message_text[:100]}\""
            if explanation:
                example += f" — {explanation}"

            examples_by_priority[priority].append(example)

        # Build examples section
        examples_text = ""
        for priority in ["p0", "p1", "p2", "p3"]:
            if examples_by_priority[priority]:
                examples_text += f"\n{priority.upper()} examples:\n"
                examples_text += "\n".join(examples_by_priority[priority][:3])
                examples_text += "\n"

        system_prompt = f"""You are an AI assistant helping a user customize their Slack message triage system.

Based on their answers about their role, communication priorities, AND their actual calibration examples, generate four priority level definitions that will be used by an AI classifier to sort incoming Slack messages.

Each definition should be 1-3 sentences, written as instructions for the classifier. Be specific to the user's context and the patterns you see in their calibration examples.

Priority levels:
- P0: Immediate attention required — the user gets notified right away, even during focus time
- P1: Important and time-sensitive — delivered in the next digest/break
- P2: Notable messages — included in summary digests
- P3: Low priority — included in daily digest

Learn from the calibration examples the user provided. Identify patterns in what they rated as each priority level.

Respond with valid JSON only:
{{"p0_definition": "...", "p1_definition": "...", "p2_definition": "...", "p3_definition": "..."}}"""

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

        if examples_text:
            user_prompt += f"""

Here are some actual messages the user rated (use these to learn their preferences):
{examples_text}"""

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
                "p0_definition": result.get("p0_definition", DEFAULT_NOTIFY_NOW),
                "p1_definition": result.get("p1_definition", DEFAULT_SUMMARIZE_NEXT),
                "p2_definition": result.get("p2_definition", DEFAULT_SUMMARIZE_EOD),
                "p3_definition": result.get("p3_definition", DEFAULT_IGNORE),
            }
        except Exception:
            logger.exception("Wizard calibration generation failed")
            return {
                "p0_definition": DEFAULT_NOTIFY_NOW,
                "p1_definition": DEFAULT_SUMMARIZE_NEXT,
                "p2_definition": DEFAULT_SUMMARIZE_EOD,
                "p3_definition": DEFAULT_IGNORE,
            }

    async def generate_wizard_types(
        self,
        roles: list[str],
    ) -> list[dict]:
        """Generate starter types based on selected roles.

        Args:
            roles: List of role names (engineering, sales, etc.)

        Returns:
            List of type definitions to create
        """
        types = []
        seen_names = set()

        for role in roles:
            role_types = ROLE_STARTER_TYPES.get(role, [])
            for type_name, definition in role_types:
                if type_name not in seen_names:
                    types.append({
                        "type_name": type_name,
                        "type_definition": definition,
                        "source": "wizard",
                    })
                    seen_names.add(type_name)

        return types

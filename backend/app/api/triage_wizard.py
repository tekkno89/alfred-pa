"""Triage Setup Wizard API endpoints."""

import json
import re

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.core.llm import LLMMessage, get_llm_provider
from app.schemas.triage import (
    FetchedMessage,
    FetchMessagesRequest,
    FetchMessagesResponse,
    MessageTypeSuggestion,
    WizardDefinitionRequest,
    WizardDefinitionResponse,
    WizardQuestionResponse,
    WizardRoleRequest,
)

router = APIRouter(prefix="/triage/wizard", tags=["triage-wizard"])


@router.post("/generate-questions", response_model=WizardQuestionResponse)
async def generate_questions(
    data: WizardRoleRequest,
    current_user: CurrentUser = None,
) -> WizardQuestionResponse:
    """Generate dynamic questions based on user role and goals."""
    llm = get_llm_provider()

    goals_text = ", ".join(data.goals) if data.goals else "general productivity"

    prompt = f"""You are helping set up a Slack triage assistant for a {data.role}.

Their goals are: {goals_text}

Generate 4-5 multiple-choice questions that will help define how to prioritize messages.

Each question should:
1. Be relevant to their role
2. Have 2-4 clear options
3. Map to a priority level (P0-P3)

Return JSON only:
{{
  "questions": [
    {{
      "question": "When a production incident is reported, how should you be notified?",
      "options": ["Immediately (P0 - Immediate)", "In next digest (P1 - Soon)", "End of day (P2 - Later)"],
      "context": "incident_handling"
    }},
    ...
  ]
}}"""

    response = await llm.generate(
        [LLMMessage(role="user", content=prompt)],
        temperature=0.7,
        max_tokens=2048,
    )
    content = response.strip()

    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\n?", "", content)
        content = re.sub(r"\n?```$", "", content)

    try:
        result = json.loads(content)
        return WizardQuestionResponse(**result)
    except json.JSONDecodeError:
        return WizardQuestionResponse(questions=[])


@router.post("/generate-definitions", response_model=WizardDefinitionResponse)
async def generate_definitions(
    data: WizardDefinitionRequest,
    current_user: CurrentUser = None,
) -> WizardDefinitionResponse:
    """Generate priority definitions from user responses."""
    llm = get_llm_provider()

    responses_text = "\n".join(
        f"- {k}: {v}" for k, v in data.question_responses.items()
    )

    types_text = ""
    if data.message_types:
        types_text = "\n\nMessage types defined:\n" + "\n".join(
            f"- {t['type_name']}: {t['type_definition']}"
            for t in data.message_types
        )

    examples_text = ""
    if data.example_messages:
        examples_text = "\n\nExample messages:\n" + "\n".join(
            f"- \"{e.get('text', '')[:50]}...\" → {e.get('priority', '')}"
            for e in data.example_messages[:5]
        )

    prompt = f"""Based on the user's role ({data.role}), goals ({', '.join(data.goals)}), and their responses:

{responses_text}
{types_text}
{examples_text}

Generate concise P0-P3 priority definitions for triaging Slack messages.

Also suggest 3-5 message types relevant to their role.

Return JSON only:
{{
  "p0_definition": "Production incidents, critical bugs, urgent mentions...",
  "p1_definition": "Code reviews, time-sensitive requests...",
  "p2_definition": "Noteworthy updates, FYI messages...",
  "p3_definition": "Low priority items, newsletters...",
  "suggested_message_types": [
    {{"type_name": "Incidents", "type_definition": "Production issues and outages", "confidence": 0.9}},
    ...
  ]
}}"""

    response = await llm.generate(
        [LLMMessage(role="user", content=prompt)],
        temperature=0.7,
        max_tokens=2048,
    )
    content = response.strip()

    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\n?", "", content)
        content = re.sub(r"\n?```$", "", content)

    try:
        result = json.loads(content)
        return WizardDefinitionResponse(
            p0_definition=result.get("p0_definition", ""),
            p1_definition=result.get("p1_definition", ""),
            p2_definition=result.get("p2_definition", ""),
            p3_definition=result.get("p3_definition", ""),
            suggested_message_types=[
                MessageTypeSuggestion(**t) for t in result.get("suggested_message_types", [])
            ],
        )
    except (json.JSONDecodeError, TypeError):
        return WizardDefinitionResponse(
            p0_definition="Urgent items requiring immediate attention",
            p1_definition="Important but not urgent items",
            p2_definition="Items to review later",
            p3_definition="Low priority items",
            suggested_message_types=[],
        )


@router.post("/fetch-messages", response_model=FetchMessagesResponse)
async def fetch_messages(
    data: FetchMessagesRequest,
    current_user: CurrentUser = None,
    db: DbSession = None,
) -> FetchMessagesResponse:
    """Fetch Slack messages from permalinks."""
    import logging

    from slack_sdk.web.async_client import AsyncWebClient

    from app.services.slack_user import SlackUserService

    logger = logging.getLogger(__name__)

    slack_user_service = SlackUserService(db)
    token = await slack_user_service.get_raw_token(current_user.id)

    if not token:
        return FetchMessagesResponse(messages=[])

    client = AsyncWebClient(token=token)
    messages = []

    permalink_pattern = re.compile(
        r"https?://[\w-]+\.slack\.com/archives/([A-Z0-9]+)/p(\d+)"
    )

    for link in data.slack_links[:10]:
        match = permalink_pattern.match(link)
        if not match:
            continue

        channel_id = match.group(1)
        timestamp = match.group(2)
        ts = f"{timestamp[:10]}.{timestamp[10:]}"

        try:
            result = await client.conversations_replies(
                channel=channel_id,
                ts=ts,
                limit=1,
            )

            if result["ok"] and result.get("messages"):
                msg = result["messages"][0]
                messages.append(
                    FetchedMessage(
                        slack_link=link,
                        text=msg.get("text", ""),
                        sender_name=msg.get("user", "Unknown"),
                        channel_name=channel_id,
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to fetch message {link}: {e}")
            continue

    return FetchMessagesResponse(messages=messages)

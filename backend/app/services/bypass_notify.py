"""Stubbed notification senders for focus mode bypass alerts."""

import logging

logger = logging.getLogger(__name__)


async def send_bypass_email(email: str, sender_name: str) -> None:
    """Send bypass notification via email.

    Currently stubbed — logs intent without sending.
    """
    logger.info(
        f"Email notification stubbed: would send bypass alert to {email} "
        f"from {sender_name}"
    )


async def send_bypass_sms(phone: str, sender_name: str) -> None:
    """Send bypass notification via SMS.

    Currently stubbed — logs intent without sending.
    """
    logger.info(
        f"SMS notification stubbed: would send bypass alert to {phone} "
        f"from {sender_name}"
    )

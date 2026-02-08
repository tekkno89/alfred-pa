"""Services module for external integrations."""

from app.services.slack import SlackService
from app.services.linking import LinkingService

__all__ = ["SlackService", "LinkingService"]

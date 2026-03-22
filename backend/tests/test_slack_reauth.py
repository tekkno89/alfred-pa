"""Tests for Slack re-authorization scope checking."""

import pytest

from app.api.auth import REQUIRED_SLACK_USER_SCOPES, _check_slack_reauth_required


class TestCheckSlackReauthRequired:
    """Tests for _check_slack_reauth_required helper."""

    def test_null_scope_requires_reauth(self):
        assert _check_slack_reauth_required(None) is True

    def test_empty_scope_requires_reauth(self):
        assert _check_slack_reauth_required("") is True

    def test_complete_scopes_no_reauth(self):
        scope = ",".join(sorted(REQUIRED_SLACK_USER_SCOPES))
        assert _check_slack_reauth_required(scope) is False

    def test_superset_scopes_no_reauth(self):
        scopes = set(REQUIRED_SLACK_USER_SCOPES) | {"extra:scope", "another:scope"}
        scope = ",".join(sorted(scopes))
        assert _check_slack_reauth_required(scope) is False

    def test_missing_one_scope_requires_reauth(self):
        scopes = set(REQUIRED_SLACK_USER_SCOPES)
        scopes.discard("channels:read")
        scope = ",".join(sorted(scopes))
        assert _check_slack_reauth_required(scope) is True

    def test_missing_multiple_scopes_requires_reauth(self):
        scopes = set(REQUIRED_SLACK_USER_SCOPES)
        scopes.discard("channels:read")
        scopes.discard("groups:read")
        scope = ",".join(sorted(scopes))
        assert _check_slack_reauth_required(scope) is True

    def test_completely_different_scopes_requires_reauth(self):
        assert _check_slack_reauth_required("chat:write,files:read") is True

    def test_whitespace_handling(self):
        scope = " , ".join(sorted(REQUIRED_SLACK_USER_SCOPES))
        assert _check_slack_reauth_required(scope) is False


class TestRequiredScopesConstant:
    """Sanity checks for the REQUIRED_SLACK_USER_SCOPES constant."""

    def test_is_frozenset(self):
        assert isinstance(REQUIRED_SLACK_USER_SCOPES, frozenset)

    def test_contains_expected_scopes(self):
        assert "channels:read" in REQUIRED_SLACK_USER_SCOPES
        assert "groups:read" in REQUIRED_SLACK_USER_SCOPES
        assert "dnd:write" in REQUIRED_SLACK_USER_SCOPES

    def test_not_empty(self):
        assert len(REQUIRED_SLACK_USER_SCOPES) > 0

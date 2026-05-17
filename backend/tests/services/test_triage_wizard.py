"""Tests for TriageWizardService."""

import pytest

from app.services.triage_wizard import TriageWizardService, ROLE_STARTER_TYPES


class TestGenerateWizardTypes:
    """Tests for generate_wizard_types method."""

    @pytest.fixture
    def service(self):
        return TriageWizardService()

    async def test_single_role_returns_types(self, service):
        """Single role returns its types."""
        result = await service.generate_wizard_types(
            roles=["engineering"],
        )

        assert len(result) == 4
        assert result[0]["type_name"] == "pr_review_request"
        assert result[0]["source"] == "wizard"

    async def test_multiple_roles_merges_types(self, service):
        """Multiple roles merge their types."""
        result = await service.generate_wizard_types(
            roles=["engineering", "sales"],
        )

        assert len(result) == 8
        type_names = [t["type_name"] for t in result]
        assert "pr_review_request" in type_names
        assert "deal_update" in type_names

    async def test_deduplicates_across_roles(self, service):
        """Duplicate type names are deduplicated."""
        result = await service.generate_wizard_types(
            roles=["engineering", "product"],
        )

        type_names = [t["type_name"] for t in result]
        assert "bug_report" in type_names
        assert type_names.count("bug_report") == 1
        assert len(type_names) == len(set(type_names))

    async def test_empty_roles_returns_empty_list(self, service):
        """Empty roles list returns empty list."""
        result = await service.generate_wizard_types(
            roles=[],
        )

        assert result == []

    async def test_unknown_role_ignored(self, service):
        """Unknown roles are ignored without error."""
        result = await service.generate_wizard_types(
            roles=["unknown_role", "engineering"],
        )

        assert len(result) == 4

    async def test_all_type_definitions_populated(self, service):
        """All returned types have required fields."""
        result = await service.generate_wizard_types(
            roles=["management"],
        )

        for type_def in result:
            assert "type_name" in type_def
            assert "type_definition" in type_def
            assert "source" in type_def
            assert type_def["source"] == "wizard"


class TestRoleStarterTypes:
    """Tests for ROLE_STARTER_TYPES constant."""

    def test_all_roles_have_types(self):
        """All defined roles have at least one type."""
        for role, types in ROLE_STARTER_TYPES.items():
            assert len(types) > 0, f"Role {role} has no types"

    def test_type_tuples_have_two_elements(self):
        """All type definitions are (name, definition) tuples."""
        for role, types in ROLE_STARTER_TYPES.items():
            for type_def in types:
                assert len(type_def) == 2, f"Invalid tuple for {role}: {type_def}"
                assert isinstance(type_def[0], str)
                assert isinstance(type_def[1], str)

    def test_type_names_are_snake_case(self):
        """Type names follow snake_case convention."""
        import re

        for role, types in ROLE_STARTER_TYPES.items():
            for type_name, _ in types:
                assert re.match(
                    r"^[a-z][a-z0-9_]*$", type_name
                ), f"Invalid snake_case: {type_name}"

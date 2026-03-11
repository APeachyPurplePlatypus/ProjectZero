"""Unit tests for PSI ability ID -> name lookup."""

from __future__ import annotations

from src.state_parser.psi_names import PSI_ABILITIES, get_psi_ability, get_psi_name


class TestGetPsiName:
    def test_known_offensive_psi(self):
        assert get_psi_name(1) == "PK Fire a"

    def test_known_healing_psi(self):
        assert get_psi_name(11) == "Healing a"

    def test_known_assist_psi(self):
        assert get_psi_name(23) == "Telepathy"

    def test_empty_slot_returns_none_string(self):
        assert get_psi_name(0) == "(none)"

    def test_unknown_psi_returns_fallback(self):
        result = get_psi_name(999)
        assert result == "PSI #999"

    def test_all_known_ids_return_nonempty_strings(self):
        for psi_id in PSI_ABILITIES:
            name = get_psi_name(psi_id)
            assert isinstance(name, str)
            assert len(name) > 0

    def test_table_has_minimum_entries(self):
        # At least healing, offense, defense, assist categories
        assert len(PSI_ABILITIES) >= 20


class TestGetPsiAbility:
    def test_known_psi_returns_ability(self):
        ability = get_psi_ability(11)
        assert ability is not None
        assert ability.name == "Healing a"
        assert ability.pp_cost == 3
        assert ability.psi_type == "healing"

    def test_offense_psi_has_correct_type(self):
        ability = get_psi_ability(1)
        assert ability is not None
        assert ability.psi_type == "offense"
        assert ability.pp_cost > 0

    def test_zero_cost_psi_exists(self):
        ability = get_psi_ability(23)  # Telepathy
        assert ability is not None
        assert ability.pp_cost == 0

    def test_unknown_returns_none(self):
        assert get_psi_ability(999) is None

    def test_all_abilities_have_valid_types(self):
        valid_types = {"offense", "defense", "healing", "assist", ""}
        for ability in PSI_ABILITIES.values():
            assert ability.psi_type in valid_types

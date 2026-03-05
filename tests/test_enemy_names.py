"""Unit tests for enemy group ID → name lookup."""

from __future__ import annotations

import pytest

from src.state_parser.enemy_names import get_enemy_name, ENEMY_NAMES


class TestGetEnemyName:
    def test_known_enemy_returns_name(self):
        assert get_enemy_name(1) == "Lamp"
        assert get_enemy_name(2) == "Hippie"
        assert get_enemy_name(9) == "Stray Dog"

    def test_unknown_enemy_returns_group_format(self):
        result = get_enemy_name(999)
        assert "999" in result
        assert result == "Enemy Group #999"

    def test_zero_group_id_returns_fallback(self):
        result = get_enemy_name(0)
        assert "0" in result

    def test_all_known_entries_return_strings(self):
        for group_id, name in ENEMY_NAMES.items():
            assert get_enemy_name(group_id) == name
            assert isinstance(name, str)
            assert len(name) > 0

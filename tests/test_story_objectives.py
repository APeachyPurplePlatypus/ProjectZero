"""Unit tests for story objective hints."""

from __future__ import annotations

from src.state_parser.story_objectives import OBJECTIVES, get_current_objective


class TestGetCurrentObjective:
    def test_zero_melodies_default(self):
        hint = get_current_objective(0, 99)  # Unknown map
        assert len(hint) > 0
        assert "Podunk" in hint

    def test_zero_melodies_at_home(self):
        hint = get_current_objective(0, 0)  # Ninten's House
        assert "house" in hint.lower() or "basement" in hint.lower()

    def test_one_melody_default(self):
        hint = get_current_objective(1, 99)
        assert "Merrysville" in hint or "east" in hint.lower()

    def test_all_melodies_collected(self):
        hint = get_current_objective(8, 0)
        assert "Magicant" in hint or "Giygas" in hint

    def test_map_specific_hint_overrides_default(self):
        default = get_current_objective(0, 99)  # Default hint
        specific = get_current_objective(0, 0)  # Map-specific hint
        assert default != specific

    def test_unknown_melody_count_returns_something(self):
        hint = get_current_objective(99, 0)
        assert isinstance(hint, str)
        assert len(hint) > 0

    def test_all_melody_counts_have_defaults(self):
        for m in range(9):
            hint = get_current_objective(m, 999)
            assert isinstance(hint, str)
            assert len(hint) > 0

    def test_mid_game_objective(self):
        hint = get_current_objective(5, 99)
        assert "Ellay" in hint or "Teddy" in hint

    def test_near_end_objective(self):
        hint = get_current_objective(7, 99)
        assert "Mt. Itoi" in hint or "melody" in hint.lower()

"""Unit tests for execute_action input validation."""

from __future__ import annotations

import pytest

from src.mcp_server.validation import MAX_DURATION_FRAMES, validate_action
from src.state_parser.models import GameMode


def valid(errors: list[str]) -> bool:
    return len(errors) == 0


# ---------------------------------------------------------------------------
# action_type validation
# ---------------------------------------------------------------------------

class TestActionType:
    def test_invalid_type_returns_error(self):
        errors = validate_action("fly", GameMode.OVERWORLD)
        assert not valid(errors)
        assert any("action_type" in e for e in errors)

    def test_valid_types_accepted(self):
        for t in ("move", "button", "menu_navigate", "text_advance", "wait"):
            # Provide required fields per type
            if t == "move":
                errors = validate_action(t, GameMode.OVERWORLD, direction="up", duration_frames=5)
            elif t == "button":
                errors = validate_action(t, GameMode.OVERWORLD, button="A")
            elif t == "menu_navigate":
                errors = validate_action(t, GameMode.MENU, menu_path=["BASH"])
            elif t == "text_advance":
                errors = validate_action(t, GameMode.DIALOG)
            else:
                errors = validate_action(t, GameMode.OVERWORLD, duration_frames=10)
            assert valid(errors), f"Expected valid for action_type='{t}', got: {errors}"


# ---------------------------------------------------------------------------
# duration_frames validation
# ---------------------------------------------------------------------------

class TestDurationFrames:
    def test_zero_duration_invalid(self):
        errors = validate_action("wait", GameMode.OVERWORLD, duration_frames=0)
        assert not valid(errors)

    def test_one_frame_valid(self):
        errors = validate_action("wait", GameMode.OVERWORLD, duration_frames=1)
        assert valid(errors)

    def test_max_duration_valid(self):
        errors = validate_action("wait", GameMode.OVERWORLD, duration_frames=MAX_DURATION_FRAMES)
        assert valid(errors)

    def test_over_max_invalid(self):
        errors = validate_action("wait", GameMode.OVERWORLD, duration_frames=MAX_DURATION_FRAMES + 1)
        assert not valid(errors)
        assert any(str(MAX_DURATION_FRAMES) in e for e in errors)


# ---------------------------------------------------------------------------
# move validation
# ---------------------------------------------------------------------------

class TestMoveAction:
    def test_move_in_overworld_valid(self):
        errors = validate_action("move", GameMode.OVERWORLD, direction="up", duration_frames=10)
        assert valid(errors)

    def test_move_in_battle_invalid(self):
        errors = validate_action("move", GameMode.BATTLE, direction="left", duration_frames=10)
        assert not valid(errors)
        assert any("battle" in e.lower() for e in errors)

    def test_move_without_direction_invalid(self):
        errors = validate_action("move", GameMode.OVERWORLD, duration_frames=5)
        assert not valid(errors)
        assert any("direction" in e for e in errors)

    def test_move_invalid_direction(self):
        errors = validate_action("move", GameMode.OVERWORLD, direction="diagonal", duration_frames=5)
        assert not valid(errors)
        assert any("diagonal" in e for e in errors)

    def test_all_valid_directions(self):
        for d in ("up", "down", "left", "right"):
            errors = validate_action("move", GameMode.OVERWORLD, direction=d, duration_frames=5)
            assert valid(errors), f"Expected valid for direction='{d}', got: {errors}"


# ---------------------------------------------------------------------------
# button validation
# ---------------------------------------------------------------------------

class TestButtonAction:
    def test_valid_buttons(self):
        for b in ("A", "B", "Start", "Select"):
            errors = validate_action("button", GameMode.OVERWORLD, button=b)
            assert valid(errors), f"Expected valid for button='{b}', got: {errors}"

    def test_missing_button_invalid(self):
        errors = validate_action("button", GameMode.OVERWORLD)
        assert not valid(errors)
        assert any("button" in e for e in errors)

    def test_invalid_button_name(self):
        errors = validate_action("button", GameMode.OVERWORLD, button="X")
        assert not valid(errors)
        assert any("X" in e for e in errors)


# ---------------------------------------------------------------------------
# menu_navigate validation
# ---------------------------------------------------------------------------

class TestMenuNavigate:
    def test_valid_in_menu_mode(self):
        errors = validate_action("menu_navigate", GameMode.MENU, menu_path=["GOODS", "Bread"])
        assert valid(errors)

    def test_valid_in_battle_mode(self):
        errors = validate_action("menu_navigate", GameMode.BATTLE, menu_path=["BASH"])
        assert valid(errors)

    def test_invalid_in_overworld(self):
        errors = validate_action("menu_navigate", GameMode.OVERWORLD, menu_path=["GOODS"])
        assert not valid(errors)
        assert any("overworld" in e.lower() for e in errors)

    def test_empty_menu_path_invalid(self):
        errors = validate_action("menu_navigate", GameMode.MENU, menu_path=[])
        assert not valid(errors)

    def test_none_menu_path_invalid(self):
        errors = validate_action("menu_navigate", GameMode.MENU)
        assert not valid(errors)


# ---------------------------------------------------------------------------
# text_advance validation
# ---------------------------------------------------------------------------

class TestTextAdvance:
    def test_valid_in_dialog(self):
        errors = validate_action("text_advance", GameMode.DIALOG)
        assert valid(errors)

    def test_valid_in_battle(self):
        errors = validate_action("text_advance", GameMode.BATTLE)
        assert valid(errors)

    def test_invalid_in_overworld(self):
        errors = validate_action("text_advance", GameMode.OVERWORLD)
        assert not valid(errors)

    def test_invalid_in_menu(self):
        errors = validate_action("text_advance", GameMode.MENU)
        assert not valid(errors)


# ---------------------------------------------------------------------------
# wait validation
# ---------------------------------------------------------------------------

class TestWaitAction:
    def test_wait_valid_in_any_mode(self):
        for mode in GameMode:
            errors = validate_action("wait", mode, duration_frames=10)
            assert valid(errors), f"Expected valid wait in {mode}, got: {errors}"

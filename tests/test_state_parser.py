"""Unit tests for GameStateParser, decode_status, and detect_game_mode."""

from __future__ import annotations

import pytest

from src.bridge.emulator_bridge import GameState as RawGameState
from src.state_parser.map_names import get_map_name
from src.state_parser.models import GameMode
from src.state_parser.parser import GameStateParser, decode_status, detect_game_mode


def make_raw(**overrides) -> RawGameState:
    """Create a RawGameState with sensible defaults, overriding specific fields."""
    defaults = dict(
        frame=100,
        map_id=0,
        player_x=10,
        player_y=20,
        player_direction=4,
        movement_state=0x88,
        ninten_hp=50,
        ninten_max_hp=68,
        ninten_pp=20,
        ninten_max_pp=30,
        ninten_level=3,
        ninten_exp=150,
        ninten_status=0,
        combat_active=0,
        enemy_group_id=0,
        menu_state=0,
        dialog_active=0,
    )
    defaults.update(overrides)
    return RawGameState(**defaults)


# ---------------------------------------------------------------------------
# decode_status
# ---------------------------------------------------------------------------

class TestDecodeStatus:
    def test_zero_returns_normal(self):
        assert decode_status(0) == "normal"

    def test_bit_0_cold(self):
        assert decode_status(0b00000001) == "cold"

    def test_bit_1_poisoned(self):
        assert decode_status(0b00000010) == "poisoned"

    def test_bit_4_asleep(self):
        assert decode_status(0b00010000) == "asleep"

    def test_bit_7_unconscious(self):
        assert decode_status(0b10000000) == "unconscious"

    def test_multiple_bits_highest_wins(self):
        # Bits 1 (poisoned) and 4 (asleep) both set — highest (asleep) wins
        assert decode_status(0b00010010) == "asleep"

    def test_all_bits_unconscious_wins(self):
        assert decode_status(0xFF) == "unconscious"


# ---------------------------------------------------------------------------
# detect_game_mode
# ---------------------------------------------------------------------------

class TestDetectGameMode:
    def test_default_is_overworld(self):
        raw = make_raw()
        assert detect_game_mode(raw) == GameMode.OVERWORLD

    def test_combat_active_nonzero_is_battle(self):
        raw = make_raw(combat_active=1)
        assert detect_game_mode(raw) == GameMode.BATTLE

    def test_menu_state_nonzero_is_menu(self):
        raw = make_raw(menu_state=1)
        assert detect_game_mode(raw) == GameMode.MENU

    def test_dialog_active_nonzero_is_dialog(self):
        raw = make_raw(dialog_active=1)
        assert detect_game_mode(raw) == GameMode.DIALOG

    def test_battle_takes_priority_over_menu(self):
        raw = make_raw(combat_active=1, menu_state=1)
        assert detect_game_mode(raw) == GameMode.BATTLE

    def test_battle_takes_priority_over_dialog(self):
        raw = make_raw(combat_active=1, dialog_active=1)
        assert detect_game_mode(raw) == GameMode.BATTLE

    def test_menu_takes_priority_over_dialog(self):
        raw = make_raw(menu_state=1, dialog_active=1)
        assert detect_game_mode(raw) == GameMode.MENU


# ---------------------------------------------------------------------------
# get_map_name
# ---------------------------------------------------------------------------

class TestGetMapName:
    def test_known_id_returns_name(self):
        assert get_map_name(0) == "Ninten's House"

    def test_unknown_id_returns_fallback(self):
        name = get_map_name(999)
        assert "999" in name
        assert "Unknown" in name


# ---------------------------------------------------------------------------
# GameStateParser.build_state
# ---------------------------------------------------------------------------

class TestGameStateParser:
    def setup_method(self):
        self.parser = GameStateParser()

    def test_overworld_state(self):
        raw = make_raw(ninten_hp=50, ninten_max_hp=68, ninten_level=3, map_id=0)
        state = self.parser.build_state(raw)

        assert state.frame == 100
        assert state.game_mode == GameMode.OVERWORLD
        assert state.player.name == "Ninten"
        assert state.player.hp == 50
        assert state.player.max_hp == 68
        assert state.player.level == 3
        assert state.player.status == "normal"
        assert state.location.map_id == 0
        assert state.location.map_name == "Ninten's House"
        assert state.location.x == 10
        assert state.location.y == 20
        assert state.battle_state is None
        assert state.dialog_state is None
        assert state.screenshot_base64 is None

    def test_battle_state_populated(self):
        raw = make_raw(combat_active=1, enemy_group_id=5)
        state = self.parser.build_state(raw)

        assert state.game_mode == GameMode.BATTLE
        assert state.battle_state is not None
        assert "5" in state.battle_state.enemy_name
        assert state.dialog_state is None

    def test_dialog_state_populated(self):
        raw = make_raw(dialog_active=1)
        state = self.parser.build_state(raw)

        assert state.game_mode == GameMode.DIALOG
        assert state.dialog_state is not None
        assert state.battle_state is None

    def test_screenshot_included_when_provided(self):
        raw = make_raw()
        state = self.parser.build_state(raw, screenshot_b64="abc123==")
        assert state.screenshot_base64 == "abc123=="

    def test_screenshot_absent_when_not_provided(self):
        raw = make_raw()
        state = self.parser.build_state(raw)
        assert state.screenshot_base64 is None

    def test_poisoned_status_decoded(self):
        raw = make_raw(ninten_status=0b00000010)  # bit 1 = poisoned
        state = self.parser.build_state(raw)
        assert state.player.status == "poisoned"

    def test_level_zero_normalised_to_one(self):
        raw = make_raw(ninten_level=0)
        state = self.parser.build_state(raw)
        assert state.player.level == 1

    def test_party_is_empty_in_phase2(self):
        raw = make_raw()
        state = self.parser.build_state(raw)
        assert state.party == []

    def test_inventory_is_empty_in_phase2(self):
        raw = make_raw()
        state = self.parser.build_state(raw)
        assert state.inventory == []

    def test_model_serialises_to_json(self):
        """Ensure model_dump works without exceptions (Pydantic v2 compatibility)."""
        raw = make_raw()
        state = self.parser.build_state(raw)
        data = state.model_dump(mode="json", exclude_none=True)
        assert data["game_mode"] == "overworld"
        assert data["player"]["name"] == "Ninten"

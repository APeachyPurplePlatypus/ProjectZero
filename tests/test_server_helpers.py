"""Tests for MCP server helper functions.

Tests _build_full_state, _dispatch_action, _enforce_rate_limit, and
KNOWN_ADDRESSES directly without going through MCP tool handlers.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import fields
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from src.bridge.emulator_bridge import GameState, EmulatorBridge
from src.mcp_server.screenshot_policy import ScreenshotPolicy
from src.mcp_server.server import (
    KNOWN_ADDRESSES,
    _build_full_state,
    _dispatch_action,
)
from src.state_parser.parser import GameStateParser


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

OVERWORLD_STATE = GameState(
    frame=100, map_id=2, player_x=10, player_y=20,
    ninten_hp=68, ninten_max_hp=68, ninten_level=5, combat_active=0,
)

BATTLE_STATE = GameState(
    frame=200, map_id=2, player_x=10, player_y=20,
    ninten_hp=40, ninten_max_hp=68, ninten_level=5,
    combat_active=1, enemy_group_id=1,
)


def _mock_bridge(state: GameState = OVERWORLD_STATE) -> MagicMock:
    bridge = MagicMock(spec=EmulatorBridge)
    bridge.get_state.return_value = state
    bridge.capture_screenshot.return_value = "base64png"
    return bridge


# ---------------------------------------------------------------------------
# TestBuildFullState
# ---------------------------------------------------------------------------

class TestBuildFullState:
    def test_with_screenshot(self):
        bridge = _mock_bridge()
        parser = GameStateParser()
        state = _build_full_state(bridge, parser, include_screenshot=True)
        bridge.capture_screenshot.assert_called_once()
        assert state.screenshot_base64 == "base64png"

    def test_without_screenshot(self):
        bridge = _mock_bridge()
        parser = GameStateParser()
        state = _build_full_state(bridge, parser, include_screenshot=False)
        bridge.capture_screenshot.assert_not_called()
        assert state.screenshot_base64 is None

    def test_policy_enabled_skips_routine(self):
        bridge = _mock_bridge()
        parser = GameStateParser()
        policy = ScreenshotPolicy(enabled=True)
        # First call: policy includes (first action rule)
        _build_full_state(bridge, parser, include_screenshot=True, policy=policy)
        bridge.capture_screenshot.assert_called_once()
        bridge.capture_screenshot.reset_mock()
        # Second call: same map, same mode → policy skips
        state = _build_full_state(bridge, parser, include_screenshot=True, policy=policy)
        bridge.capture_screenshot.assert_not_called()
        assert state.screenshot_base64 is None

    def test_policy_includes_on_mode_transition(self):
        parser = GameStateParser()
        policy = ScreenshotPolicy(enabled=True)
        # First call with overworld
        bridge_ow = _mock_bridge(OVERWORLD_STATE)
        _build_full_state(bridge_ow, parser, include_screenshot=True, policy=policy)
        # Second call with battle (mode transition)
        bridge_battle = _mock_bridge(BATTLE_STATE)
        _build_full_state(bridge_battle, parser, include_screenshot=True, policy=policy)
        bridge_battle.capture_screenshot.assert_called_once()

    def test_explicit_false_always_skips(self):
        bridge = _mock_bridge()
        parser = GameStateParser()
        policy = ScreenshotPolicy(enabled=True)
        # Even first action with explicit False should skip
        state = _build_full_state(bridge, parser, include_screenshot=False, policy=policy)
        bridge.capture_screenshot.assert_not_called()
        assert state.screenshot_base64 is None


# ---------------------------------------------------------------------------
# TestDispatchAction
# ---------------------------------------------------------------------------

class TestDispatchAction:
    def test_dispatch_move(self):
        bridge = _mock_bridge()
        desc = _dispatch_action(bridge, "move", "right", None, None, 15)
        bridge.send_input.assert_called_once_with(
            command="move", direction="right", duration_frames=15
        )
        assert "move right" in desc

    def test_dispatch_button(self):
        bridge = _mock_bridge()
        desc = _dispatch_action(bridge, "button", None, "A", None, 2)
        bridge.send_input.assert_called_once_with(
            command="button", button="A", duration_frames=2
        )
        assert "press A" in desc

    def test_dispatch_text_advance(self):
        bridge = _mock_bridge()
        desc = _dispatch_action(bridge, "text_advance", None, None, None, 2)
        bridge.send_input.assert_called_once_with(
            command="button", button="A", duration_frames=2
        )
        assert "text_advance" in desc

    def test_dispatch_menu_navigate(self):
        bridge = _mock_bridge()
        desc = _dispatch_action(bridge, "menu_navigate", None, None, ["BASH", "Enemy"], 4)
        assert bridge.send_input.call_count == 2
        assert "BASH" in desc and "Enemy" in desc

    def test_dispatch_wait(self):
        bridge = _mock_bridge()
        desc = _dispatch_action(bridge, "wait", None, None, None, 30)
        bridge.send_input.assert_called_once_with(
            command="wait", duration_frames=30
        )
        assert "wait 30" in desc


# ---------------------------------------------------------------------------
# TestKnownAddresses
# ---------------------------------------------------------------------------

class TestKnownAddresses:
    def test_all_keys_valid_hex_format(self):
        for addr in KNOWN_ADDRESSES:
            assert re.match(r"^0x[0-9a-f]+$", addr), f"Invalid hex address: {addr}"

    def test_all_field_names_exist_in_gamestate(self):
        gs_fields = {f.name for f in fields(GameState)}
        for addr, (field_name, _) in KNOWN_ADDRESSES.items():
            assert field_name in gs_fields, (
                f"KNOWN_ADDRESSES[{addr}] → '{field_name}' not in GameState"
            )

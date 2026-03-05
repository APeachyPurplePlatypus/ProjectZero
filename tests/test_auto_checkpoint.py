"""Unit tests for the AutoCheckpoint system using a mock EmulatorBridge."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import time

import pytest

from src.bridge.auto_checkpoint import AutoCheckpoint


def make_bridge(save_id: str = "ss_test_label") -> MagicMock:
    """Return a mock EmulatorBridge with create_save_state returning save_id."""
    bridge = MagicMock()
    bridge.create_save_state.return_value = save_id
    return bridge


class TestNewMapTrigger:
    def test_new_map_triggers_save(self):
        bridge = make_bridge("ss_new_map")
        cp = AutoCheckpoint(bridge)
        # First observation — sets baseline
        cp.check_and_save(map_id=0, hp=50, max_hp=100)
        # Second observation — different map
        result = cp.check_and_save(map_id=1, hp=50, max_hp=100)
        assert result == "ss_new_map"
        bridge.create_save_state.assert_called_once()

    def test_same_map_no_save(self):
        bridge = make_bridge()
        cp = AutoCheckpoint(bridge)
        cp.check_and_save(map_id=0, hp=50, max_hp=100)
        result = cp.check_and_save(map_id=0, hp=50, max_hp=100)
        assert result is None
        bridge.create_save_state.assert_not_called()

    def test_no_save_on_first_observation(self):
        """First call sets baseline; should not trigger even if map_id=99."""
        bridge = make_bridge()
        cp = AutoCheckpoint(bridge)
        result = cp.check_and_save(map_id=99, hp=50, max_hp=100)
        assert result is None
        bridge.create_save_state.assert_not_called()


class TestHealedFullTrigger:
    def test_healed_to_full_triggers_save(self):
        bridge = make_bridge("ss_healed")
        cp = AutoCheckpoint(bridge)
        # Baseline: damaged
        cp.check_and_save(map_id=0, hp=30, max_hp=100)
        # Now healed to full
        result = cp.check_and_save(map_id=0, hp=100, max_hp=100)
        assert result == "ss_healed"

    def test_already_at_full_no_save(self):
        bridge = make_bridge()
        cp = AutoCheckpoint(bridge)
        cp.check_and_save(map_id=0, hp=100, max_hp=100)
        result = cp.check_and_save(map_id=0, hp=100, max_hp=100)
        assert result is None

    def test_partial_heal_no_save(self):
        bridge = make_bridge()
        cp = AutoCheckpoint(bridge)
        cp.check_and_save(map_id=0, hp=30, max_hp=100)
        result = cp.check_and_save(map_id=0, hp=70, max_hp=100)
        assert result is None

    def test_no_heal_trigger_at_session_start(self):
        """If the first observation shows full HP, don't trigger (last_hp starts at -1)."""
        bridge = make_bridge()
        cp = AutoCheckpoint(bridge)
        result = cp.check_and_save(map_id=0, hp=100, max_hp=100)
        assert result is None


class TestPeriodicTrigger:
    def test_periodic_timer_triggers_save(self):
        bridge = make_bridge("ss_periodic")
        cp = AutoCheckpoint(bridge, interval_minutes=0.001)  # ~60ms
        # First observation sets baseline but should not trigger yet
        cp.check_and_save(map_id=0, hp=50, max_hp=100)
        time.sleep(0.1)  # Wait past interval
        result = cp.check_and_save(map_id=0, hp=50, max_hp=100)
        assert result == "ss_periodic"

    def test_periodic_not_triggered_before_interval(self):
        bridge = make_bridge()
        cp = AutoCheckpoint(bridge, interval_minutes=10.0)  # Long interval
        cp.check_and_save(map_id=0, hp=50, max_hp=100)
        result = cp.check_and_save(map_id=0, hp=50, max_hp=100)
        assert result is None


class TestDisabled:
    def test_disabled_does_nothing(self):
        bridge = make_bridge()
        cp = AutoCheckpoint(bridge, enabled=False)
        cp.check_and_save(map_id=0, hp=50, max_hp=100)
        result = cp.check_and_save(map_id=1, hp=100, max_hp=100)  # Would trigger
        assert result is None
        bridge.create_save_state.assert_not_called()


class TestGameOver:
    def test_game_over_restores_latest_save(self):
        bridge = make_bridge("ss_checkpoint")
        cp = AutoCheckpoint(bridge)
        cp.check_and_save(map_id=0, hp=50, max_hp=100)
        cp.check_and_save(map_id=1, hp=50, max_hp=100)  # triggers save
        restored = cp.check_game_over(hp=0)
        assert restored is True
        bridge.restore_save_state.assert_called_once_with("ss_checkpoint")

    def test_game_over_no_save_returns_false(self):
        bridge = make_bridge()
        cp = AutoCheckpoint(bridge)
        restored = cp.check_game_over(hp=0)
        assert restored is False
        bridge.restore_save_state.assert_not_called()

    def test_alive_no_restore(self):
        bridge = make_bridge("ss_x")
        cp = AutoCheckpoint(bridge)
        cp.check_and_save(map_id=0, hp=50, max_hp=100)
        cp.check_and_save(map_id=1, hp=50, max_hp=100)
        restored = cp.check_game_over(hp=40)
        assert restored is False

    def test_restore_failure_returns_false(self):
        bridge = make_bridge("ss_x")
        bridge.restore_save_state.side_effect = RuntimeError("Emulator crashed")
        cp = AutoCheckpoint(bridge)
        cp.check_and_save(map_id=0, hp=50, max_hp=100)
        cp.check_and_save(map_id=1, hp=50, max_hp=100)
        restored = cp.check_game_over(hp=0)
        assert restored is False


class TestProperties:
    def test_latest_save_id_tracks_most_recent(self):
        bridge = MagicMock()
        bridge.create_save_state.side_effect = ["ss_1", "ss_2"]
        cp = AutoCheckpoint(bridge, interval_minutes=0.001)
        cp.check_and_save(map_id=0, hp=50, max_hp=100)
        time.sleep(0.1)
        cp.check_and_save(map_id=0, hp=50, max_hp=100)
        time.sleep(0.1)
        cp.check_and_save(map_id=0, hp=50, max_hp=100)
        assert cp.latest_save_id == "ss_2"

    def test_all_save_ids_accumulates(self):
        bridge = MagicMock()
        bridge.create_save_state.side_effect = ["ss_a", "ss_b"]
        cp = AutoCheckpoint(bridge)
        cp.check_and_save(map_id=0, hp=50, max_hp=100)
        cp.check_and_save(map_id=1, hp=50, max_hp=100)
        cp.check_and_save(map_id=2, hp=50, max_hp=100)
        assert cp.all_save_ids == ["ss_a", "ss_b"]

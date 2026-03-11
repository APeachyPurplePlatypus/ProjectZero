"""Unit tests for EmulatorBridge without a live emulator.

Uses tmp_path for IPC files and mocks for subprocess. Tests state parsing,
input writing, save state management, and file utilities.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.bridge.emulator_bridge import (
    BridgeTimeoutError,
    EmulatorBridge,
    EmulatorCrashedError,
    GameState,
    StaleStateError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(shared_dir: Path) -> dict:
    return {
        "emulator": {"path": "fceux", "lua_script": "lua/main.lua"},
        "ipc": {
            "shared_dir": str(shared_dir),
            "state_file": "state.json",
            "input_file": "input.json",
            "screenshot_file": "screenshot.png",
            "poll_interval_ms": 5,
            "stale_threshold_ms": 200,
        },
    }


def _make_bridge(tmp_path: Path) -> EmulatorBridge:
    shared = tmp_path / "shared"
    shared.mkdir()
    bridge = EmulatorBridge(_make_config(shared))
    # Simulate a running process so is_alive() returns True
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None
    bridge._process = mock_proc
    return bridge


def _write_state(bridge: EmulatorBridge, data: dict) -> None:
    bridge._state_file.write_text(json.dumps(data))


# ---------------------------------------------------------------------------
# TestGetState
# ---------------------------------------------------------------------------

class TestGetState:
    def test_parses_valid_state_json(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        _write_state(bridge, {
            "frame": 100, "map_id": 2, "player_x": 10, "player_y": 20,
            "ninten_hp": 68, "ninten_max_hp": 68, "ninten_level": 5,
            "combat_active": 0, "money": 500, "melodies": 3,
        })
        state = bridge.get_state()
        assert state.frame == 100
        assert state.map_id == 2
        assert state.ninten_hp == 68
        assert state.ninten_level == 5
        assert state.money == 500
        assert state.melodies == 3

    def test_missing_fields_default_to_zero(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        _write_state(bridge, {"frame": 1})
        state = bridge.get_state()
        assert state.ninten_hp == 0
        assert state.map_id == 0
        assert state.money == 0

    def test_missing_file_raises_stale_state(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        with pytest.raises(StaleStateError):
            bridge.get_state()

    def test_empty_file_raises_stale_state(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge._state_file.write_text("")
        with pytest.raises(StaleStateError):
            bridge.get_state()

    def test_invalid_json_raises_stale_state(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge._state_file.write_text("{broken json!!")
        with pytest.raises(StaleStateError):
            bridge.get_state()

    def test_not_alive_raises_emulator_crashed(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge._process.poll.return_value = 1  # process exited
        with pytest.raises(EmulatorCrashedError):
            bridge.get_state()


# ---------------------------------------------------------------------------
# TestSendInput
# ---------------------------------------------------------------------------

class TestSendInput:
    def test_writes_correct_input_json(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        orig_write = bridge._write_json_atomic

        def write_and_ack(path, data):
            orig_write(path, data)
            # Verify content before removing
            content = json.loads(path.read_text())
            assert content["command"] == "button"
            assert content["button"] == "A"
            assert content["duration_frames"] == 4
            path.unlink()  # Simulate Lua consuming input
            # Write done file after consumption (like Lua would)
            bridge._done_file.write_text(json.dumps({"frame_id": data["frame_id"]}))

        bridge._write_json_atomic = write_and_ack
        bridge.send_input(command="button", button="A", duration_frames=4)

    def test_frame_id_increments(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        assert bridge._frame_id_counter == 0

        orig_write = bridge._write_json_atomic

        def auto_ack(path, data):
            orig_write(path, data)
            path.unlink()
            bridge._done_file.write_text(json.dumps({"frame_id": data["frame_id"]}))

        bridge._write_json_atomic = auto_ack
        bridge.send_input(command="wait", duration_frames=1)
        assert bridge._frame_id_counter == 1

    def test_duration_capped_at_120(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        written_data = {}
        orig_write = bridge._write_json_atomic

        def capture_and_ack(path, data):
            written_data.update(data)
            orig_write(path, data)
            path.unlink()
            bridge._done_file.write_text(json.dumps({"frame_id": data["frame_id"]}))

        bridge._write_json_atomic = capture_and_ack
        bridge.send_input(command="wait", duration_frames=200)
        assert written_data["duration_frames"] == 120

    def test_not_alive_raises_emulator_crashed(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge._process.poll.return_value = 1
        with pytest.raises(EmulatorCrashedError):
            bridge.send_input(command="wait", duration_frames=1)


# ---------------------------------------------------------------------------
# TestSaveStates
# ---------------------------------------------------------------------------

class TestSaveStates:
    def test_create_returns_id_with_label(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        orig_write = bridge._write_json_atomic

        def auto_ack(path, data):
            orig_write(path, data)
            path.unlink()
            bridge._done_file.write_text(json.dumps({"frame_id": data["frame_id"]}))

        bridge._write_json_atomic = auto_ack
        state_id = bridge.create_save_state("before_boss")
        assert "before_boss" in state_id
        assert state_id.startswith("ss_")

    def test_sequential_slot_allocation(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        orig_write = bridge._write_json_atomic

        def auto_ack(path, data):
            orig_write(path, data)
            path.unlink()
            bridge._done_file.write_text(json.dumps({"frame_id": data["frame_id"]}))

        bridge._write_json_atomic = auto_ack

        id1 = bridge.create_save_state("slot1")
        id2 = bridge.create_save_state("slot2")
        assert bridge._save_slots[id1] == 1
        assert bridge._save_slots[id2] == 2

    def test_slot_cycling_wraps_at_max(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge._max_slots = 3
        # Allocate 4 slots — 4th should wrap to 1
        slots = [bridge._allocate_slot() for _ in range(4)]
        assert slots == [1, 2, 3, 1]

    def test_restore_unknown_id_raises_value_error(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        with pytest.raises(ValueError, match="Unknown save state"):
            bridge.restore_save_state("nonexistent_id")

    def test_list_save_states_returns_mapping(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge._save_slots = {"ss_a": 1, "ss_b": 2}
        result = bridge.list_save_states()
        assert result == {"ss_a": 1, "ss_b": 2}


# ---------------------------------------------------------------------------
# TestFileUtilities
# ---------------------------------------------------------------------------

class TestFileUtilities:
    def test_read_json_safe_valid(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        path = tmp_path / "test.json"
        path.write_text('{"key": "value"}')
        result = bridge._read_json_safe(path)
        assert result == {"key": "value"}

    def test_read_json_safe_missing_returns_none(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        result = bridge._read_json_safe(tmp_path / "missing.json")
        assert result is None

    def test_read_json_safe_invalid_returns_none(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        path = tmp_path / "bad.json"
        path.write_text("not json")
        result = bridge._read_json_safe(path)
        assert result is None

    def test_write_json_atomic_creates_file(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        path = tmp_path / "out.json"
        bridge._write_json_atomic(path, {"hello": "world"})
        assert json.loads(path.read_text()) == {"hello": "world"}

    def test_cleanup_ipc_files_removes_all(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        for f in [bridge._state_file, bridge._input_file, bridge._done_file,
                   bridge._screenshot_file, bridge._ready_file]:
            f.write_text("{}")
        bridge._cleanup_ipc_files()
        for f in [bridge._state_file, bridge._input_file, bridge._done_file,
                   bridge._screenshot_file, bridge._ready_file]:
            assert not f.exists()


# ---------------------------------------------------------------------------
# TestLifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    def test_is_alive_false_with_no_process(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        bridge._process = None
        assert bridge.is_alive() is False

    def test_is_alive_true_with_running_process(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        assert bridge.is_alive() is True

    def test_stop_terminates_process(self, tmp_path):
        bridge = _make_bridge(tmp_path)
        mock_proc = bridge._process
        mock_proc.wait.return_value = 0
        bridge.stop()
        mock_proc.terminate.assert_called_once()

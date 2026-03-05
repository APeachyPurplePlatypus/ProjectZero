"""Python bridge to FCEUX emulator via file-based IPC.

Launches FCEUX with Lua scripts, reads game state from shared/state.json,
writes input commands to shared/input.json, and captures screenshots.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class EmulatorNotFoundError(Exception):
    """FCEUX executable not found."""


class RomNotFoundError(Exception):
    """ROM file not found."""


class BridgeTimeoutError(Exception):
    """IPC operation timed out."""


class StaleStateError(Exception):
    """Game state is stale (not updating)."""


class EmulatorCrashedError(Exception):
    """FCEUX process exited unexpectedly."""


# ---------------------------------------------------------------------------
# GameState
# ---------------------------------------------------------------------------

@dataclass
class GameState:
    """Raw game state from FCEUX memory reads."""

    frame: int = 0
    map_id: int = 0
    player_x: int = 0
    player_y: int = 0
    player_direction: int = 0
    movement_state: int = 0
    ninten_hp: int = 0
    ninten_max_hp: int = 0
    ninten_pp: int = 0
    ninten_max_pp: int = 0
    ninten_level: int = 0
    ninten_exp: int = 0
    ninten_status: int = 0
    combat_active: int = 0
    enemy_group_id: int = 0
    menu_state: int = 0
    dialog_active: int = 0

    # Party allies (Phase 5)
    ana_hp: int = 0
    ana_max_hp: int = 0
    ana_pp: int = 0
    ana_max_pp: int = 0
    ana_level: int = 0
    ana_status: int = 0

    lloyd_hp: int = 0
    lloyd_max_hp: int = 0
    lloyd_pp: int = 0
    lloyd_max_pp: int = 0
    lloyd_level: int = 0
    lloyd_status: int = 0

    teddy_hp: int = 0
    teddy_max_hp: int = 0
    teddy_pp: int = 0
    teddy_max_pp: int = 0
    teddy_level: int = 0
    teddy_status: int = 0

    # Party composition slots (ally IDs; 0 = empty)
    party_0: int = 0
    party_1: int = 0
    party_2: int = 0
    party_3: int = 0

    # Inventory — flat 32-slot array (4 characters x 8 slots)
    inv_0: int = 0
    inv_1: int = 0
    inv_2: int = 0
    inv_3: int = 0
    inv_4: int = 0
    inv_5: int = 0
    inv_6: int = 0
    inv_7: int = 0
    inv_8: int = 0
    inv_9: int = 0
    inv_10: int = 0
    inv_11: int = 0
    inv_12: int = 0
    inv_13: int = 0
    inv_14: int = 0
    inv_15: int = 0
    inv_16: int = 0
    inv_17: int = 0
    inv_18: int = 0
    inv_19: int = 0
    inv_20: int = 0
    inv_21: int = 0
    inv_22: int = 0
    inv_23: int = 0
    inv_24: int = 0
    inv_25: int = 0
    inv_26: int = 0
    inv_27: int = 0
    inv_28: int = 0
    inv_29: int = 0
    inv_30: int = 0
    inv_31: int = 0

    # Economy / progress
    money: int = 0
    melodies: int = 0  # Bitfield: each bit = one melody collected


# ---------------------------------------------------------------------------
# EmulatorBridge
# ---------------------------------------------------------------------------

class EmulatorBridge:
    """Two-way IPC bridge between Python and FCEUX via shared JSON files."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        if config is None:
            config = self._load_config()

        self._config = config
        self._project_root = Path(__file__).resolve().parent.parent.parent
        self._shared_dir = self._project_root / config["ipc"]["shared_dir"]
        self._state_file = self._shared_dir / config["ipc"]["state_file"]
        self._input_file = self._shared_dir / config["ipc"]["input_file"]
        self._done_file = self._shared_dir / "input_done.json"
        self._screenshot_file = self._shared_dir / config["ipc"]["screenshot_file"]
        self._ready_file = self._shared_dir / "lua_ready.json"
        self._poll_interval = config["ipc"]["poll_interval_ms"] / 1000.0
        self._stale_threshold = config["ipc"]["stale_threshold_ms"] / 1000.0
        self._process: subprocess.Popen[bytes] | None = None
        self._last_frame: int = -1
        self._frame_id_counter: int = 0
        self._save_slots: dict[str, int] = {}  # state_id -> slot number
        self._next_slot: int = 1
        self._max_slots: int = 10

    def _load_config(self) -> dict[str, Any]:
        config_path = Path(__file__).resolve().parent.parent.parent / "config.json"
        with open(config_path) as f:
            return json.load(f)

    # -- Lifecycle ------------------------------------------------------------

    def start(self, rom_path: str | Path) -> None:
        """Launch FCEUX with Lua scripts and wait for ready signal."""
        rom_path = Path(rom_path).resolve()
        if not rom_path.exists():
            raise RomNotFoundError(f"ROM not found: {rom_path}")

        fceux_path = self._resolve_fceux_path()

        # Ensure shared directory exists and is clean
        self._shared_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_ipc_files()

        lua_script = str(self._project_root / self._config["emulator"]["lua_script"])
        cmd = [fceux_path, "-lua", lua_script, str(rom_path)]

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        self._wait_for_ready(timeout=15.0)

    def _resolve_fceux_path(self) -> str:
        """Find the FCEUX executable."""
        configured = self._config["emulator"]["path"]

        # Check if it's directly executable
        found = shutil.which(configured)
        if found:
            return found

        # Check if it's an absolute/relative path that exists
        if Path(configured).exists():
            return str(Path(configured).resolve())

        # Try common Windows install locations
        common_paths = [
            Path(r"C:\Program Files\FCEUX\fceux.exe"),
            Path(r"C:\Program Files (x86)\FCEUX\fceux.exe"),
            Path.home() / "scoop" / "apps" / "fceux" / "current" / "fceux.exe",
        ]
        for p in common_paths:
            if p.exists():
                return str(p)

        raise EmulatorNotFoundError(
            f"FCEUX not found at '{configured}'. "
            "Install FCEUX and add to PATH, or set emulator.path in config.json."
        )

    def _wait_for_ready(self, timeout: float) -> None:
        """Block until lua_ready.json appears or timeout."""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if self._ready_file.exists():
                data = self._read_json_safe(self._ready_file)
                if data and data.get("status") == "ready":
                    return
            if not self.is_alive():
                stderr = ""
                if self._process and self._process.stderr:
                    stderr = self._process.stderr.read().decode(errors="replace")
                raise EmulatorCrashedError(
                    f"FCEUX exited during startup. stderr: {stderr[:500]}"
                )
            time.sleep(0.1)
        raise BridgeTimeoutError(f"FCEUX did not signal ready within {timeout}s")

    def stop(self) -> None:
        """Terminate FCEUX process and clean up."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._cleanup_ipc_files()

    def is_alive(self) -> bool:
        """Check if FCEUX process is still running."""
        return self._process is not None and self._process.poll() is None

    # -- State Reading --------------------------------------------------------

    def get_state(self) -> GameState:
        """Read current game state from shared/state.json."""
        if not self.is_alive():
            raise EmulatorCrashedError("FCEUX is not running.")

        data = self._read_json_safe(self._state_file)
        if data is None:
            raise StaleStateError("state.json not found or unreadable.")

        self._last_frame = data.get("frame", -1)

        return GameState(
            frame=data.get("frame", 0),
            map_id=data.get("map_id", 0),
            player_x=data.get("player_x", 0),
            player_y=data.get("player_y", 0),
            player_direction=data.get("player_direction", 0),
            movement_state=data.get("movement_state", 0),
            ninten_hp=data.get("ninten_hp", 0),
            ninten_max_hp=data.get("ninten_max_hp", 0),
            ninten_pp=data.get("ninten_pp", 0),
            ninten_max_pp=data.get("ninten_max_pp", 0),
            ninten_level=data.get("ninten_level", 0),
            ninten_exp=data.get("ninten_exp", 0),
            ninten_status=data.get("ninten_status", 0),
            combat_active=data.get("combat_active", 0),
            enemy_group_id=data.get("enemy_group_id", 0),
            menu_state=data.get("menu_state", 0),
            dialog_active=data.get("dialog_active", 0),
            # Party allies
            ana_hp=data.get("ana_hp", 0),
            ana_max_hp=data.get("ana_max_hp", 0),
            ana_pp=data.get("ana_pp", 0),
            ana_max_pp=data.get("ana_max_pp", 0),
            ana_level=data.get("ana_level", 0),
            ana_status=data.get("ana_status", 0),
            lloyd_hp=data.get("lloyd_hp", 0),
            lloyd_max_hp=data.get("lloyd_max_hp", 0),
            lloyd_pp=data.get("lloyd_pp", 0),
            lloyd_max_pp=data.get("lloyd_max_pp", 0),
            lloyd_level=data.get("lloyd_level", 0),
            lloyd_status=data.get("lloyd_status", 0),
            teddy_hp=data.get("teddy_hp", 0),
            teddy_max_hp=data.get("teddy_max_hp", 0),
            teddy_pp=data.get("teddy_pp", 0),
            teddy_max_pp=data.get("teddy_max_pp", 0),
            teddy_level=data.get("teddy_level", 0),
            teddy_status=data.get("teddy_status", 0),
            # Party composition
            party_0=data.get("party_0", 0),
            party_1=data.get("party_1", 0),
            party_2=data.get("party_2", 0),
            party_3=data.get("party_3", 0),
            # Inventory
            inv_0=data.get("inv_0", 0),
            inv_1=data.get("inv_1", 0),
            inv_2=data.get("inv_2", 0),
            inv_3=data.get("inv_3", 0),
            inv_4=data.get("inv_4", 0),
            inv_5=data.get("inv_5", 0),
            inv_6=data.get("inv_6", 0),
            inv_7=data.get("inv_7", 0),
            inv_8=data.get("inv_8", 0),
            inv_9=data.get("inv_9", 0),
            inv_10=data.get("inv_10", 0),
            inv_11=data.get("inv_11", 0),
            inv_12=data.get("inv_12", 0),
            inv_13=data.get("inv_13", 0),
            inv_14=data.get("inv_14", 0),
            inv_15=data.get("inv_15", 0),
            inv_16=data.get("inv_16", 0),
            inv_17=data.get("inv_17", 0),
            inv_18=data.get("inv_18", 0),
            inv_19=data.get("inv_19", 0),
            inv_20=data.get("inv_20", 0),
            inv_21=data.get("inv_21", 0),
            inv_22=data.get("inv_22", 0),
            inv_23=data.get("inv_23", 0),
            inv_24=data.get("inv_24", 0),
            inv_25=data.get("inv_25", 0),
            inv_26=data.get("inv_26", 0),
            inv_27=data.get("inv_27", 0),
            inv_28=data.get("inv_28", 0),
            inv_29=data.get("inv_29", 0),
            inv_30=data.get("inv_30", 0),
            inv_31=data.get("inv_31", 0),
            # Economy / progress
            money=data.get("money", 0),
            melodies=data.get("melodies", 0),
        )

    # -- Input Sending --------------------------------------------------------

    def send_input(
        self,
        command: str,
        button: str | None = None,
        direction: str | None = None,
        duration_frames: int = 2,
        capture_screenshot: bool = False,
    ) -> None:
        """Write an input command and block until Lua completes it.

        Args:
            command: "button", "move", or "wait"
            button: Button name (A, B, Start, Select) — for "button" command
            direction: Direction (up, down, left, right) — for "move" command
            duration_frames: How many frames to hold the input (max 120)
            capture_screenshot: If True, capture a screenshot after the action
        """
        if not self.is_alive():
            raise EmulatorCrashedError("FCEUX is not running.")

        duration_frames = min(duration_frames, 120)  # Cap at 2 seconds

        self._frame_id_counter += 1
        cmd = {
            "command": command,
            "button": button,
            "direction": direction,
            "duration_frames": duration_frames,
            "capture_screenshot": capture_screenshot,
            "frame_id": self._frame_id_counter,
        }

        # Clean stale done file
        self._remove_safe(self._done_file)

        # Write command atomically
        self._write_json_atomic(self._input_file, cmd)

        # Wait for Lua to acknowledge (deletes input.json)
        self._wait_for_file_gone(self._input_file, timeout=2.0)

        # Wait for action to complete (input_done.json appears)
        max_wait = (duration_frames / 60.0) + 2.0  # action time + 2s buffer
        self._wait_for_done(self._frame_id_counter, timeout=max_wait)

    def _wait_for_file_gone(self, path: Path, timeout: float) -> None:
        """Wait until a file no longer exists."""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if not path.exists():
                return
            if not self.is_alive():
                raise EmulatorCrashedError("FCEUX crashed while processing input.")
            time.sleep(self._poll_interval)
        raise BridgeTimeoutError(f"Lua did not acknowledge input within {timeout}s")

    def _wait_for_done(self, frame_id: int, timeout: float) -> None:
        """Wait until input_done.json appears with matching frame_id."""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            data = self._read_json_safe(self._done_file)
            if data and data.get("frame_id") == frame_id:
                self._remove_safe(self._done_file)
                return
            if not self.is_alive():
                raise EmulatorCrashedError("FCEUX crashed during action execution.")
            time.sleep(self._poll_interval)
        raise BridgeTimeoutError(
            f"Input command (frame_id={frame_id}) did not complete within {timeout}s"
        )

    # -- Screenshots ----------------------------------------------------------

    def capture_screenshot(self) -> str:
        """Trigger screenshot capture and return base64-encoded PNG data."""
        self.send_input(command="wait", duration_frames=1, capture_screenshot=True)

        # Wait briefly for the file to be written
        for _ in range(20):
            if self._screenshot_file.exists():
                with open(self._screenshot_file, "rb") as f:
                    png_data = f.read()
                if len(png_data) > 0:
                    return base64.b64encode(png_data).decode("ascii")
            time.sleep(0.05)

        raise BridgeTimeoutError("Screenshot file not created.")

    # -- Save States ----------------------------------------------------------

    def create_save_state(self, label: str) -> str:
        """Create an emulator save state via FCEUX Lua savestate API.

        Returns a state_id string that can be passed to restore_save_state().
        Cycles through slots 1-10, overwriting the oldest when full.
        """
        if not self.is_alive():
            raise EmulatorCrashedError("FCEUX is not running.")

        slot = self._allocate_slot()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        state_id = f"ss_{timestamp}_{label}"

        self._frame_id_counter += 1
        cmd = {
            "command": "savestate_save",
            "slot": slot,
            "frame_id": self._frame_id_counter,
        }
        self._remove_safe(self._done_file)
        self._write_json_atomic(self._input_file, cmd)
        self._wait_for_file_gone(self._input_file, timeout=2.0)
        self._wait_for_done(self._frame_id_counter, timeout=3.0)

        self._save_slots[state_id] = slot
        return state_id

    def restore_save_state(self, state_id: str) -> None:
        """Restore a previously created save state via FCEUX Lua savestate API."""
        if not self.is_alive():
            raise EmulatorCrashedError("FCEUX is not running.")

        slot = self._save_slots.get(state_id)
        if slot is None:
            raise ValueError(f"Unknown save state ID: '{state_id}'")

        self._frame_id_counter += 1
        cmd = {
            "command": "savestate_load",
            "slot": slot,
            "frame_id": self._frame_id_counter,
        }
        self._remove_safe(self._done_file)
        self._write_json_atomic(self._input_file, cmd)
        self._wait_for_file_gone(self._input_file, timeout=2.0)
        self._wait_for_done(self._frame_id_counter, timeout=3.0)

    def _allocate_slot(self) -> int:
        """Allocate next save state slot (1-10), cycling to reuse oldest."""
        slot = self._next_slot
        self._next_slot = (self._next_slot % self._max_slots) + 1
        return slot

    def list_save_states(self) -> dict[str, int]:
        """Return current state_id -> slot mapping (for debugging)."""
        return dict(self._save_slots)

    # -- File Utilities -------------------------------------------------------

    def _read_json_safe(self, path: Path) -> dict[str, Any] | None:
        """Read and parse a JSON file, returning None on any error."""
        try:
            with open(path) as f:
                content = f.read()
            if not content.strip():
                return None
            return json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    def _write_json_atomic(self, path: Path, data: dict[str, Any]) -> None:
        """Atomically write JSON data to a file."""
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(data, f)
        os.replace(str(tmp_path), str(path))

    def _remove_safe(self, path: Path) -> None:
        """Remove a file, ignoring errors if it doesn't exist."""
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def _cleanup_ipc_files(self) -> None:
        """Remove all IPC files for a clean start."""
        for f in [
            self._state_file,
            self._input_file,
            self._done_file,
            self._screenshot_file,
            self._ready_file,
        ]:
            self._remove_safe(f)

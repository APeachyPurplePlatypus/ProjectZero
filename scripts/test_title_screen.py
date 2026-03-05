"""Deterministic test: navigate title screen to start a new game.

Expected sequence:
  1. Wait for title screen (~3 seconds)
  2. Press Start to open the main menu
  3. Press A to select NEW GAME (cursor starts on NEW GAME)
  4. Press A through name entry (accept default name "Ninten")
  5. Press A repeatedly to advance the intro dialog
  6. Verify: in overworld mode, max HP > 0

Usage:
    python scripts/test_title_screen.py <rom_path>

Note: Button timing is generous to accommodate frame-rate variation.
Adjust wait durations if the sequence misses a prompt.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.bridge.emulator_bridge import EmulatorBridge


def press(bridge: EmulatorBridge, button: str, hold: int = 4, pause: int = 30) -> None:
    """Press a button and wait for the animation to settle."""
    bridge.send_input(command="button", button=button, duration_frames=hold)
    bridge.send_input(command="wait", duration_frames=pause)


def test_title_to_gameplay(rom_path: str) -> None:
    bridge = EmulatorBridge()

    try:
        print("[1/6] Starting FCEUX...")
        bridge.start(rom_path)

        print("[2/6] Waiting for title screen to load (3s = 180 frames)...")
        bridge.send_input(command="wait", duration_frames=180)

        print("[3/6] Pressing Start...")
        press(bridge, "Start", hold=4, pause=90)  # 1.5s for menu to appear

        print("[4/6] Pressing A to select NEW GAME...")
        press(bridge, "A", hold=4, pause=90)  # 1.5s for name entry screen

        print("[5/6] Accepting default name — pressing A 5 times...")
        for _ in range(5):
            press(bridge, "A", hold=4, pause=60)

        print("[5/6] Advancing intro dialog — pressing A 20 times...")
        for i in range(20):
            press(bridge, "A", hold=4, pause=40)

        print("[6/6] Reading game state...")
        time.sleep(0.5)
        state = bridge.get_state()

        print(f"  map_id:        {state.map_id}")
        print(f"  position:      ({state.player_x}, {state.player_y})")
        print(f"  combat_active: {state.combat_active}")
        print(f"  HP:            {state.ninten_hp}/{state.ninten_max_hp}")
        print(f"  Level:         {state.ninten_level}")
        print(f"  Frame:         {state.frame}")

        # Assertions
        assert state.combat_active == 0, \
            f"Expected not in combat, combat_active={state.combat_active}"
        assert state.ninten_max_hp > 0, \
            f"Max HP should be set after game starts, got {state.ninten_max_hp}"

        print("\n[PASS] Title screen -> overworld navigation succeeded.")

    except AssertionError as exc:
        print(f"\n[FAIL] Assertion failed: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"\n[ERROR] Unexpected error: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        if bridge.is_alive():
            bridge.stop()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_title_screen.py <rom_path>")
        sys.exit(1)
    test_title_to_gameplay(sys.argv[1])

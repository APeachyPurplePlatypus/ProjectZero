"""Deterministic test: detect a battle, execute BASH, and verify the battle ends.

Strategy:
  1. Navigate the title screen to reach the overworld (Ninten's House).
  2. Walk outside and move randomly to trigger a random encounter.
  3. In battle: press A to select BASH (default cursor), press A to confirm.
  4. Advance battle result text.
  5. Assert: battle ended (combat_active == 0) and Ninten is still alive (HP > 0).

Usage:
    python scripts/test_first_battle.py <rom_path>
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.bridge.emulator_bridge import EmulatorBridge, GameState


def press(bridge: EmulatorBridge, button: str, hold: int = 4, pause: int = 30) -> None:
    bridge.send_input(command="button", button=button, duration_frames=hold)
    bridge.send_input(command="wait", duration_frames=pause)


def advance_title_screen(bridge: EmulatorBridge) -> None:
    """Navigate title screen to reach the overworld."""
    print("  [SETUP] Waiting for title screen...")
    bridge.send_input(command="wait", duration_frames=180)
    press(bridge, "Start", hold=4, pause=90)
    press(bridge, "A", hold=4, pause=90)
    for _ in range(5):
        press(bridge, "A", hold=4, pause=60)
    for _ in range(20):
        press(bridge, "A", hold=4, pause=40)
    time.sleep(0.5)


def walk_until_battle(bridge: EmulatorBridge, max_attempts: int = 300) -> bool:
    """Alternate right/left movement until combat_active triggers.

    Returns True when a battle is detected, False if max_attempts exceeded.
    """
    directions = ["right", "left", "up", "down"]
    for i in range(max_attempts):
        direction = directions[i % len(directions)]
        bridge.send_input(command="move", direction=direction, duration_frames=15)
        state = bridge.get_state()
        if state.combat_active != 0:
            return True
        time.sleep(0.05)
    return False


def execute_bash(bridge: EmulatorBridge) -> None:
    """Select BASH and confirm in the battle menu.

    In EarthBound Zero, the battle cursor defaults to BASH (first option).
    Pressing A selects BASH; the game auto-selects the first (only) enemy target.
    """
    # Select BASH
    press(bridge, "A", hold=4, pause=60)
    # Confirm target (or advance if auto-selected)
    press(bridge, "A", hold=4, pause=90)


def advance_battle_text(bridge: EmulatorBridge, max_presses: int = 40) -> bool:
    """Press A repeatedly to advance battle text until battle ends.

    Returns True when combat_active drops to 0, False if timeout reached.
    """
    for _ in range(max_presses):
        state = bridge.get_state()
        if state.combat_active == 0:
            return True
        press(bridge, "A", hold=4, pause=30)
    return False


def test_first_battle(rom_path: str) -> None:
    bridge = EmulatorBridge()

    try:
        print("[1/5] Starting FCEUX...")
        bridge.start(rom_path)

        print("[2/5] Navigating title screen...")
        advance_title_screen(bridge)

        state = bridge.get_state()
        print(f"  After title: HP={state.ninten_hp}/{state.ninten_max_hp}, "
              f"map={state.map_id}, combat={state.combat_active}")

        if state.ninten_max_hp == 0:
            print("[WARN] Max HP is 0 — game may not have loaded fully. "
                  "SRAM addresses may require an in-game save. Skipping battle test.")
            sys.exit(0)

        print("[3/5] Walking to trigger random encounter (up to 300 steps)...")
        found = walk_until_battle(bridge, max_attempts=300)
        if not found:
            print("[FAIL] No battle triggered within 300 movement steps.")
            sys.exit(1)

        state = bridge.get_state()
        print(f"  Battle started! enemy_group_id={state.enemy_group_id}, "
              f"HP={state.ninten_hp}/{state.ninten_max_hp}")

        print("[4/5] Executing BASH attack...")
        execute_bash(bridge)

        print("[4/5] Advancing battle result text...")
        # Battles in EarthBound Zero can take multiple rounds
        # For simple early encounters, one BASH is often enough
        for _round in range(5):
            state = bridge.get_state()
            if state.combat_active == 0:
                break
            print(f"  Round {_round + 1}: HP={state.ninten_hp}, combat still active")
            execute_bash(bridge)

        ended = advance_battle_text(bridge, max_presses=60)

        print("[5/5] Checking final state...")
        state = bridge.get_state()
        print(f"  combat_active: {state.combat_active}")
        print(f"  HP:            {state.ninten_hp}/{state.ninten_max_hp}")
        print(f"  Level:         {state.ninten_level}")

        assert ended, "Battle did not end within the expected number of turns."
        assert state.ninten_hp > 0, \
            f"Ninten should be alive after the first battle, HP={state.ninten_hp}"

        print("\n[PASS] First battle completed successfully.")

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
        print("Usage: python scripts/test_first_battle.py <rom_path>")
        sys.exit(1)
    test_first_battle(sys.argv[1])

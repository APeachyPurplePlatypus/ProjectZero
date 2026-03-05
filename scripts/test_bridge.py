"""Integration test for the emulator bridge.

Usage:
    python scripts/test_bridge.py <rom_path>

Requires FCEUX installed (on PATH or configured in config.json).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.bridge.emulator_bridge import EmulatorBridge, GameState


def test_startup(bridge: EmulatorBridge, rom_path: str) -> None:
    """Test 1: FCEUX launches and Lua signals ready."""
    print("[TEST 1] Starting FCEUX...")
    bridge.start(rom_path)
    assert bridge.is_alive(), "FCEUX should be running"
    print("[PASS] FCEUX started and Lua bridge ready.\n")


def test_read_state(bridge: EmulatorBridge) -> None:
    """Test 2: Can read game state from state.json."""
    print("[TEST 2] Reading game state...")
    time.sleep(0.5)  # Let a few state exports accumulate
    state = bridge.get_state()
    assert isinstance(state, GameState)
    assert state.frame > 0, f"Frame should be positive, got {state.frame}"
    print(f"  frame={state.frame}")
    print(f"  map_id={state.map_id}")
    print(f"  position=({state.player_x}, {state.player_y})")
    print(f"  direction={state.player_direction}")
    print(f"  HP={state.ninten_hp}/{state.ninten_max_hp}")
    print(f"  PP={state.ninten_pp}/{state.ninten_max_pp}")
    print(f"  level={state.ninten_level}")
    print(f"  combat_active={state.combat_active}")
    print("[PASS] State read successfully.\n")


def test_send_movement(bridge: EmulatorBridge) -> None:
    """Test 3: Can send movement input."""
    print("[TEST 3] Sending movement input (right, 30 frames)...")
    state_before = bridge.get_state()
    bridge.send_input(command="move", direction="right", duration_frames=30)
    time.sleep(0.2)  # Let state update after movement
    state_after = bridge.get_state()
    print(f"  before: frame={state_before.frame}, pos=({state_before.player_x}, {state_before.player_y})")
    print(f"  after:  frame={state_after.frame}, pos=({state_after.player_x}, {state_after.player_y})")
    assert state_after.frame > state_before.frame, "Frame should have advanced"
    print("[PASS] Movement input sent and acknowledged.\n")


def test_screenshot(bridge: EmulatorBridge) -> None:
    """Test 4: Can capture screenshot."""
    print("[TEST 4] Capturing screenshot...")
    b64_data = bridge.capture_screenshot()
    assert len(b64_data) > 100, f"Screenshot too small: {len(b64_data)} bytes"
    # Verify it's valid base64 PNG
    import base64
    raw = base64.b64decode(b64_data)
    assert raw[:4] == b"\x89PNG", "Screenshot should be a PNG file"
    print(f"  screenshot size: {len(raw)} bytes")
    print("[PASS] Screenshot captured successfully.\n")


def test_button_press(bridge: EmulatorBridge) -> None:
    """Test 5: Can press A button."""
    print("[TEST 5] Pressing A button...")
    state_before = bridge.get_state()
    bridge.send_input(command="button", button="A", duration_frames=2)
    state_after = bridge.get_state()
    assert state_after.frame > state_before.frame, "Frame should have advanced"
    print("[PASS] Button press completed.\n")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_bridge.py <rom_path>")
        print("\nExample:")
        print('  python scripts/test_bridge.py "path/to/EarthBound Zero.nes"')
        sys.exit(1)

    rom_path = sys.argv[1]
    if not Path(rom_path).exists():
        print(f"ERROR: ROM file not found: {rom_path}")
        sys.exit(1)

    bridge = EmulatorBridge()

    try:
        test_startup(bridge, rom_path)
        test_read_state(bridge)
        test_send_movement(bridge)
        test_screenshot(bridge)
        test_button_press(bridge)

        print("=" * 40)
        print("ALL 5 TESTS PASSED")
        print("=" * 40)
    except Exception as e:
        print(f"\nTEST FAILED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("\nShutting down FCEUX...")
        bridge.stop()


if __name__ == "__main__":
    main()

"""Launch FCEUX with the EarthBound Zero Lua bridge.

Run this in a terminal BEFORE opening Claude Desktop. The MCP server
(spawned automatically by Claude Desktop) will connect to the running
FCEUX process via the shared IPC files in shared/.

Usage:
    python scripts/start_game.py                    # ROM path from config.json
    python scripts/start_game.py <rom_path>         # override ROM path
"""

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.bridge.emulator_bridge import EmulatorBridge, EmulatorCrashedError


def main() -> None:
    config_path = PROJECT_ROOT / "config.json"
    config = json.loads(config_path.read_text())

    rom_path = (
        sys.argv[1]
        if len(sys.argv) > 1
        else config.get("emulator", {}).get("rom_path", "")
    )
    if not rom_path:
        print("Error: provide <rom_path> as an argument or set emulator.rom_path in config.json")
        sys.exit(1)

    bridge = EmulatorBridge(config)
    print(f"Starting FCEUX: {rom_path}")
    bridge.start(rom_path)
    print("Lua bridge ready.")
    print()
    print("Now open Claude Desktop and start a new conversation.")
    print("The 'earthbound-zero' MCP tools will be available automatically.")
    print("Paste docs/system_prompt.md as your first message to begin playing.")
    print()
    print("Press Ctrl+C to stop FCEUX.")

    try:
        while bridge.is_alive():
            time.sleep(1)
        print("FCEUX exited.")
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        bridge.stop()


if __name__ == "__main__":
    main()

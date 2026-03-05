"""MCP server for the EarthBound Zero AI Player.

Wraps EmulatorBridge in 6 MCP tools Claude can call to observe game state
and control the emulator. Uses FastMCP with stdio transport.

Start with: python -m src.mcp_server
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from src.bridge.emulator_bridge import (
    BridgeTimeoutError,
    EmulatorCrashedError,
    GameState as RawGameState,
    StaleStateError,
    EmulatorBridge,
)
from src.mcp_server.validation import validate_action
from src.state_parser.models import (
    ActionResult,
    FullGameState,
    KnowledgeBaseResult,
    MemoryValueResult,
    RestoreStateResult,
    SaveStateResult,
)
from src.state_parser.parser import GameStateParser, detect_game_mode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known address reverse-lookup for get_memory_value
# Maps lowercase hex address → (RawGameState field name, byte length)
# ---------------------------------------------------------------------------
KNOWN_ADDRESSES: dict[str, tuple[str, int]] = {
    "0x000c": ("player_direction", 1),
    "0x0015": ("map_id", 1),
    "0x0018": ("player_x", 2),
    "0x001a": ("player_y", 2),
    "0x00a0": ("movement_state", 1),
    "0x0047": ("combat_active", 1),
    "0x0048": ("enemy_group_id", 1),
    "0x7441": ("ninten_status", 1),
    "0x7443": ("ninten_max_hp", 2),
    "0x7445": ("ninten_max_pp", 2),
    "0x7450": ("ninten_level", 1),
    "0x7451": ("ninten_exp", 3),
    "0x7454": ("ninten_hp", 2),
    "0x7456": ("ninten_pp", 2),
}


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _load_config() -> dict[str, Any]:
    config_path = Path(__file__).resolve().parent.parent.parent / "config.json"
    with open(config_path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Lifespan — creates shared resources for the server's lifetime
# ---------------------------------------------------------------------------

@asynccontextmanager
async def app_lifespan(app: FastMCP):
    """Initialise bridge, parser, and config. Clean up on shutdown."""
    config = _load_config()
    bridge = EmulatorBridge(config)
    parser = GameStateParser()

    ctx_data: dict[str, Any] = {
        "bridge": bridge,
        "parser": parser,
        "config": config,
        "last_action_time": 0.0,
        "action_lock": asyncio.Lock(),
    }

    yield ctx_data

    if bridge.is_alive():
        bridge.stop()


# ---------------------------------------------------------------------------
# FastMCP server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="earthbound-zero-ai",
    instructions=(
        "MCP server for playing EarthBound Zero (Mother 1) on NES via FCEUX emulator. "
        "Call get_game_state to observe the current state, execute_action to send controller "
        "input, and create_save_state/restore_save_state to manage checkpoints. "
        "FCEUX must already be running with the Lua bridge loaded before calling tools."
    ),
    lifespan=app_lifespan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _deps(ctx: Context) -> tuple[EmulatorBridge, GameStateParser, dict[str, Any]]:
    lc = ctx.request_context.lifespan_context
    return lc["bridge"], lc["parser"], lc["config"]


async def _enforce_rate_limit(ctx: Context) -> None:
    """Sleep if less than rate_limit_ms has elapsed since the last execute_action."""
    lc = ctx.request_context.lifespan_context
    rate_s = lc["config"]["mcp_server"]["rate_limit_ms"] / 1000.0
    async with lc["action_lock"]:
        elapsed = time.monotonic() - lc["last_action_time"]
        if elapsed < rate_s:
            await asyncio.sleep(rate_s - elapsed)
        lc["last_action_time"] = time.monotonic()


def _build_full_state(
    bridge: EmulatorBridge,
    parser: GameStateParser,
    include_screenshot: bool,
) -> FullGameState:
    raw: RawGameState = bridge.get_state()
    screenshot_b64 = bridge.capture_screenshot() if include_screenshot else None
    return parser.build_state(raw, screenshot_b64)


# ---------------------------------------------------------------------------
# Tool 1: get_game_state
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_game_state",
    description=(
        "Returns the complete current game state: player stats, location, game mode "
        "(overworld/battle/menu/dialog), and optionally a screenshot. "
        "Pass include_screenshot=false to skip the screenshot and save tokens."
    ),
)
async def get_game_state(
    include_screenshot: bool = True,
    ctx: Context = None,
) -> dict[str, Any]:
    bridge, parser, config = _deps(ctx)
    # Respect config default
    if not config["gameplay"].get("screenshot_by_default", True):
        include_screenshot = False
    try:
        state = _build_full_state(bridge, parser, include_screenshot)
        return state.model_dump(mode="json", exclude_none=True)
    except EmulatorCrashedError as e:
        return {"error": f"Emulator not running: {e}"}
    except StaleStateError as e:
        return {"error": f"State unavailable: {e}"}
    except BridgeTimeoutError as e:
        return {"error": f"Timeout reading state: {e}"}


# ---------------------------------------------------------------------------
# Tool 2: execute_action
# ---------------------------------------------------------------------------

@mcp.tool(
    name="execute_action",
    description=(
        "Sends a controller action to the emulator and returns the resulting state.\n"
        "action_type options:\n"
        "  move            — direction (up/down/left/right) + duration_frames\n"
        "  button          — button (A/B/Start/Select) + optional duration_frames\n"
        "  menu_navigate   — menu_path list (e.g. ['GOODS', 'Bread'])\n"
        "  text_advance    — presses A to advance dialog\n"
        "  wait            — idles for duration_frames without input\n"
        "Returns {success, action_performed, game_state}."
    ),
)
async def execute_action(
    action_type: str,
    direction: str | None = None,
    button: str | None = None,
    menu_path: list[str] | None = None,
    duration_frames: int = 2,
    include_screenshot: bool = True,
    ctx: Context = None,
) -> dict[str, Any]:
    bridge, parser, config = _deps(ctx)

    await _enforce_rate_limit(ctx)

    max_frames = config["mcp_server"]["max_action_duration_frames"]
    duration_frames = min(duration_frames, max_frames)

    # Read current mode for validation
    try:
        raw = bridge.get_state()
    except (EmulatorCrashedError, StaleStateError, BridgeTimeoutError) as e:
        return {"success": False, "error": str(e), "game_state": None}

    current_mode = detect_game_mode(raw)

    errors = validate_action(
        action_type=action_type,
        game_mode=current_mode,
        direction=direction,
        button=button,
        menu_path=menu_path,
        duration_frames=duration_frames,
    )
    if errors:
        return {"success": False, "error": "; ".join(errors), "game_state": None}

    # Execute
    try:
        description = _dispatch_action(
            bridge, action_type, direction, button, menu_path, duration_frames
        )
    except (EmulatorCrashedError, BridgeTimeoutError) as e:
        return {"success": False, "error": str(e), "game_state": None}

    # Read result state
    try:
        result_state = _build_full_state(bridge, parser, include_screenshot)
    except (EmulatorCrashedError, StaleStateError, BridgeTimeoutError) as e:
        return {
            "success": True,
            "action_performed": description,
            "error": f"Action executed but state read failed: {e}",
            "game_state": None,
        }

    return ActionResult(
        success=True,
        action_performed=description,
        game_state=result_state,
    ).model_dump(mode="json", exclude_none=True)


def _dispatch_action(
    bridge: EmulatorBridge,
    action_type: str,
    direction: str | None,
    button: str | None,
    menu_path: list[str] | None,
    duration_frames: int,
) -> str:
    """Send the appropriate bridge command(s) and return a description string."""
    if action_type == "move":
        bridge.send_input(command="move", direction=direction, duration_frames=duration_frames)
        return f"move {direction} for {duration_frames} frames"

    if action_type == "button":
        bridge.send_input(command="button", button=button, duration_frames=duration_frames)
        return f"press {button} for {duration_frames} frames"

    if action_type == "text_advance":
        bridge.send_input(command="button", button="A", duration_frames=2)
        return "text_advance (press A)"

    if action_type == "menu_navigate":
        # Phase 2 stub: press A for each menu path entry
        # Full cursor-aware navigation is Phase 3
        for entry in (menu_path or []):
            bridge.send_input(command="button", button="A", duration_frames=4)
        path_str = " -> ".join(menu_path or [])
        return f"menu_navigate: {path_str}"

    if action_type == "wait":
        bridge.send_input(command="wait", duration_frames=duration_frames)
        return f"wait {duration_frames} frames"

    return f"unknown action: {action_type}"


# ---------------------------------------------------------------------------
# Tool 3: create_save_state
# ---------------------------------------------------------------------------

@mcp.tool(
    name="create_save_state",
    description="Creates a labeled emulator save state checkpoint for later restoration.",
)
async def create_save_state(label: str, ctx: Context = None) -> dict[str, Any]:
    bridge, parser, _ = _deps(ctx)
    try:
        state_id = bridge.create_save_state(label)
        state = _build_full_state(bridge, parser, include_screenshot=False)
        summary = (
            f"Ninten Lv{state.player.level} "
            f"HP:{state.player.hp}/{state.player.max_hp} "
            f"at {state.location.map_name} ({state.location.x},{state.location.y})"
        )
        return SaveStateResult(
            save_state_id=state_id,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            game_state_summary=summary,
        ).model_dump(mode="json")
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool 4: restore_save_state
# ---------------------------------------------------------------------------

@mcp.tool(
    name="restore_save_state",
    description="Restores the emulator to a previously created save state checkpoint.",
)
async def restore_save_state(save_state_id: str, ctx: Context = None) -> dict[str, Any]:
    bridge, parser, _ = _deps(ctx)
    try:
        bridge.restore_save_state(save_state_id)
        await asyncio.sleep(0.2)  # Let emulator settle after restore
        state = _build_full_state(bridge, parser, include_screenshot=False)
        return RestoreStateResult(success=True, restored_state=state).model_dump(
            mode="json", exclude_none=True
        )
    except Exception as e:
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Tool 5: get_memory_value (debug)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_memory_value",
    description=(
        "Reads raw NES RAM at a known address. For debugging only. "
        f"Readable addresses: {', '.join(sorted(KNOWN_ADDRESSES.keys()))}"
    ),
)
async def get_memory_value(
    address: str,
    length: int = 1,
    ctx: Context = None,
) -> dict[str, Any]:
    bridge, _, _ = _deps(ctx)
    addr = address.lower()
    if not addr.startswith("0x"):
        addr = "0x" + addr

    if addr not in KNOWN_ADDRESSES:
        return {
            "error": (
                f"Address {address} is not mapped. "
                f"Known: {', '.join(sorted(KNOWN_ADDRESSES.keys()))}"
            )
        }

    field_name, byte_len = KNOWN_ADDRESSES[addr]
    try:
        raw = bridge.get_state()
        value: int = getattr(raw, field_name, 0)
        num_bytes = max(byte_len, length)
        raw_bytes = value.to_bytes(num_bytes, byteorder="little")
        return MemoryValueResult(
            address=addr,
            hex=raw_bytes[:length].hex().upper(),
            decimal=list(raw_bytes[:length]),
        ).model_dump(mode="json")
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool 6: update_knowledge_base (Phase 4 stub)
# ---------------------------------------------------------------------------

@mcp.tool(
    name="update_knowledge_base",
    description=(
        "Read, write, or delete entries in Claude's persistent knowledge base. "
        "Sections: map_data, npc_notes, battle_strategies, inventory, objectives, death_log. "
        "(Not yet implemented — coming in Phase 4.)"
    ),
)
async def update_knowledge_base(
    operation: str,
    section: str | None = None,
    key: str | None = None,
    value: str | None = None,
    ctx: Context = None,
) -> dict[str, Any]:
    return KnowledgeBaseResult(
        error="Knowledge base not yet implemented. Coming in Phase 4."
    ).model_dump(mode="json", exclude_none=True)

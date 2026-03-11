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
from src.bridge.auto_checkpoint import AutoCheckpoint
from src.knowledge_base.kb import KnowledgeBase
from src.knowledge_base.session import SessionManager
from src.mcp_server.performance import DeathContext, PerformanceTracker
from src.mcp_server.screenshot_policy import ScreenshotPolicy
from src.mcp_server.validation import validate_action
from src.state_parser.enemy_names import get_enemy_name
from src.state_parser.models import (
    ActionResult,
    FullGameState,
    KnowledgeBaseResult,
    MemoryValueResult,
    ProgressSummaryResult,
    RestoreStateResult,
    SaveStateResult,
    SessionListResult,
    SessionRestoreResult,
    SessionSaveResult,
    SessionStatsResult,
)
from src.state_parser.parser import GameStateParser, detect_game_mode

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known address reverse-lookup for get_memory_value
# Maps lowercase hex address → (RawGameState field name, byte length)
# ---------------------------------------------------------------------------
KNOWN_ADDRESSES: dict[str, tuple[str, int]] = {
    # Overworld / combat (internal RAM)
    "0x000c": ("player_direction", 1),
    "0x0015": ("map_id", 1),
    "0x0018": ("player_x", 2),
    "0x001a": ("player_y", 2),
    "0x00a0": ("movement_state", 1),
    "0x0047": ("combat_active", 1),
    "0x0048": ("enemy_group_id", 1),
    # Ninten (SRAM Last Save block)
    "0x7441": ("ninten_status", 1),
    "0x7443": ("ninten_max_hp", 2),
    "0x7445": ("ninten_max_pp", 2),
    "0x7450": ("ninten_level", 1),
    "0x7451": ("ninten_exp", 3),
    "0x7454": ("ninten_hp", 2),
    "0x7456": ("ninten_pp", 2),
    # Party allies (Phase 5)
    "0x7481": ("ana_status", 1),
    "0x7483": ("ana_max_hp", 2),
    "0x7485": ("ana_max_pp", 2),
    "0x7490": ("ana_level", 1),
    "0x7494": ("ana_hp", 2),
    "0x7496": ("ana_pp", 2),
    "0x74c1": ("lloyd_status", 1),
    "0x74c3": ("lloyd_max_hp", 2),
    "0x74d0": ("lloyd_level", 1),
    "0x74d4": ("lloyd_hp", 2),
    "0x7501": ("teddy_status", 1),
    "0x7503": ("teddy_max_hp", 2),
    "0x7510": ("teddy_level", 1),
    "0x7514": ("teddy_hp", 2),
    # Economy / progress (Phase 5)
    "0x7410": ("money", 2),
    "0x761e": ("melodies", 1),
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
    kb = KnowledgeBase(config["knowledge_base"]["save_path"])
    session_mgr = SessionManager(
        sessions_dir=config["knowledge_base"]["sessions_dir"],
        kb=kb,
        summarization_threshold=config["gameplay"]["summarization_threshold_tool_calls"],
    )
    auto_cp = AutoCheckpoint(
        bridge=bridge,
        interval_minutes=config["gameplay"]["auto_checkpoint_interval_minutes"],
        enabled=config["gameplay"]["auto_checkpoint_on_new_map"],
    )
    performance = PerformanceTracker()
    screenshot_policy = ScreenshotPolicy(
        enabled=config["gameplay"].get("smart_screenshot_policy", False),
        force_interval=config["gameplay"].get("screenshot_policy_interval", 20),
    )

    ctx_data: dict[str, Any] = {
        "bridge": bridge,
        "parser": parser,
        "config": config,
        "kb": kb,
        "session_mgr": session_mgr,
        "auto_cp": auto_cp,
        "performance": performance,
        "screenshot_policy": screenshot_policy,
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


def _track_call(ctx: Context) -> None:
    """Increment the session tool call counter. Call at start of every tool handler."""
    ctx.request_context.lifespan_context["session_mgr"].increment_tool_calls()


def _build_full_state(
    bridge: EmulatorBridge,
    parser: GameStateParser,
    include_screenshot: bool,
    policy: ScreenshotPolicy | None = None,
) -> FullGameState:
    raw: RawGameState = bridge.get_state()
    if policy is not None:
        # True → policy decides (caller_explicit=None); False → explicit skip
        caller_explicit = False if not include_screenshot else None
        actual_screenshot = policy.should_include(
            caller_explicit=caller_explicit,
            game_mode=detect_game_mode(raw).value,
            map_id=raw.map_id,
        )
    else:
        actual_screenshot = include_screenshot
    screenshot_b64 = bridge.capture_screenshot() if actual_screenshot else None
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
    _track_call(ctx)
    bridge, parser, _ = _deps(ctx)
    lc = ctx.request_context.lifespan_context
    policy: ScreenshotPolicy = lc["screenshot_policy"]
    try:
        state = _build_full_state(bridge, parser, include_screenshot, policy=policy)
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
    _track_call(ctx)
    lc = ctx.request_context.lifespan_context
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
    policy: ScreenshotPolicy = lc["screenshot_policy"]
    try:
        result_state = _build_full_state(bridge, parser, include_screenshot, policy=policy)
    except (EmulatorCrashedError, StaleStateError, BridgeTimeoutError) as e:
        return {
            "success": False,
            "action_performed": description,
            "error": f"Action executed but state read failed: {e}",
            "game_state": None,
        }

    # Auto-checkpoint: check if we should save (new map, healed full, periodic timer)
    auto_cp: AutoCheckpoint = lc["auto_cp"]
    auto_cp.check_and_save(
        map_id=result_state.location.map_id,
        hp=result_state.player.hp,
        max_hp=result_state.player.max_hp,
    )

    # Performance tracking
    tracker: PerformanceTracker = lc["performance"]

    # Death detection with context for post-mortem analysis
    if result_state.player.hp == 0:
        auto_cp.check_game_over(0)
        death_ctx = DeathContext(
            enemy_group_id=raw.enemy_group_id,
            enemy_name=get_enemy_name(raw.enemy_group_id) if raw.enemy_group_id else "Unknown",
            map_id=result_state.location.map_id,
            map_name=result_state.location.map_name,
            ninten_hp_at_death=result_state.player.hp,
            ninten_max_hp=result_state.player.max_hp,
            party_hp=[(m.name, m.hp, m.max_hp) for m in result_state.party],
        )
        tracker.record_death_with_context(death_ctx)
        kb: KnowledgeBase = lc["kb"]
        death_desc = (
            f"Died to {death_ctx.enemy_name} in {death_ctx.map_name} "
            f"(HP: {death_ctx.ninten_hp_at_death}/{death_ctx.ninten_max_hp})"
        )
        kb.write("death_log", f"death_{tracker.deaths}", death_desc)
    tracker.update_position(result_state.location.x, result_state.location.y)
    new_mode = result_state.game_mode.value
    transition = tracker.update_game_mode(new_mode)
    if transition == "ended":
        # Battle just ended — determine outcome from the action that ended it
        if action_type == "menu_navigate" and menu_path and "RUN" in (menu_path or []):
            tracker.record_battle_result("fled")
        elif result_state.player.hp > 0:
            tracker.record_battle_result("won")
        else:
            tracker.record_battle_result("lost")

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
    _track_call(ctx)
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
    _track_call(ctx)
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
    _track_call(ctx)
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
        "Read, write, delete, or list entries in Claude's persistent knowledge base. "
        "Sections: map_data, npc_notes, battle_strategies, inventory, objectives, death_log. "
        "Values are natural language strings. Keys should be snake_case descriptors."
    ),
)
async def update_knowledge_base(
    operation: str,
    section: str | None = None,
    key: str | None = None,
    value: str | None = None,
    ctx: Context = None,
) -> dict[str, Any]:
    _track_call(ctx)
    lc = ctx.request_context.lifespan_context
    kb: KnowledgeBase = lc["kb"]

    try:
        if operation == "list_sections":
            return KnowledgeBaseResult(
                sections=kb.list_sections()
            ).model_dump(mode="json", exclude_none=True)

        if operation == "read":
            if not section or not key:
                return KnowledgeBaseResult(
                    error="'read' requires section and key."
                ).model_dump(mode="json", exclude_none=True)
            val = kb.read(section, key)
            return KnowledgeBaseResult(
                section=section, key=key, value=val
            ).model_dump(mode="json", exclude_none=True)

        if operation == "write":
            if not section or not key or value is None:
                return KnowledgeBaseResult(
                    error="'write' requires section, key, and value."
                ).model_dump(mode="json", exclude_none=True)
            kb.write(section, key, value)
            return KnowledgeBaseResult(
                section=section, key=key, value=value
            ).model_dump(mode="json", exclude_none=True)

        if operation == "delete":
            if not section or not key:
                return KnowledgeBaseResult(
                    error="'delete' requires section and key."
                ).model_dump(mode="json", exclude_none=True)
            kb.delete(section, key)
            return KnowledgeBaseResult(
                section=section, key=key
            ).model_dump(mode="json", exclude_none=True)

        return KnowledgeBaseResult(
            error=f"Unknown operation '{operation}'. Use: read, write, delete, list_sections."
        ).model_dump(mode="json", exclude_none=True)

    except ValueError as e:
        return KnowledgeBaseResult(error=str(e)).model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# Tool 7: get_session_stats
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_session_stats",
    description=(
        "Returns session statistics: how many MCP tool calls have been made this conversation, "
        "the summarization threshold, and whether Claude should write a progress summary. "
        "Check this every ~10 actions. When should_summarize is true, call write_progress_summary."
    ),
)
async def get_session_stats(ctx: Context = None) -> dict[str, Any]:
    _track_call(ctx)
    lc = ctx.request_context.lifespan_context
    session_mgr: SessionManager = lc["session_mgr"]
    stats = session_mgr.get_session_stats()
    return SessionStatsResult(
        tool_call_count=stats["tool_call_count"],
        summarization_threshold=stats["summarization_threshold"],
        should_summarize=stats["should_summarize"],
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Tool 8: write_progress_summary
# ---------------------------------------------------------------------------

@mcp.tool(
    name="write_progress_summary",
    description=(
        "Write a progress summary to disk for continuity across conversations. "
        "Call this when get_session_stats says should_summarize is true. "
        "Include: current location, objectives completed, current goal, party status, "
        "notable discoveries. Retrieved via get_last_summary in future conversations."
    ),
)
async def write_progress_summary(summary: str, ctx: Context = None) -> dict[str, Any]:
    _track_call(ctx)
    lc = ctx.request_context.lifespan_context
    session_mgr: SessionManager = lc["session_mgr"]
    session_mgr.write_progress_summary(summary)
    return ProgressSummaryResult(
        summary=summary,
        message="Progress summary saved. Retrieve it with get_last_summary in future sessions.",
    ).model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# Tool 9: get_last_summary
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_last_summary",
    description=(
        "Retrieve the most recent progress summary from a previous session. "
        "Call this at the START of every new conversation to restore context. "
        "Returns null summary if no summary has been written yet."
    ),
)
async def get_last_summary(ctx: Context = None) -> dict[str, Any]:
    _track_call(ctx)
    lc = ctx.request_context.lifespan_context
    session_mgr: SessionManager = lc["session_mgr"]
    summary = session_mgr.get_last_summary()
    if summary:
        return ProgressSummaryResult(summary=summary).model_dump(mode="json", exclude_none=True)
    return ProgressSummaryResult(
        message="No previous progress summary found. This appears to be the first session.",
    ).model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# Tool 10: save_session
# ---------------------------------------------------------------------------

@mcp.tool(
    name="save_session",
    description=(
        "Save a complete session bundle: emulator save state + knowledge base snapshot + "
        "progress summary. Use before ending a long session or when instructed to save progress. "
        "Restore later with restore_session. List saved sessions with list_sessions."
    ),
)
async def save_session(name: str, ctx: Context = None) -> dict[str, Any]:
    _track_call(ctx)
    lc = ctx.request_context.lifespan_context
    bridge: EmulatorBridge = lc["bridge"]
    parser: GameStateParser = lc["parser"]
    session_mgr: SessionManager = lc["session_mgr"]

    # Try to create an emulator save state for this session
    save_state_id: str | None = None
    game_summary = "(emulator unavailable)"
    try:
        save_state_id = bridge.create_save_state(f"session_{name}")
        state = _build_full_state(bridge, parser, include_screenshot=False)
        game_summary = (
            f"Ninten Lv{state.player.level} "
            f"HP:{state.player.hp}/{state.player.max_hp} "
            f"at {state.location.map_name} ({state.location.x},{state.location.y})"
        )
    except Exception as e:
        logger.warning("Could not create emulator save state during save_session: %s", e)

    session_data = session_mgr.save_session(
        name=name,
        save_state_id=save_state_id,
        game_state_summary=game_summary,
    )
    return SessionSaveResult(
        session_id=session_data.session_id,
        timestamp=session_data.timestamp,
        game_state_summary=session_data.game_state_summary,
        tool_call_count=session_data.tool_call_count,
    ).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Tool 11: list_sessions
# ---------------------------------------------------------------------------

@mcp.tool(
    name="list_sessions",
    description="List all saved sessions with their metadata, sorted newest first.",
)
async def list_sessions(ctx: Context = None) -> dict[str, Any]:
    _track_call(ctx)
    lc = ctx.request_context.lifespan_context
    session_mgr: SessionManager = lc["session_mgr"]
    return SessionListResult(sessions=session_mgr.list_sessions()).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Tool 12: restore_session
# ---------------------------------------------------------------------------

@mcp.tool(
    name="restore_session",
    description=(
        "Restore a previously saved session: reloads the knowledge base snapshot and "
        "emulator save state. Returns the session's progress summary for context. "
        "Call list_sessions first to see available session IDs."
    ),
)
async def restore_session(session_id: str, ctx: Context = None) -> dict[str, Any]:
    _track_call(ctx)
    lc = ctx.request_context.lifespan_context
    bridge: EmulatorBridge = lc["bridge"]
    session_mgr: SessionManager = lc["session_mgr"]

    try:
        session_data = session_mgr.restore_session(session_id)
    except FileNotFoundError:
        return SessionRestoreResult(
            success=False,
            session_id=session_id,
            game_state_summary="",
            error=f"Session '{session_id}' not found.",
        ).model_dump(mode="json", exclude_none=True)

    # Restore emulator save state if available
    if session_data.save_state_id:
        try:
            bridge.restore_save_state(session_data.save_state_id)
        except Exception as e:
            return SessionRestoreResult(
                success=False,
                session_id=session_id,
                game_state_summary=session_data.game_state_summary,
                progress_summary=session_data.progress_summary or None,
                error=f"KB restored but emulator restore failed: {e}",
            ).model_dump(mode="json", exclude_none=True)

    return SessionRestoreResult(
        success=True,
        session_id=session_id,
        game_state_summary=session_data.game_state_summary,
        progress_summary=session_data.progress_summary or None,
    ).model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# Tool 13: get_performance_dashboard
# ---------------------------------------------------------------------------

@mcp.tool(
    name="get_performance_dashboard",
    description=(
        "Returns gameplay performance metrics for the current session: "
        "battle win/loss/fled counts, win rate, deaths, tiles traveled, and elapsed time. "
        "Check periodically (every ~20 actions) to monitor progress. "
        "If win rate drops below 50%, consider updating battle_strategies in the knowledge base."
    ),
)
async def get_performance_dashboard(ctx: Context = None) -> dict[str, Any]:
    _track_call(ctx)
    lc = ctx.request_context.lifespan_context
    tracker: PerformanceTracker = lc["performance"]
    return tracker.get_dashboard()

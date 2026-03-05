"""Integration tests for MCP server tool handlers.

These tests call the async tool handler functions directly with mock MCP
contexts, verifying that each tool returns well-formed responses without
requiring a live emulator.

The mock context pattern:
    ctx.request_context.lifespan_context == a dict with the same keys
    that app_lifespan populates (bridge, parser, config, kb, session_mgr,
    auto_cp, performance, last_action_time, action_lock).
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from src.bridge.auto_checkpoint import AutoCheckpoint
from src.bridge.emulator_bridge import (
    EmulatorCrashedError,
    GameState,
    EmulatorBridge,
)
from src.knowledge_base.kb import KnowledgeBase
from src.knowledge_base.session import SessionManager
from src.mcp_server import server as srv
from src.mcp_server.performance import PerformanceTracker
from src.state_parser.parser import GameStateParser


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_CONFIG = {
    "mcp_server": {"rate_limit_ms": 0, "max_action_duration_frames": 120},
    "gameplay": {
        "screenshot_by_default": True,
        "heal_threshold_hp_percent": 30,
        "auto_checkpoint_on_new_map": False,
        "auto_checkpoint_interval_minutes": 999,
        "summarization_threshold_tool_calls": 50,
    },
    "knowledge_base": {
        "save_path": "data/knowledge_base.json",
        "sessions_dir": "data/sessions",
    },
}

OVERWORLD_STATE = GameState(
    frame=100,
    map_id=0,
    player_x=10,
    player_y=20,
    ninten_hp=68,
    ninten_max_hp=68,
    ninten_level=1,
    combat_active=0,
)

BATTLE_STATE = GameState(
    frame=200,
    map_id=0,
    player_x=10,
    player_y=20,
    ninten_hp=40,
    ninten_max_hp=68,
    ninten_level=2,
    combat_active=1,  # Note: Lua inverts this; parser expects 1=battle
    enemy_group_id=1,
)


def make_mock_bridge(state: GameState = OVERWORLD_STATE) -> MagicMock:
    bridge = MagicMock(spec=EmulatorBridge)
    bridge.get_state.return_value = state
    bridge.capture_screenshot.return_value = None
    bridge.create_save_state.return_value = "ss_test_001"
    bridge.restore_save_state.return_value = None
    bridge.is_alive.return_value = True
    return bridge


def make_ctx(tmp_path, state: GameState = OVERWORLD_STATE) -> MagicMock:
    bridge = make_mock_bridge(state)
    parser = GameStateParser()
    kb = KnowledgeBase(tmp_path / "kb.json")
    session_mgr = SessionManager(
        sessions_dir=tmp_path / "sessions",
        kb=kb,
        summarization_threshold=50,
    )
    auto_cp = AutoCheckpoint(bridge=bridge, interval_minutes=999, enabled=False)

    lc = {
        "bridge": bridge,
        "parser": parser,
        "config": MINIMAL_CONFIG,
        "kb": kb,
        "session_mgr": session_mgr,
        "auto_cp": auto_cp,
        "performance": PerformanceTracker(),
        "last_action_time": 0.0,
        "action_lock": asyncio.Lock(),
    }

    ctx = MagicMock()
    ctx.request_context.lifespan_context = lc
    return ctx


# ---------------------------------------------------------------------------
# Tool: get_game_state
# ---------------------------------------------------------------------------

class TestGetGameState:
    @pytest.mark.asyncio
    async def test_returns_valid_game_state(self, tmp_path):
        ctx = make_ctx(tmp_path, OVERWORLD_STATE)
        result = await srv.get_game_state(include_screenshot=False, ctx=ctx)
        assert "game_mode" in result
        assert result["game_mode"] == "overworld"
        assert result["player"]["hp"] == 68

    @pytest.mark.asyncio
    async def test_battle_mode_detected(self, tmp_path):
        # combat_active=1 maps to battle in the parser
        ctx = make_ctx(tmp_path, BATTLE_STATE)
        result = await srv.get_game_state(include_screenshot=False, ctx=ctx)
        assert result["game_mode"] == "battle"

    @pytest.mark.asyncio
    async def test_emulator_crashed_returns_error(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.request_context.lifespan_context["bridge"].get_state.side_effect = (
            EmulatorCrashedError("FCEUX died")
        )
        result = await srv.get_game_state(include_screenshot=False, ctx=ctx)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_increments_tool_call_count(self, tmp_path):
        ctx = make_ctx(tmp_path)
        session_mgr = ctx.request_context.lifespan_context["session_mgr"]
        assert session_mgr.tool_call_count == 0
        await srv.get_game_state(include_screenshot=False, ctx=ctx)
        assert session_mgr.tool_call_count == 1


# ---------------------------------------------------------------------------
# Tool: execute_action
# ---------------------------------------------------------------------------

class TestExecuteAction:
    @pytest.mark.asyncio
    async def test_move_in_overworld_succeeds(self, tmp_path):
        ctx = make_ctx(tmp_path, OVERWORLD_STATE)
        result = await srv.execute_action(
            action_type="move", direction="right", duration_frames=5, ctx=ctx
        )
        assert result["success"] is True
        assert "right" in result["action_performed"]

    @pytest.mark.asyncio
    async def test_move_in_battle_rejected(self, tmp_path):
        ctx = make_ctx(tmp_path, BATTLE_STATE)
        result = await srv.execute_action(
            action_type="move", direction="right", duration_frames=5, ctx=ctx
        )
        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_button_press_returns_game_state(self, tmp_path):
        ctx = make_ctx(tmp_path, OVERWORLD_STATE)
        result = await srv.execute_action(
            action_type="button", button="A", ctx=ctx
        )
        assert result["success"] is True
        assert "game_state" in result

    @pytest.mark.asyncio
    async def test_state_read_failure_returns_success_false(self, tmp_path):
        ctx = make_ctx(tmp_path, OVERWORLD_STATE)
        bridge = ctx.request_context.lifespan_context["bridge"]
        # First call (pre-validation) succeeds, second call (post-action) fails
        bridge.get_state.side_effect = [
            OVERWORLD_STATE,
            EmulatorCrashedError("crashed after action"),
        ]
        result = await srv.execute_action(
            action_type="button", button="A", ctx=ctx
        )
        assert result["success"] is False
        assert "state read failed" in result["error"]

    @pytest.mark.asyncio
    async def test_duration_capped_at_max(self, tmp_path):
        ctx = make_ctx(tmp_path, OVERWORLD_STATE)
        # Request 999 frames — should be capped at 120
        result = await srv.execute_action(
            action_type="wait", duration_frames=999, ctx=ctx
        )
        assert result["success"] is True
        assert "120" in result["action_performed"]


# ---------------------------------------------------------------------------
# Tool: create_save_state / restore_save_state
# ---------------------------------------------------------------------------

class TestSaveStateTools:
    @pytest.mark.asyncio
    async def test_create_save_state_returns_id(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = await srv.create_save_state(label="test", ctx=ctx)
        assert "save_state_id" in result
        assert result["save_state_id"] == "ss_test_001"

    @pytest.mark.asyncio
    async def test_restore_save_state_returns_success(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = await srv.restore_save_state(save_state_id="ss_test_001", ctx=ctx)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_restore_save_state_error_returns_failure(self, tmp_path):
        ctx = make_ctx(tmp_path)
        ctx.request_context.lifespan_context["bridge"].restore_save_state.side_effect = (
            KeyError("unknown state id")
        )
        result = await srv.restore_save_state(save_state_id="bad_id", ctx=ctx)
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tool: get_memory_value
# ---------------------------------------------------------------------------

class TestGetMemoryValue:
    @pytest.mark.asyncio
    async def test_known_address_returns_value(self, tmp_path):
        ctx = make_ctx(tmp_path, OVERWORLD_STATE)
        result = await srv.get_memory_value(address="0x7454", ctx=ctx)  # ninten_hp
        assert "hex" in result
        assert "decimal" in result

    @pytest.mark.asyncio
    async def test_unknown_address_returns_error(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = await srv.get_memory_value(address="0x9999", ctx=ctx)
        assert "error" in result

    @pytest.mark.asyncio
    async def test_player_y_address_readable(self, tmp_path):
        ctx = make_ctx(tmp_path, OVERWORLD_STATE)
        result = await srv.get_memory_value(address="0x001a", ctx=ctx)
        assert "hex" in result


# ---------------------------------------------------------------------------
# Tool: update_knowledge_base
# ---------------------------------------------------------------------------

class TestUpdateKnowledgeBase:
    @pytest.mark.asyncio
    async def test_write_and_read(self, tmp_path):
        ctx = make_ctx(tmp_path)
        await srv.update_knowledge_base(
            operation="write", section="map_data", key="podunk", value="Small town", ctx=ctx
        )
        result = await srv.update_knowledge_base(
            operation="read", section="map_data", key="podunk", ctx=ctx
        )
        assert result["value"] == "Small town"

    @pytest.mark.asyncio
    async def test_list_sections_returns_counts(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = await srv.update_knowledge_base(operation="list_sections", ctx=ctx)
        assert "sections" in result
        assert "map_data" in result["sections"]

    @pytest.mark.asyncio
    async def test_invalid_section_returns_error(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = await srv.update_knowledge_base(
            operation="write", section="bad_section", key="k", value="v", ctx=ctx
        )
        assert "error" in result

    @pytest.mark.asyncio
    async def test_unknown_operation_returns_error(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = await srv.update_knowledge_base(operation="explode", ctx=ctx)
        assert "error" in result


# ---------------------------------------------------------------------------
# Tools: Session management
# ---------------------------------------------------------------------------

class TestSessionTools:
    @pytest.mark.asyncio
    async def test_get_session_stats_shape(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = await srv.get_session_stats(ctx=ctx)
        assert "tool_call_count" in result
        assert "summarization_threshold" in result
        assert "should_summarize" in result

    @pytest.mark.asyncio
    async def test_write_and_get_progress_summary(self, tmp_path):
        ctx = make_ctx(tmp_path)
        await srv.write_progress_summary(
            summary="At Podunk, Lv5, heading east.", ctx=ctx
        )
        result = await srv.get_last_summary(ctx=ctx)
        assert result["summary"] == "At Podunk, Lv5, heading east."

    @pytest.mark.asyncio
    async def test_get_last_summary_no_history_returns_message(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = await srv.get_last_summary(ctx=ctx)
        assert "message" in result
        assert result.get("summary") is None

    @pytest.mark.asyncio
    async def test_save_and_list_sessions(self, tmp_path):
        ctx = make_ctx(tmp_path)
        await srv.save_session(name="checkpoint1", ctx=ctx)
        result = await srv.list_sessions(ctx=ctx)
        assert len(result["sessions"]) == 1
        assert "checkpoint1" in result["sessions"][0]["session_id"]

    @pytest.mark.asyncio
    async def test_restore_nonexistent_session_returns_error(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = await srv.restore_session(session_id="nonexistent_abc", ctx=ctx)
        assert result["success"] is False
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# Phase 5: Extended state fields
# ---------------------------------------------------------------------------

PHASE5_STATE = GameState(
    frame=300,
    map_id=1,
    player_x=5,
    player_y=10,
    ninten_hp=50,
    ninten_max_hp=68,
    ninten_level=3,
    combat_active=0,
    # Party member present: Ana (party_0=1, max_hp>0)
    party_0=1,
    ana_hp=30,
    ana_max_hp=40,
    ana_pp=10,
    ana_max_pp=20,
    ana_level=3,
    ana_status=0,
    # Inventory: Bread in slot 0
    inv_0=1,
    # Economy
    money=250,
    melodies=0b00000011,  # 2 melodies
)


class TestPhase5GameState:
    @pytest.mark.asyncio
    async def test_get_game_state_includes_money(self, tmp_path):
        ctx = make_ctx(tmp_path, PHASE5_STATE)
        result = await srv.get_game_state(include_screenshot=False, ctx=ctx)
        assert "money" in result
        assert result["money"] == 250

    @pytest.mark.asyncio
    async def test_get_game_state_includes_melodies(self, tmp_path):
        ctx = make_ctx(tmp_path, PHASE5_STATE)
        result = await srv.get_game_state(include_screenshot=False, ctx=ctx)
        assert "melodies_collected" in result
        assert result["melodies_collected"] == 2

    @pytest.mark.asyncio
    async def test_get_game_state_includes_party(self, tmp_path):
        ctx = make_ctx(tmp_path, PHASE5_STATE)
        result = await srv.get_game_state(include_screenshot=False, ctx=ctx)
        assert "party" in result
        assert len(result["party"]) == 1
        assert result["party"][0]["name"] == "Ana"

    @pytest.mark.asyncio
    async def test_get_game_state_includes_inventory(self, tmp_path):
        ctx = make_ctx(tmp_path, PHASE5_STATE)
        result = await srv.get_game_state(include_screenshot=False, ctx=ctx)
        assert "inventory" in result
        assert "Bread" in result["inventory"]


class TestPerformanceDashboard:
    @pytest.mark.asyncio
    async def test_get_performance_dashboard_shape(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = await srv.get_performance_dashboard(ctx=ctx)
        assert "battles_won" in result
        assert "battles_lost" in result
        assert "battles_fled" in result
        assert "total_battles" in result
        assert "win_rate" in result
        assert "deaths" in result
        assert "distance_traveled_tiles" in result
        assert "session_elapsed_minutes" in result

    @pytest.mark.asyncio
    async def test_initial_dashboard_is_zeroed(self, tmp_path):
        ctx = make_ctx(tmp_path)
        result = await srv.get_performance_dashboard(ctx=ctx)
        assert result["battles_won"] == 0
        assert result["deaths"] == 0
        assert result["win_rate"] == 0.0

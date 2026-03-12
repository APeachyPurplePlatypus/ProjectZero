"""Full-stack scenario integration test.

Simulates a complete gameplay session with all Phase 5 features enabled:
ScreenshotPolicy, AutoCheckpoint, PerformanceTracker, DeathContext, and
SessionManager working together through chained MCP tool calls.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from src.bridge.auto_checkpoint import AutoCheckpoint
from src.bridge.emulator_bridge import GameState, EmulatorBridge
from src.knowledge_base.kb import KnowledgeBase
from src.knowledge_base.session import SessionManager
from src.mcp_server import server as srv
from src.mcp_server.performance import PerformanceTracker
from src.mcp_server.screenshot_policy import ScreenshotPolicy
from src.state_parser.parser import GameStateParser


# ---------------------------------------------------------------------------
# Stateful mock bridge — state can be swapped between tool calls
# ---------------------------------------------------------------------------

class StatefulBridge:
    """Mock bridge that returns a mutable current_state."""

    def __init__(self, initial: GameState):
        self.current_state = initial
        self.send_input_calls: list[dict] = []
        self.screenshot_calls = 0
        self._save_slots: dict[str, int] = {}
        self._next_slot = 1

    def get_state(self) -> GameState:
        return self.current_state

    def send_input(self, **kwargs) -> None:
        self.send_input_calls.append(kwargs)

    def capture_screenshot(self) -> str:
        self.screenshot_calls += 1
        return "screenshot_base64_data"

    def create_save_state(self, label: str) -> str:
        state_id = f"ss_{label}"
        self._save_slots[state_id] = self._next_slot
        self._next_slot += 1
        return state_id

    def restore_save_state(self, state_id: str) -> None:
        if state_id not in self._save_slots:
            raise ValueError(f"Unknown: {state_id}")

    def is_alive(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Game state presets
# ---------------------------------------------------------------------------

HOME = GameState(
    frame=100, map_id=0, player_x=10, player_y=20,
    ninten_hp=68, ninten_max_hp=68, ninten_pp=20, ninten_max_pp=20,
    ninten_level=5, combat_active=0, money=500, melodies=0,
)

HOME_MOVED = GameState(
    frame=200, map_id=0, player_x=15, player_y=20,
    ninten_hp=68, ninten_max_hp=68, ninten_pp=20, ninten_max_pp=20,
    ninten_level=5, combat_active=0, money=500, melodies=0,
)

PODUNK = GameState(
    frame=300, map_id=2, player_x=30, player_y=40,
    ninten_hp=68, ninten_max_hp=68, ninten_pp=20, ninten_max_pp=20,
    ninten_level=5, combat_active=0, money=500, melodies=0,
)

BATTLE = GameState(
    frame=400, map_id=2, player_x=30, player_y=40,
    ninten_hp=50, ninten_max_hp=68, ninten_pp=20, ninten_max_pp=20,
    ninten_level=5, combat_active=1, enemy_group_id=1, money=500, melodies=0,
)

BATTLE_WON = GameState(
    frame=500, map_id=2, player_x=30, player_y=40,
    ninten_hp=45, ninten_max_hp=68, ninten_pp=20, ninten_max_pp=20,
    ninten_level=5, combat_active=0, money=520, melodies=0,
)

DEAD = GameState(
    frame=600, map_id=2, player_x=30, player_y=40,
    ninten_hp=0, ninten_max_hp=68, ninten_pp=0, ninten_max_pp=20,
    ninten_level=5, combat_active=0, enemy_group_id=5, money=500, melodies=0,
)

REVIVED = GameState(
    frame=700, map_id=2, player_x=30, player_y=40,
    ninten_hp=68, ninten_max_hp=68, ninten_pp=20, ninten_max_pp=20,
    ninten_level=6, combat_active=0, money=500, melodies=1,
)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

def make_scenario_ctx(tmp_path, bridge: StatefulBridge):
    mock_bridge = MagicMock(spec=EmulatorBridge)
    mock_bridge.get_state.side_effect = lambda: bridge.get_state()
    mock_bridge.send_input.side_effect = lambda **kw: bridge.send_input(**kw)
    mock_bridge.capture_screenshot.side_effect = lambda: bridge.capture_screenshot()
    mock_bridge.create_save_state.side_effect = lambda l: bridge.create_save_state(l)
    mock_bridge.restore_save_state.side_effect = lambda s: bridge.restore_save_state(s)
    mock_bridge.is_alive.return_value = True

    parser = GameStateParser()
    kb = KnowledgeBase(tmp_path / "kb.json")
    session_mgr = SessionManager(
        sessions_dir=tmp_path / "sessions", kb=kb, summarization_threshold=50,
    )
    auto_cp = AutoCheckpoint(bridge=mock_bridge, interval_minutes=999, enabled=True)
    performance = PerformanceTracker()
    policy = ScreenshotPolicy(enabled=True, force_interval=20)

    lc = {
        "bridge": mock_bridge,
        "parser": parser,
        "config": {
            "mcp_server": {"rate_limit_ms": 0, "max_action_duration_frames": 120},
            "gameplay": {
                "screenshot_by_default": True, "heal_threshold_hp_percent": 30,
                "auto_checkpoint_on_new_map": True, "auto_checkpoint_interval_minutes": 999,
                "summarization_threshold_tool_calls": 50,
            },
            "knowledge_base": {"save_path": str(tmp_path / "kb.json"), "sessions_dir": str(tmp_path / "sessions")},
        },
        "kb": kb,
        "session_mgr": session_mgr,
        "auto_cp": auto_cp,
        "performance": performance,
        "screenshot_policy": policy,
        "last_action_time": 0.0,
        "action_lock": asyncio.Lock(),
    }
    ctx = MagicMock()
    ctx.request_context.lifespan_context = lc
    return ctx


# ---------------------------------------------------------------------------
# Scenario tests
# ---------------------------------------------------------------------------

class TestStartupAndOverworld:
    @pytest.mark.asyncio
    async def test_initial_state_at_nintens_house(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        result = await srv.get_game_state(include_screenshot=True, ctx=ctx)
        assert result["game_mode"] == "overworld"
        assert result["location"]["map_name"] == "Ninten's House"
        assert result["player"]["hp"] == 68
        assert result["player"]["level"] == 5

    @pytest.mark.asyncio
    async def test_first_get_game_state_includes_screenshot(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        result = await srv.get_game_state(include_screenshot=True, ctx=ctx)
        assert bridge.screenshot_calls == 1

    @pytest.mark.asyncio
    async def test_current_objective_present(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        result = await srv.get_game_state(include_screenshot=False, ctx=ctx)
        assert "current_objective" in result
        assert len(result["current_objective"]) > 0

    @pytest.mark.asyncio
    async def test_movement_updates_position(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        # First action sets up tracking
        await srv.execute_action("move", direction="right", duration_frames=15, ctx=ctx)
        bridge.current_state = HOME_MOVED
        result = await srv.execute_action("move", direction="right", duration_frames=15, ctx=ctx)
        tracker = ctx.request_context.lifespan_context["performance"]
        assert tracker.distance_traveled > 0

    @pytest.mark.asyncio
    async def test_routine_movement_skips_screenshot(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        await srv.get_game_state(include_screenshot=True, ctx=ctx)  # first action
        bridge.screenshot_calls = 0
        await srv.execute_action("move", direction="right", duration_frames=10, ctx=ctx)
        assert bridge.screenshot_calls == 0  # policy skipped

    @pytest.mark.asyncio
    async def test_invalid_action_rejected_in_overworld(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        result = await srv.execute_action("menu_navigate", menu_path=["BASH"], ctx=ctx)
        assert result["success"] is False


class TestBattleSequence:
    @pytest.mark.asyncio
    async def test_battle_entry_detected(self, tmp_path):
        bridge = StatefulBridge(BATTLE)
        ctx = make_scenario_ctx(tmp_path, bridge)
        result = await srv.get_game_state(include_screenshot=True, ctx=ctx)
        assert result["game_mode"] == "battle"
        assert result["battle_state"] is not None

    @pytest.mark.asyncio
    async def test_screenshot_on_mode_transition(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        await srv.get_game_state(include_screenshot=True, ctx=ctx)
        bridge.screenshot_calls = 0
        bridge.current_state = BATTLE
        await srv.get_game_state(include_screenshot=True, ctx=ctx)
        assert bridge.screenshot_calls == 1  # mode transition triggered screenshot

    @pytest.mark.asyncio
    async def test_button_press_in_battle(self, tmp_path):
        bridge = StatefulBridge(BATTLE)
        ctx = make_scenario_ctx(tmp_path, bridge)
        result = await srv.execute_action("button", button="A", ctx=ctx)
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_battle_win_recorded(self, tmp_path):
        bridge = StatefulBridge(BATTLE)
        ctx = make_scenario_ctx(tmp_path, bridge)
        # Enter battle
        await srv.execute_action("button", button="A", ctx=ctx)
        # Battle ends with win
        bridge.current_state = BATTLE_WON
        await srv.execute_action("button", button="A", ctx=ctx)
        tracker = ctx.request_context.lifespan_context["performance"]
        assert tracker.battles_won == 1


class TestDeathAndRecovery:
    @pytest.mark.asyncio
    async def test_death_detected_and_logged(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        await srv.execute_action("button", button="A", ctx=ctx)
        bridge.current_state = DEAD
        await srv.execute_action("button", button="A", ctx=ctx)
        kb = ctx.request_context.lifespan_context["kb"]
        assert kb.list_sections().get("death_log", 0) > 0

    @pytest.mark.asyncio
    async def test_death_context_has_enemy_info(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        await srv.execute_action("button", button="A", ctx=ctx)
        bridge.current_state = DEAD
        await srv.execute_action("button", button="A", ctx=ctx)
        tracker = ctx.request_context.lifespan_context["performance"]
        assert len(tracker._death_contexts) == 1
        assert tracker._death_contexts[0].map_name == "Podunk"

    @pytest.mark.asyncio
    async def test_repeated_death_not_double_counted(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        await srv.execute_action("button", button="A", ctx=ctx)
        bridge.current_state = DEAD
        await srv.execute_action("button", button="A", ctx=ctx)
        await srv.execute_action("button", button="A", ctx=ctx)
        tracker = ctx.request_context.lifespan_context["performance"]
        assert tracker.deaths == 1


class TestSessionManagement:
    @pytest.mark.asyncio
    async def test_save_session_captures_state(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        result = await srv.save_session(name="test_save", ctx=ctx)
        assert "session_id" in result

    @pytest.mark.asyncio
    async def test_restore_session_recovers_kb(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        kb = ctx.request_context.lifespan_context["kb"]
        kb.write("objectives", "current", "Go to Podunk")
        result = await srv.save_session(name="with_kb", ctx=ctx)
        session_id = result["session_id"]
        # Modify KB
        kb.write("objectives", "current", "Modified")
        # Restore
        await srv.restore_session(session_id=session_id, ctx=ctx)
        assert kb.read("objectives", "current") == "Go to Podunk"

    @pytest.mark.asyncio
    async def test_tool_call_count_tracks(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        await srv.get_game_state(include_screenshot=False, ctx=ctx)
        await srv.get_game_state(include_screenshot=False, ctx=ctx)
        result = await srv.get_session_stats(ctx=ctx)
        assert result["tool_call_count"] == 3  # 2 get_game_state + 1 get_session_stats


class TestPerformanceDashboard:
    @pytest.mark.asyncio
    async def test_dashboard_reflects_accumulated_stats(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        # Move around
        await srv.execute_action("move", direction="right", duration_frames=10, ctx=ctx)
        bridge.current_state = HOME_MOVED
        await srv.execute_action("move", direction="right", duration_frames=10, ctx=ctx)
        result = await srv.get_performance_dashboard(ctx=ctx)
        assert result["distance_traveled_tiles"] > 0
        assert result["deaths"] == 0
        assert result["total_battles"] == 0

    @pytest.mark.asyncio
    async def test_dashboard_includes_death_analysis_after_death(self, tmp_path):
        bridge = StatefulBridge(HOME)
        ctx = make_scenario_ctx(tmp_path, bridge)
        await srv.execute_action("button", button="A", ctx=ctx)
        bridge.current_state = DEAD
        await srv.execute_action("button", button="A", ctx=ctx)
        result = await srv.get_performance_dashboard(ctx=ctx)
        assert result["deaths"] == 1
        assert "death_analysis" in result
        assert result["death_analysis"]["total_deaths"] == 1

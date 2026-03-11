"""Unit tests for PerformanceTracker."""

from __future__ import annotations

import time

import pytest

from src.mcp_server.performance import DeathContext, PerformanceTracker


class TestInitialState:
    def test_initial_battles_zeroed(self):
        tracker = PerformanceTracker()
        assert tracker.battles_won == 0
        assert tracker.battles_lost == 0
        assert tracker.battles_fled == 0

    def test_initial_deaths_zero(self):
        tracker = PerformanceTracker()
        assert tracker.deaths == 0

    def test_initial_distance_zero(self):
        tracker = PerformanceTracker()
        assert tracker.distance_traveled == 0


class TestBattleRecording:
    def test_record_battle_won(self):
        tracker = PerformanceTracker()
        tracker.record_battle_result("won")
        assert tracker.battles_won == 1
        assert tracker.battles_lost == 0

    def test_record_battle_lost(self):
        tracker = PerformanceTracker()
        tracker.record_battle_result("lost")
        assert tracker.battles_lost == 1

    def test_record_battle_fled(self):
        tracker = PerformanceTracker()
        tracker.record_battle_result("fled")
        assert tracker.battles_fled == 1

    def test_record_multiple_results(self):
        tracker = PerformanceTracker()
        tracker.record_battle_result("won")
        tracker.record_battle_result("won")
        tracker.record_battle_result("lost")
        assert tracker.battles_won == 2
        assert tracker.battles_lost == 1

    def test_unknown_outcome_ignored(self):
        tracker = PerformanceTracker()
        tracker.record_battle_result("draw")  # not a valid outcome
        assert tracker.battles_won == 0
        assert tracker.battles_lost == 0
        assert tracker.battles_fled == 0


class TestDeathRecording:
    def test_record_death_increments(self):
        tracker = PerformanceTracker()
        tracker.record_death()
        assert tracker.deaths == 1

    def test_multiple_deaths(self):
        tracker = PerformanceTracker()
        tracker.record_death()
        tracker.record_death()
        tracker.record_death()
        assert tracker.deaths == 3


class TestPositionTracking:
    def test_first_update_no_distance(self):
        tracker = PerformanceTracker()
        tracker.update_position(10, 20)
        assert tracker.distance_traveled == 0  # No previous position

    def test_distance_accumulates(self):
        tracker = PerformanceTracker()
        tracker.update_position(0, 0)
        tracker.update_position(3, 4)  # Manhattan: |3| + |4| = 7
        assert tracker.distance_traveled == 7

    def test_stationary_no_distance(self):
        tracker = PerformanceTracker()
        tracker.update_position(5, 5)
        tracker.update_position(5, 5)
        assert tracker.distance_traveled == 0

    def test_large_jump_ignored(self):
        # Jumps > 20 tiles are map transitions — should not inflate distance
        tracker = PerformanceTracker()
        tracker.update_position(0, 0)
        tracker.update_position(100, 100)  # Jump = 200 tiles — ignored
        assert tracker.distance_traveled == 0

    def test_normal_movement_added(self):
        tracker = PerformanceTracker()
        tracker.update_position(10, 10)
        tracker.update_position(12, 10)  # dx=2, dy=0 → 2
        tracker.update_position(12, 15)  # dx=0, dy=5 → 5
        assert tracker.distance_traveled == 7


class TestDashboard:
    def test_dashboard_shape(self):
        tracker = PerformanceTracker()
        d = tracker.get_dashboard()
        assert "session_elapsed_minutes" in d
        assert "battles_won" in d
        assert "battles_lost" in d
        assert "battles_fled" in d
        assert "total_battles" in d
        assert "win_rate" in d
        assert "deaths" in d
        assert "distance_traveled_tiles" in d
        assert "distance_per_minute" in d

    def test_win_rate_no_battles_returns_zero(self):
        tracker = PerformanceTracker()
        d = tracker.get_dashboard()
        assert d["win_rate"] == 0.0

    def test_win_rate_calculation(self):
        tracker = PerformanceTracker()
        tracker.record_battle_result("won")
        tracker.record_battle_result("won")
        tracker.record_battle_result("won")
        tracker.record_battle_result("lost")
        d = tracker.get_dashboard()
        assert d["win_rate"] == pytest.approx(0.75)

    def test_total_battles_is_sum(self):
        tracker = PerformanceTracker()
        tracker.record_battle_result("won")
        tracker.record_battle_result("fled")
        d = tracker.get_dashboard()
        assert d["total_battles"] == 2

    def test_elapsed_time_is_positive(self):
        tracker = PerformanceTracker()
        time.sleep(0.01)
        d = tracker.get_dashboard()
        assert d["session_elapsed_minutes"] >= 0.0

    def test_dashboard_no_death_analysis_when_no_deaths(self):
        tracker = PerformanceTracker()
        d = tracker.get_dashboard()
        assert "death_analysis" not in d

    def test_dashboard_includes_death_analysis_when_deaths(self):
        tracker = PerformanceTracker()
        ctx = DeathContext(
            enemy_group_id=1, enemy_name="Lamp",
            map_id=2, map_name="Podunk",
            ninten_hp_at_death=0, ninten_max_hp=68,
            party_hp=[],
        )
        tracker.record_death_with_context(ctx)
        d = tracker.get_dashboard()
        assert "death_analysis" in d


# ---------------------------------------------------------------------------
# Death context and analysis
# ---------------------------------------------------------------------------

def _make_death(
    enemy_name: str = "Lamp",
    map_name: str = "Podunk",
    hp_at_death: int = 0,
    max_hp: int = 68,
) -> DeathContext:
    return DeathContext(
        enemy_group_id=1,
        enemy_name=enemy_name,
        map_id=2,
        map_name=map_name,
        ninten_hp_at_death=hp_at_death,
        ninten_max_hp=max_hp,
        party_hp=[],
    )


class TestDeathWithContext:
    def test_record_increments_deaths(self):
        tracker = PerformanceTracker()
        tracker.record_death_with_context(_make_death())
        assert tracker.deaths == 1

    def test_context_stored(self):
        tracker = PerformanceTracker()
        tracker.record_death_with_context(_make_death())
        assert len(tracker._death_contexts) == 1

    def test_multiple_contexts_stored(self):
        tracker = PerformanceTracker()
        tracker.record_death_with_context(_make_death(enemy_name="Lamp"))
        tracker.record_death_with_context(_make_death(enemy_name="Crow"))
        assert tracker.deaths == 2
        assert len(tracker._death_contexts) == 2


class TestDeathAnalysis:
    def test_no_contexts_returns_total(self):
        tracker = PerformanceTracker()
        analysis = tracker.get_death_analysis()
        assert analysis["total_deaths"] == 0

    def test_single_death_analysis(self):
        tracker = PerformanceTracker()
        tracker.record_death_with_context(_make_death())
        analysis = tracker.get_death_analysis()
        assert analysis["total_deaths"] == 1
        assert "Lamp" in analysis["deaths_by_enemy"]
        assert "Podunk" in analysis["deaths_by_location"]
        assert analysis["deadliest_enemy"] == "Lamp"

    def test_repeated_enemy_suggests_strategy(self):
        tracker = PerformanceTracker()
        for _ in range(3):
            tracker.record_death_with_context(_make_death(enemy_name="Gang Zombie"))
        analysis = tracker.get_death_analysis()
        assert any("Gang Zombie" in s for s in analysis["suggestions"])

    def test_repeated_area_suggests_grinding(self):
        tracker = PerformanceTracker()
        for _ in range(2):
            tracker.record_death_with_context(_make_death(map_name="Spookane"))
        analysis = tracker.get_death_analysis()
        assert any("Spookane" in s for s in analysis["suggestions"])

    def test_low_hp_death_suggests_healing(self):
        tracker = PerformanceTracker()
        tracker.record_death_with_context(_make_death(hp_at_death=5, max_hp=68))
        analysis = tracker.get_death_analysis()
        assert any("30%" in s or "Heal" in s for s in analysis["suggestions"])

    def test_recent_deaths_limited_to_five(self):
        tracker = PerformanceTracker()
        for i in range(8):
            tracker.record_death_with_context(_make_death(enemy_name=f"Enemy{i}"))
        analysis = tracker.get_death_analysis()
        assert len(analysis["recent_deaths"]) == 5

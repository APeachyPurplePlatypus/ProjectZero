"""Unit tests for PerformanceTracker."""

from __future__ import annotations

import time

import pytest

from src.mcp_server.performance import PerformanceTracker


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

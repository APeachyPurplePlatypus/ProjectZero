"""Unit tests for ScreenshotPolicy."""

from __future__ import annotations

from src.mcp_server.screenshot_policy import ScreenshotPolicy


class TestFirstAction:
    def test_first_action_always_includes(self):
        policy = ScreenshotPolicy()
        assert policy.should_include(game_mode="overworld", map_id=0) is True


class TestRoutineSkipping:
    def test_routine_overworld_skips(self):
        policy = ScreenshotPolicy()
        policy.should_include(game_mode="overworld", map_id=0)  # First: True
        assert policy.should_include(game_mode="overworld", map_id=0) is False

    def test_same_mode_same_map_skips(self):
        policy = ScreenshotPolicy()
        policy.should_include(game_mode="overworld", map_id=5)
        assert policy.should_include(game_mode="overworld", map_id=5) is False

    def test_consecutive_battle_actions_skip(self):
        policy = ScreenshotPolicy()
        policy.should_include(game_mode="battle", map_id=0)  # First: True
        assert policy.should_include(game_mode="battle", map_id=0) is False


class TestTransitionIncludes:
    def test_mode_transition_includes(self):
        policy = ScreenshotPolicy()
        policy.should_include(game_mode="overworld", map_id=0)
        assert policy.should_include(game_mode="battle", map_id=0) is True

    def test_battle_to_overworld_transition_includes(self):
        policy = ScreenshotPolicy()
        policy.should_include(game_mode="battle", map_id=0)
        assert policy.should_include(game_mode="overworld", map_id=0) is True

    def test_new_map_includes(self):
        policy = ScreenshotPolicy()
        policy.should_include(game_mode="overworld", map_id=0)
        assert policy.should_include(game_mode="overworld", map_id=1) is True


class TestPeriodicForce:
    def test_periodic_force_includes(self):
        policy = ScreenshotPolicy(force_interval=5)
        policy.should_include(game_mode="overworld", map_id=0)  # 1: True (first action)
        for _ in range(4):
            policy.should_include(game_mode="overworld", map_id=0)  # 2,3,4,5: False
        # Action 6: forced by interval (5 actions since last screenshot)
        assert policy.should_include(game_mode="overworld", map_id=0) is True


class TestCallerOverride:
    def test_caller_explicit_true_always_includes(self):
        policy = ScreenshotPolicy()
        policy.should_include(game_mode="overworld", map_id=0)  # Init tracking
        result = policy.should_include(
            caller_explicit=True, game_mode="overworld", map_id=0,
        )
        assert result is True

    def test_caller_explicit_false_always_skips(self):
        policy = ScreenshotPolicy()
        # Even on first action with mode transition, explicit False wins
        result = policy.should_include(
            caller_explicit=False, game_mode="battle", map_id=1,
        )
        assert result is False


class TestDisabledPolicy:
    def test_disabled_policy_always_includes(self):
        policy = ScreenshotPolicy(enabled=False)
        policy.should_include(game_mode="overworld", map_id=0)
        assert policy.should_include(game_mode="overworld", map_id=0) is True

    def test_disabled_policy_ignores_same_state(self):
        policy = ScreenshotPolicy(enabled=False)
        for _ in range(10):
            assert policy.should_include(game_mode="overworld", map_id=0) is True

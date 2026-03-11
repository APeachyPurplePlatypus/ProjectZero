"""Smart screenshot policy for token cost optimization.

Decides whether to include a screenshot in game state responses based on
context: mode transitions, map changes, and periodicity. Only applies when
the caller uses the default (True) for include_screenshot. Explicit True/False
from the caller always takes precedence.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScreenshotPolicy:
    """Decides whether a screenshot should actually be captured."""

    enabled: bool = True
    force_interval: int = 20  # Include a screenshot at least every N actions

    _action_count: int = field(default=0, repr=False)
    _last_screenshot_action: int = field(default=0, repr=False)
    _last_map_id: int = field(default=-1, repr=False)
    _last_game_mode: str = field(default="", repr=False)

    def should_include(
        self,
        *,
        caller_explicit: bool | None = None,
        game_mode: str = "overworld",
        map_id: int = 0,
    ) -> bool:
        """Determine whether a screenshot should be included.

        Args:
            caller_explicit: If True or False, the caller explicitly chose.
                             If None, the policy decides.
            game_mode: Current game mode string.
            map_id: Current map ID.

        Returns:
            True if a screenshot should be included.
        """
        self._action_count += 1

        # Caller explicitly set a value — always respect it
        if caller_explicit is not None:
            if caller_explicit:
                self._last_screenshot_action = self._action_count
            self._update_tracking(game_mode, map_id)
            return caller_explicit

        # Policy disabled — always include
        if not self.enabled:
            self._last_screenshot_action = self._action_count
            self._update_tracking(game_mode, map_id)
            return True

        should = False

        # Rule 1: First action always gets a screenshot
        if self._action_count == 1:
            should = True

        # Rule 2: Include on game mode transition
        if self._last_game_mode and game_mode != self._last_game_mode:
            should = True

        # Rule 3: Include on new map entry
        if self._last_map_id != -1 and map_id != self._last_map_id:
            should = True

        # Rule 4: Include periodically
        actions_since = self._action_count - self._last_screenshot_action
        if actions_since >= self.force_interval:
            should = True

        if should:
            self._last_screenshot_action = self._action_count

        self._update_tracking(game_mode, map_id)
        return should

    def _update_tracking(self, game_mode: str, map_id: int) -> None:
        self._last_game_mode = game_mode
        self._last_map_id = map_id

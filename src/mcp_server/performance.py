"""Performance tracking for extended gameplay sessions.

Tracks battle outcomes, deaths, position travel distance, and timing
so Claude can monitor and adapt strategy during long play sessions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class PerformanceTracker:
    """Tracks gameplay performance metrics for an active session."""

    battles_won: int = 0
    battles_lost: int = 0
    battles_fled: int = 0
    deaths: int = 0
    distance_traveled: int = 0  # Cumulative Manhattan distance in tiles

    _session_start: float = field(default_factory=time.monotonic, repr=False)
    _last_x: int | None = field(default=None, repr=False)
    _last_y: int | None = field(default=None, repr=False)
    _last_game_mode: str = field(default="overworld", repr=False)

    # -- Public API -----------------------------------------------------------

    def record_battle_result(self, outcome: str) -> None:
        """Record a battle result.

        Args:
            outcome: One of "won", "lost", or "fled".
        """
        if outcome == "won":
            self.battles_won += 1
        elif outcome == "lost":
            self.battles_lost += 1
        elif outcome == "fled":
            self.battles_fled += 1

    def record_death(self) -> None:
        """Record a player death."""
        self.deaths += 1

    def update_position(self, x: int, y: int) -> None:
        """Update position tracking, accumulating travel distance.

        Uses Manhattan distance (|dx| + |dy|) for simplicity.
        Skips large jumps (map transitions) to avoid inflating the count.
        """
        if self._last_x is not None and self._last_y is not None:
            dx = abs(x - self._last_x)
            dy = abs(y - self._last_y)
            # Ignore jumps > 20 tiles — likely a map transition, not movement
            if dx + dy <= 20:
                self.distance_traveled += dx + dy
        self._last_x = x
        self._last_y = y

    def update_game_mode(self, mode: str) -> str | None:
        """Track game mode transitions. Returns detected battle outcome or None.

        Call after every execute_action with the new game mode string.
        Returns "won" if transitioning from battle to overworld,
        "fled" if the previous action was a RUN command (not detectable here —
        handled externally by checking the action_type).
        """
        prev = self._last_game_mode
        self._last_game_mode = mode
        # If we were in battle and now we're not, the battle ended
        if prev == "battle" and mode != "battle":
            return "ended"
        return None

    def get_dashboard(self) -> dict:
        """Return all performance metrics as a dict for the MCP tool response."""
        elapsed_seconds = time.monotonic() - self._session_start
        elapsed_minutes = elapsed_seconds / 60.0

        total_battles = self.battles_won + self.battles_lost + self.battles_fled
        win_rate = (self.battles_won / total_battles) if total_battles > 0 else 0.0

        distance_per_minute = (
            self.distance_traveled / elapsed_minutes if elapsed_minutes > 0 else 0.0
        )

        return {
            "session_elapsed_minutes": round(elapsed_minutes, 1),
            "battles_won": self.battles_won,
            "battles_lost": self.battles_lost,
            "battles_fled": self.battles_fled,
            "total_battles": total_battles,
            "win_rate": round(win_rate, 3),
            "deaths": self.deaths,
            "distance_traveled_tiles": self.distance_traveled,
            "distance_per_minute": round(distance_per_minute, 1),
        }

"""Performance tracking for extended gameplay sessions.

Tracks battle outcomes, deaths, position travel distance, and timing
so Claude can monitor and adapt strategy during long play sessions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class DeathContext:
    """Context captured at the moment of death for post-mortem analysis."""

    enemy_group_id: int
    enemy_name: str
    map_id: int
    map_name: str
    ninten_hp_at_death: int
    ninten_max_hp: int
    party_hp: list[tuple[str, int, int]]  # [(name, hp, max_hp), ...]
    timestamp: float = field(default_factory=time.monotonic)


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
    _death_contexts: list[DeathContext] = field(default_factory=list, repr=False)

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
        """Record a player death (without context)."""
        self.deaths += 1

    def record_death_with_context(self, context: DeathContext) -> None:
        """Record a death with full context for post-mortem analysis."""
        self.deaths += 1
        self._death_contexts.append(context)

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
        Returns "ended" if transitioning from battle to non-battle.
        """
        prev = self._last_game_mode
        self._last_game_mode = mode
        if prev == "battle" and mode != "battle":
            return "ended"
        return None

    def get_death_analysis(self) -> dict:
        """Analyze death patterns and return strategy suggestions."""
        if not self._death_contexts:
            return {"total_deaths": self.deaths, "analysis": "No death details recorded."}

        enemy_deaths: dict[str, int] = {}
        location_deaths: dict[str, int] = {}

        for dc in self._death_contexts:
            enemy_deaths[dc.enemy_name] = enemy_deaths.get(dc.enemy_name, 0) + 1
            location_deaths[dc.map_name] = location_deaths.get(dc.map_name, 0) + 1

        deadliest_enemy = max(enemy_deaths, key=enemy_deaths.get) if enemy_deaths else "Unknown"
        deadliest_area = max(location_deaths, key=location_deaths.get) if location_deaths else "Unknown"

        suggestions: list[str] = []
        if enemy_deaths.get(deadliest_enemy, 0) >= 2:
            suggestions.append(
                f"Died {enemy_deaths[deadliest_enemy]}x to {deadliest_enemy}. "
                "Update battle_strategies with a counter-strategy."
            )
        if location_deaths.get(deadliest_area, 0) >= 2:
            suggestions.append(
                f"Died {location_deaths[deadliest_area]}x in {deadliest_area}. "
                "Consider grinding levels before returning."
            )
        low_hp_deaths = sum(
            1 for dc in self._death_contexts
            if dc.ninten_max_hp > 0 and dc.ninten_hp_at_death < dc.ninten_max_hp * 0.3
        )
        if low_hp_deaths > 0:
            suggestions.append(f"{low_hp_deaths} death(s) with HP below 30%. Heal more aggressively.")

        if not suggestions:
            suggestions.append("Review enemy patterns and stock healing items.")

        return {
            "total_deaths": self.deaths,
            "deaths_by_enemy": enemy_deaths,
            "deaths_by_location": location_deaths,
            "deadliest_enemy": deadliest_enemy,
            "deadliest_area": deadliest_area,
            "suggestions": suggestions,
            "recent_deaths": [
                {
                    "enemy": dc.enemy_name,
                    "location": dc.map_name,
                    "hp_at_death": dc.ninten_hp_at_death,
                }
                for dc in self._death_contexts[-5:]
            ],
        }

    def get_dashboard(self) -> dict:
        """Return all performance metrics as a dict for the MCP tool response."""
        elapsed_seconds = time.monotonic() - self._session_start
        elapsed_minutes = elapsed_seconds / 60.0

        total_battles = self.battles_won + self.battles_lost + self.battles_fled
        win_rate = (self.battles_won / total_battles) if total_battles > 0 else 0.0

        distance_per_minute = (
            self.distance_traveled / elapsed_minutes if elapsed_minutes > 0 else 0.0
        )

        dashboard = {
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
        if self._death_contexts:
            dashboard["death_analysis"] = self.get_death_analysis()
        return dashboard

"""Automatic save state management for gameplay sessions.

Triggers a save state checkpoint when:
- The player enters a new map (map_id changes)
- HP is restored to full after previously being below max (post-heal detection)
- A configurable timer interval elapses (default: 5 minutes)

Game over handling:
- When HP drops to 0, restore the most recent checkpoint.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from src.bridge.emulator_bridge import EmulatorBridge

logger = logging.getLogger(__name__)


@dataclass
class _CheckpointState:
    """Internal tracking state for auto-checkpoint triggers."""
    last_map_id: int = -1
    last_hp: int = -1
    last_max_hp: int = -1
    last_checkpoint_time: float = 0.0
    latest_save_id: str | None = None
    save_ids: list[str] = field(default_factory=list)


class AutoCheckpoint:
    """Monitors game state and creates save state checkpoints automatically."""

    def __init__(
        self,
        bridge: EmulatorBridge,
        interval_minutes: float = 5.0,
        enabled: bool = True,
    ) -> None:
        self._bridge = bridge
        self._interval_seconds = interval_minutes * 60.0
        self._enabled = enabled
        self._state = _CheckpointState(last_checkpoint_time=time.monotonic())

    # -- Public API -----------------------------------------------------------

    def check_and_save(self, map_id: int, hp: int, max_hp: int) -> str | None:
        """Evaluate triggers and create a checkpoint if any fire.

        Call this after every get_game_state in the session loop.

        Args:
            map_id: Current map ID from game state.
            hp: Current HP.
            max_hp: Max HP.

        Returns:
            The save_state_id if a checkpoint was created, else None.
        """
        if not self._enabled:
            return None

        reason = self._evaluate_triggers(map_id, hp, max_hp)

        # Update tracked state unconditionally so next call has correct baseline
        self._state.last_map_id = map_id
        self._state.last_hp = hp
        self._state.last_max_hp = max_hp

        if reason:
            return self._create_checkpoint(reason)
        return None

    def check_game_over(self, hp: int) -> bool:
        """Check for game over and restore the latest checkpoint if needed.

        Args:
            hp: Current HP from game state.

        Returns:
            True if a restore was attempted, False otherwise.
        """
        if hp > 0 or not self._state.latest_save_id:
            return False

        logger.warning("Game over detected (HP=0). Restoring: %s", self._state.latest_save_id)
        try:
            self._bridge.restore_save_state(self._state.latest_save_id)
            return True
        except Exception as exc:
            logger.error("Failed to restore save state: %s", exc)
            return False

    @property
    def latest_save_id(self) -> str | None:
        """The most recently created checkpoint ID."""
        return self._state.latest_save_id

    @property
    def all_save_ids(self) -> list[str]:
        """All checkpoint IDs created this session, oldest first."""
        return list(self._state.save_ids)

    # -- Internal -------------------------------------------------------------

    def _evaluate_triggers(self, map_id: int, hp: int, max_hp: int) -> str | None:
        s = self._state

        # Trigger 1: Entered a new map (skip the very first observation)
        if s.last_map_id != -1 and map_id != s.last_map_id:
            return f"new_map_{map_id}"

        # Trigger 2: HP restored to max from a lower value
        # (avoids triggering at session start when last_hp=-1)
        if (
            s.last_hp > 0
            and s.last_hp < s.last_max_hp
            and hp == max_hp
            and max_hp > 0
        ):
            return "healed_full"

        # Trigger 3: Periodic timer
        if time.monotonic() - s.last_checkpoint_time >= self._interval_seconds:
            return "periodic"

        return None

    def _create_checkpoint(self, label: str) -> str | None:
        try:
            save_id = self._bridge.create_save_state(label)
            self._state.latest_save_id = save_id
            self._state.save_ids.append(save_id)
            self._state.last_checkpoint_time = time.monotonic()
            logger.info("Auto-checkpoint created: %s (%s)", save_id, label)
            return save_id
        except Exception as exc:
            logger.error("Auto-checkpoint failed (%s): %s", label, exc)
            return None

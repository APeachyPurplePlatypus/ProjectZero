"""Transforms raw EmulatorBridge GameState into structured FullGameState.

Handles:
- Game mode detection from memory flags
- Status bitfield decoding
- Map name resolution
- Conditional battle/dialog sub-state construction
"""

from __future__ import annotations

from src.bridge.emulator_bridge import GameState as RawGameState
from src.state_parser.map_names import get_map_name
from src.state_parser.models import (
    BattleState,
    DialogState,
    FullGameState,
    GameMode,
    Location,
    PlayerState,
)

# Status bitfield — bit position → status name (DataCrystal: ninten_status at $7441)
# Priority: check highest bit first (most severe condition wins)
_STATUS_FLAGS: list[tuple[int, str]] = [
    (0, "cold"),
    (1, "poisoned"),
    (2, "puzzled"),
    (3, "confused"),
    (4, "asleep"),
    (5, "paralyzed"),
    (6, "stone"),
    (7, "unconscious"),
]


def decode_status(status_byte: int) -> str:
    """Decode status bitfield into the highest-severity active condition.

    Returns "normal" when no bits are set.
    """
    if status_byte == 0:
        return "normal"
    for bit, name in reversed(_STATUS_FLAGS):
        if status_byte & (1 << bit):
            return name
    return "normal"


def detect_game_mode(raw: RawGameState) -> GameMode:
    """Determine current game mode from memory flags.

    Priority order (from docs/SPEC.md):
      combat_active != 0  → battle
      menu_state != 0     → menu
      dialog_active != 0  → dialog
      else                → overworld
    """
    if raw.combat_active != 0:
        return GameMode.BATTLE
    if raw.menu_state != 0:
        return GameMode.MENU
    if raw.dialog_active != 0:
        return GameMode.DIALOG
    return GameMode.OVERWORLD


class GameStateParser:
    """Transforms raw bridge state into structured MCP-ready game state."""

    def build_state(
        self,
        raw: RawGameState,
        screenshot_b64: str | None = None,
    ) -> FullGameState:
        """Build a FullGameState from raw memory values and optional screenshot.

        Args:
            raw: Raw game state from EmulatorBridge.get_state()
            screenshot_b64: Base64-encoded PNG, or None to omit.

        Returns:
            Structured FullGameState ready for MCP tool response.
        """
        game_mode = detect_game_mode(raw)

        player = PlayerState(
            name="Ninten",
            level=max(raw.ninten_level, 1),  # level 0 means game not started
            hp=raw.ninten_hp,
            max_hp=raw.ninten_max_hp,
            pp=raw.ninten_pp,
            max_pp=raw.ninten_max_pp,
            experience=raw.ninten_exp,
            status=decode_status(raw.ninten_status),
        )

        location = Location(
            map_id=raw.map_id,
            map_name=get_map_name(raw.map_id),
            x=raw.player_x,
            y=raw.player_y,
        )

        battle_state = self._build_battle_state(raw) if game_mode == GameMode.BATTLE else None
        dialog_state = self._build_dialog_state() if game_mode == GameMode.DIALOG else None

        return FullGameState(
            frame=raw.frame,
            game_mode=game_mode,
            player=player,
            party=[],        # Phase 3: Ana, Lloyd, Teddy
            location=location,
            inventory=[],    # Phase 4: item slot reading
            battle_state=battle_state,
            dialog_state=dialog_state,
            screenshot_base64=screenshot_b64,
        )

    def _build_battle_state(self, raw: RawGameState) -> BattleState:
        """Build battle sub-state. Enemy details are limited in Phase 2."""
        # enemy_group_id is available; enemy name lookup table is Phase 3
        enemy_label = f"Enemy Group #{raw.enemy_group_id}" if raw.enemy_group_id else "Unknown Enemy"
        return BattleState(
            enemy_name=enemy_label,
            enemy_hp=None,       # Combat struct offsets not yet mapped
            turn=0,              # Turn counter address TBD
            available_actions=["BASH", "PSI", "GOODS", "RUN"],
            menu_cursor="BASH",
        )

    def _build_dialog_state(self) -> DialogState:
        """Build dialog sub-state. Text extraction is Phase 5."""
        return DialogState(
            text="[Dialog active — text extraction not yet implemented]",
            can_advance=True,
        )

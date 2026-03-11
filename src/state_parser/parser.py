"""Transforms raw EmulatorBridge GameState into structured FullGameState.

Handles:
- Game mode detection from memory flags
- Status bitfield decoding
- Map name resolution
- Conditional battle/dialog sub-state construction
"""

from __future__ import annotations

from src.bridge.emulator_bridge import GameState as RawGameState
from src.state_parser.enemy_names import get_enemy_name
from src.state_parser.item_names import get_item_name
from src.state_parser.map_names import get_map_name
from src.state_parser.psi_names import get_psi_name
from src.state_parser.story_objectives import get_current_objective
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
            level=min(max(raw.ninten_level, 1), 99),  # clamp to valid range
            hp=raw.ninten_hp,
            max_hp=raw.ninten_max_hp,
            pp=raw.ninten_pp,
            max_pp=raw.ninten_max_pp,
            experience=raw.ninten_exp,
            status=decode_status(raw.ninten_status),
            learned_psi=self._build_psi(raw, "ninten"),
        )

        location = Location(
            map_id=raw.map_id,
            map_name=get_map_name(raw.map_id),
            x=raw.player_x,
            y=raw.player_y,
        )

        battle_state = self._build_battle_state(raw) if game_mode == GameMode.BATTLE else None
        dialog_state = self._build_dialog_state() if game_mode == GameMode.DIALOG else None

        melodies_count = bin(raw.melodies).count("1")

        return FullGameState(
            frame=raw.frame,
            game_mode=game_mode,
            player=player,
            party=self._build_party(raw),
            location=location,
            inventory=self._build_inventory(raw),
            battle_state=battle_state,
            dialog_state=dialog_state,
            screenshot_base64=screenshot_b64,
            money=raw.money,
            melodies_collected=melodies_count,
            current_objective=get_current_objective(melodies_count, raw.map_id),
        )

    # Ally ID -> (name, raw stat field prefix) mapping.
    # IDs are from the party_0..party_3 slots in state.json.
    # 0 = empty; any non-zero value indicates the ally is active.
    _ALLY_INFO: dict[int, tuple[str, str]] = {
        1: ("Ana",   "ana"),
        2: ("Lloyd", "lloyd"),
        3: ("Teddy", "teddy"),
    }

    # PSI slot offset: "ninten" -> psi_0..7, "ana" -> psi_8..15
    _PSI_OFFSETS: dict[str, int] = {"ninten": 0, "ana": 8}

    def _build_psi(self, raw: RawGameState, character: str) -> list[str]:
        """Build list of learned PSI ability names for a character.

        Args:
            raw: Raw game state.
            character: "ninten" or "ana" (Lloyd/Teddy have no PSI).
        """
        offset = self._PSI_OFFSETS.get(character)
        if offset is None:
            return []
        abilities: list[str] = []
        for i in range(8):
            psi_id = getattr(raw, f"psi_{offset + i}")
            if psi_id != 0:
                abilities.append(get_psi_name(psi_id))
        return abilities

    def _build_party(self, raw: RawGameState) -> list[PlayerState]:
        """Build the active party list from raw state ally slots.

        Reads party_0..party_3 for non-zero ally IDs, then constructs a
        PlayerState for each using the corresponding stat fields.
        Allies with HP=0 (not yet recruited) are omitted.
        """
        party: list[PlayerState] = []
        for slot in (raw.party_0, raw.party_1, raw.party_2, raw.party_3):
            info = self._ALLY_INFO.get(slot)
            if info is None:
                continue
            name, prefix = info
            hp     = getattr(raw, f"{prefix}_hp")
            max_hp = getattr(raw, f"{prefix}_max_hp")
            # Skip allies that have never been recruited (all stats zero)
            if max_hp == 0:
                continue
            party.append(PlayerState(
                name=name,
                level=min(max(getattr(raw, f"{prefix}_level"), 1), 99),
                hp=hp,
                max_hp=max_hp,
                pp=getattr(raw, f"{prefix}_pp"),
                max_pp=getattr(raw, f"{prefix}_max_pp"),
                status=decode_status(getattr(raw, f"{prefix}_status")),
                learned_psi=self._build_psi(raw, prefix),
            ))
        return party

    def _build_inventory(self, raw: RawGameState) -> list[str]:
        """Build a flat inventory list from all 32 item slots.

        Slots 0-7: Ninten, 8-15: Ana, 16-23: Lloyd, 24-31: Teddy.
        Empty slots (item_id == 0) are excluded from the result.
        """
        items: list[str] = []
        for i in range(32):
            item_id = getattr(raw, f"inv_{i}")
            if item_id != 0:
                items.append(get_item_name(item_id))
        return items

    def _build_battle_state(self, raw: RawGameState) -> BattleState:
        """Build battle sub-state. Enemy details are limited in Phase 2."""
        enemy_label = get_enemy_name(raw.enemy_group_id) if raw.enemy_group_id else "Unknown Enemy"
        # Collect PSI from Ninten + Ana (if in party)
        all_psi = list(self._build_psi(raw, "ninten"))
        for slot in (raw.party_0, raw.party_1, raw.party_2, raw.party_3):
            if slot == 1:  # Ana's ally ID
                all_psi.extend(self._build_psi(raw, "ana"))
                break
        return BattleState(
            enemy_name=enemy_label,
            enemy_hp=None,       # Combat struct offsets not yet mapped
            turn=0,              # Turn counter address TBD
            available_actions=["BASH", "PSI", "GOODS", "RUN"],
            menu_cursor="BASH",
            available_psi=all_psi,
        )

    def _build_dialog_state(self) -> DialogState:
        """Build dialog sub-state. Text extraction is Phase 5."""
        return DialogState(
            text="[Dialog active — text extraction not yet implemented]",
            can_advance=True,
        )

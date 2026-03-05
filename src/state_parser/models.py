"""Pydantic models for structured EarthBound Zero game state.

These models define the MCP tool response schemas as specified in docs/MCP_TOOLS.md.
GameStateParser transforms raw bridge GameState into these structured models.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class GameMode(str, Enum):
    """Current game mode detected from memory flags."""
    OVERWORLD = "overworld"
    BATTLE = "battle"
    MENU = "menu"
    DIALOG = "dialog"
    TRANSITION = "transition"


class PlayerState(BaseModel):
    """Stats for a single party member."""
    name: str
    level: int = Field(ge=0, le=99)
    hp: int = Field(ge=0)
    max_hp: int = Field(ge=0)
    pp: int = Field(ge=0)
    max_pp: int = Field(ge=0)
    experience: int = Field(ge=0, default=0)
    status: str = "normal"  # One of: normal, cold, poisoned, puzzled, confused, asleep, paralyzed, stone, unconscious


class Location(BaseModel):
    """Player's current map location."""
    map_id: int
    map_name: str
    x: int
    y: int


class BattleState(BaseModel):
    """Combat state. Present only when game_mode == 'battle'."""
    enemy_name: str = "Unknown"
    enemy_hp: int | None = None
    turn: int = 0
    available_actions: list[str] = Field(
        default_factory=lambda: ["BASH", "PSI", "GOODS", "RUN"]
    )
    menu_cursor: str = "BASH"


class DialogState(BaseModel):
    """Dialog state. Present only when game_mode == 'dialog'."""
    text: str = ""
    can_advance: bool = True


class FullGameState(BaseModel):
    """Complete structured game state — the primary MCP tool response."""
    frame: int
    game_mode: GameMode
    player: PlayerState
    party: list[PlayerState] = Field(default_factory=list)
    location: Location
    inventory: list[str] = Field(default_factory=list)
    battle_state: BattleState | None = None
    dialog_state: DialogState | None = None
    screenshot_base64: str | None = None


class ActionResult(BaseModel):
    """Return value of execute_action tool."""
    success: bool
    action_performed: str
    game_state: FullGameState | None = None


class SaveStateResult(BaseModel):
    """Return value of create_save_state tool."""
    save_state_id: str
    timestamp: str
    game_state_summary: str


class RestoreStateResult(BaseModel):
    """Return value of restore_save_state tool."""
    success: bool
    restored_state: FullGameState | None = None


class MemoryValueResult(BaseModel):
    """Return value of get_memory_value tool."""
    address: str
    hex: str
    decimal: list[int]


class KnowledgeBaseResult(BaseModel):
    """Return value of update_knowledge_base tool."""
    section: str | None = None
    key: str | None = None
    value: str | None = None
    sections: dict[str, int] | None = None
    error: str | None = None

"""Enemy group ID to name lookup for EarthBound Zero.

Source: DataCrystal Mother 1 enemy list. Early-game enemies are pre-populated.
IDs are approximate — validate via screenshots and update the knowledge base
(battle_strategies section) as Claude encounters new enemies.

Expand this table during gameplay by having Claude note enemy names from
screenshots and write them back via update_knowledge_base.
"""

# Enemy group ID -> display name
# Priority: early-game Podunk area enemies listed first
ENEMY_NAMES: dict[int, str] = {
    1:  "Lamp",
    2:  "Hippie",
    3:  "Crow",
    4:  "Snake",
    5:  "Gang Zombie",
    6:  "Centipede",
    7:  "Mr. Batty",
    8:  "Wally",
    9:  "Stray Dog",
    10: "Rat",
    11: "Coil Snake",
    12: "Dung Beetle",
    13: "Mad Car",
    14: "Robot (early)",
    15: "Bully",
}

_UNKNOWN_FORMAT = "Enemy Group #{}"


def get_enemy_name(group_id: int) -> str:
    """Return the display name for an enemy group ID, or a descriptive fallback."""
    return ENEMY_NAMES.get(group_id, _UNKNOWN_FORMAT.format(group_id))

"""Story objective hints based on melody count and current location.

Provides directional guidance for Claude based on game progress.
Not comprehensive — serves as a nudge toward the next major goal.

Melody count is the primary progress indicator (0-8). Map ID provides
location-specific hints when available.
"""

from __future__ import annotations

# Objective hints keyed by melody count (0-8).
# Each entry maps map_id -> hint, with "_default" as fallback.
OBJECTIVES: dict[int, dict[int | str, str]] = {
    0: {
        "_default": "Explore Podunk. Talk to everyone, search Ninten's house for items.",
        0: "Check the basement and upstairs of Ninten's house for items and clues.",
        2: "Explore Podunk town. Visit the zoo and talk to the mayor.",
    },
    1: {
        "_default": "Head east toward Merrysville. Look for the next melody.",
        2: "You have the first melody. Head east from Podunk toward Merrysville.",
        10: "Explore Merrysville. Check the school and talk to Lloyd.",
    },
    2: {
        "_default": "Continue the journey. Consider visiting Magicant or heading to Snowman.",
        8: "Explore Magicant. Visit Queen Mary for story clues.",
        12: "Head to Snowman to find Ana and the next melody.",
    },
    3: {
        "_default": "With 3 melodies, push further. Try Spookane or Youngtown.",
        14: "Explore Spookane. The haunted house holds a melody.",
    },
    4: {
        "_default": "Over halfway. Search for melodies in remaining towns.",
    },
    5: {
        "_default": "Visit Ellay. Teddy can be recruited there.",
        15: "Find Teddy in Ellay's Live House.",
    },
    6: {
        "_default": "Head toward Mt. Itoi for the final melodies.",
    },
    7: {
        "_default": "One melody remaining. Ascend Mt. Itoi to confront Giygas.",
        20: "Climb Mt. Itoi. The last melody awaits near the summit.",
    },
    8: {
        "_default": "All 8 melodies collected! Return to Magicant to face Giygas.",
        21: "Enter the Sea of Eden in Magicant to complete the game.",
    },
}

_FALLBACK = "Continue exploring and searching for melodies."


def get_current_objective(melodies_collected: int, map_id: int) -> str:
    """Return a story hint based on current progress.

    Args:
        melodies_collected: Number of melodies obtained (0-8).
        map_id: Current map ID.

    Returns:
        A hint string describing the suggested next objective.
    """
    melody_hints = OBJECTIVES.get(melodies_collected)
    if melody_hints is None:
        # Out-of-range melody count — use highest known tier
        melody_hints = OBJECTIVES.get(8, {})
    # Try map-specific hint first, then fall back to default
    if map_id in melody_hints:
        return melody_hints[map_id]
    return melody_hints.get("_default", _FALLBACK)

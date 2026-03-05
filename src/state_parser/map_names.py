"""Map ID to human-readable name lookup.

Source: DataCrystal community docs + empirical validation.
These IDs are approximate — validate by loading the game and reading
address $0015 (map_id) at each known location.
Expand this table as Claude explores the world.
"""

# Map ID → display name
# TODO: validate all IDs against the ROM with FCEUX RAM viewer
MAP_NAMES: dict[int, str] = {
    0:  "Ninten's House",
    1:  "Ninten's House - 2F",
    2:  "Podunk",
    3:  "Podunk - South",
    4:  "Podunk - Department Store",
    5:  "Podunk - Department Store B1",
    6:  "Canary Village",
    7:  "Canary Village - Sweet's Factory",
    8:  "Magicant",
    9:  "Magicant - Flying Man's House",
    10: "Merrysville",
    11: "Merrysville - Train Station",
    12: "Snowman",
    13: "Youngtown",
    14: "Spookane",
    15: "Ellay",
    16: "Ellay - Twinkle Elementary",
    17: "Reindeer",
    18: "Thanksgiving",
    19: "Duncan's Factory",
    20: "Mt. Itoi",
    21: "Magicant - Sea of Eden",
}

_UNKNOWN_FORMAT = "Unknown Area (ID: {})"


def get_map_name(map_id: int) -> str:
    """Return the display name for a map ID, or a descriptive fallback."""
    return MAP_NAMES.get(map_id, _UNKNOWN_FORMAT.format(map_id))

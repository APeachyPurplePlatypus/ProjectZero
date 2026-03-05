"""Item ID to display name lookup for EarthBound Zero.

Source: DataCrystal EarthBound Beginnings, community item databases.
IDs are approximate — validate during gameplay and expand this table
as Claude encounters new items.

Claude can note item names from screenshots and record them in the
knowledge base (inventory section) as a secondary reference.
"""

# Item ID -> display name
# 0 = empty slot
ITEM_NAMES: dict[int, str] = {
    0:  "(empty)",
    1:  "Bread",
    2:  "Hamburger",
    3:  "Pizza",
    4:  "Steak",
    5:  "Pork Chop",
    6:  "Cookie",
    7:  "Iced Tea",
    8:  "Vial",
    9:  "Full Bottle",
    10: "Orange Juice",
    11: "Skip Sandwich",
    12: "Love Potion",
    13: "Secret Herb",
    14: "PK Power",
    15: "Boomerang",
    16: "Slingshot",
    17: "Toy Air Gun",
    18: "Baseball Bat",
    19: "Little League Bat",
    20: "Copper Bracelet",
    21: "Silver Bracelet",
    22: "Gold Bracelet",
    23: "Diamond Bracelet",
    24: "Mr. Baseball Cap",
    25: "Diadem",
    26: "Key",
    27: "Teardrop",
    28: "Franklin Badge",
    29: "Ruler",
    30: "Crystal",
    31: "Eraser Eraser",
    32: "Cheap Bracelet",
    33: "Fry Pan",
    34: "Better Fry Pan",
    35: "Best Fry Pan",
    36: "Cracked Bat",
    37: "Thick Pencil",
    38: "Mr. Baseball Bat",
    39: "PSI Caramel",
    40: "Penny",
    41: "Coin of Defense",
    42: "Coin of Slumber",
    43: "Coin of Silence",
    44: "Coin of Bomb",
    45: "Brace Bracelet",
    46: "Night Pendant",
    47: "Picnic Lunch",
    48: "Magic Tart",
    49: "Refreshing Herb",
    50: "Antidote",
}

_UNKNOWN_FORMAT = "Item #{}"


def get_item_name(item_id: int) -> str:
    """Return the display name for an item ID, or a descriptive fallback."""
    return ITEM_NAMES.get(item_id, _UNKNOWN_FORMAT.format(item_id))

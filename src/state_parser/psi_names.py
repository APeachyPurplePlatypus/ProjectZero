"""PSI ability ID to display name and PP cost lookup for EarthBound Zero.

Source: DataCrystal Mother 1 / EarthBound Beginnings community documentation.
IDs are approximate — validate during gameplay with FCEUX memory viewer.

PSI data is stored at character struct offset +$30 through +$37 (8 slots).
Ninten primarily learns support/healing PSI; Ana learns offensive PSI.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PSIAbility:
    """A single PSI ability with its display name, PP cost, and type."""

    name: str
    pp_cost: int
    psi_type: str  # "offense", "defense", "healing", "assist"


# PSI ID -> PSIAbility
# 0 = empty/unlearned slot
PSI_ABILITIES: dict[int, PSIAbility] = {
    0:  PSIAbility("(none)", 0, ""),
    # Offensive PSI (primarily Ana)
    1:  PSIAbility("PK Fire a", 6, "offense"),
    2:  PSIAbility("PK Fire b", 12, "offense"),
    3:  PSIAbility("PK Freeze a", 9, "offense"),
    4:  PSIAbility("PK Freeze b", 18, "offense"),
    5:  PSIAbility("PK Beam a", 4, "offense"),
    6:  PSIAbility("PK Beam b", 8, "offense"),
    7:  PSIAbility("PK Beam g", 16, "offense"),
    8:  PSIAbility("PK Thunder a", 3, "offense"),
    9:  PSIAbility("PK Thunder b", 7, "offense"),
    10: PSIAbility("Brain Shock", 5, "offense"),
    # Healing PSI (Ninten and Ana)
    11: PSIAbility("Healing a", 3, "healing"),
    12: PSIAbility("Healing b", 5, "healing"),
    13: PSIAbility("Healing g", 9, "healing"),
    14: PSIAbility("Healing p", 15, "healing"),
    15: PSIAbility("SuperHealing", 20, "healing"),
    # Defense PSI
    16: PSIAbility("PSI Shield a", 6, "defense"),
    17: PSIAbility("PSI Shield b", 12, "defense"),
    # Assist PSI (Ninten)
    18: PSIAbility("Offense Up a", 5, "assist"),
    19: PSIAbility("Offense Up b", 10, "assist"),
    20: PSIAbility("Defense Up a", 5, "assist"),
    21: PSIAbility("Defense Up b", 10, "assist"),
    22: PSIAbility("Quick Up", 7, "assist"),
    23: PSIAbility("Telepathy", 0, "assist"),
    24: PSIAbility("Teleport", 8, "assist"),
    25: PSIAbility("Hypnosis", 6, "assist"),
    26: PSIAbility("Paralysis", 6, "assist"),
    27: PSIAbility("Darkness", 4, "assist"),
    28: PSIAbility("4th-D Slip", 16, "assist"),
}

_UNKNOWN_FORMAT = "PSI #{}"


def get_psi_name(psi_id: int) -> str:
    """Return the display name for a PSI ability ID, or a descriptive fallback."""
    ability = PSI_ABILITIES.get(psi_id)
    if ability:
        return ability.name
    return _UNKNOWN_FORMAT.format(psi_id)


def get_psi_ability(psi_id: int) -> PSIAbility | None:
    """Return the full PSIAbility for an ID, or None if unknown."""
    return PSI_ABILITIES.get(psi_id)

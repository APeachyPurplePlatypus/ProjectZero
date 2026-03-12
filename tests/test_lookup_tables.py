"""Data integrity tests for lookup tables.

Validates that map_names, enemy_names, item_names, psi_names, and story_objectives
have no duplicate entries, valid keys, and cross-table consistency.
"""

from __future__ import annotations

from dataclasses import fields

from src.bridge.emulator_bridge import GameState
from src.mcp_server.server import KNOWN_ADDRESSES
from src.state_parser.enemy_names import ENEMY_NAMES
from src.state_parser.item_names import ITEM_NAMES
from src.state_parser.map_names import MAP_NAMES
from src.state_parser.psi_names import PSI_ABILITIES
from src.state_parser.story_objectives import OBJECTIVES


class TestMapNamesIntegrity:
    def test_no_duplicate_map_names(self):
        values = list(MAP_NAMES.values())
        assert len(values) == len(set(values))

    def test_all_map_ids_non_negative(self):
        for map_id in MAP_NAMES:
            assert map_id >= 0, f"Map ID {map_id} is negative"


class TestEnemyNamesIntegrity:
    def test_no_duplicate_enemy_names(self):
        values = list(ENEMY_NAMES.values())
        assert len(values) == len(set(values))

    def test_all_enemy_ids_positive(self):
        for eid in ENEMY_NAMES:
            assert eid > 0, f"Enemy ID {eid} should be positive"


class TestItemNamesIntegrity:
    def test_no_duplicate_item_names_excluding_empty(self):
        values = [v for v in ITEM_NAMES.values() if v != "(empty)"]
        assert len(values) == len(set(values))

    def test_zero_id_is_empty_slot(self):
        assert ITEM_NAMES[0] == "(empty)"

    def test_all_item_ids_non_negative(self):
        for item_id in ITEM_NAMES:
            assert item_id >= 0, f"Item ID {item_id} is negative"


class TestPsiNamesIntegrity:
    def test_no_duplicate_psi_names_excluding_none(self):
        names = [a.name for a in PSI_ABILITIES.values() if a.name != "(none)"]
        assert len(names) == len(set(names))

    def test_zero_id_is_none_slot(self):
        assert PSI_ABILITIES[0].name == "(none)"
        assert PSI_ABILITIES[0].pp_cost == 0

    def test_all_pp_costs_non_negative(self):
        for psi_id, ability in PSI_ABILITIES.items():
            assert ability.pp_cost >= 0, f"PSI ID {psi_id} has negative PP cost"


class TestCrossTableConsistency:
    def test_known_addresses_field_names_exist_in_gamestate(self):
        gs_fields = {f.name for f in fields(GameState)}
        for addr, (field_name, _) in KNOWN_ADDRESSES.items():
            assert field_name in gs_fields, (
                f"KNOWN_ADDRESSES[{addr}] references '{field_name}' "
                f"which is not a GameState field"
            )

    def test_story_objective_map_ids_exist_in_map_names(self):
        for melody_count, hints in OBJECTIVES.items():
            for key in hints:
                if isinstance(key, int):
                    assert key in MAP_NAMES, (
                        f"OBJECTIVES[{melody_count}] references map_id={key} "
                        f"which is not in MAP_NAMES"
                    )

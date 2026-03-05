"""Tests for party and inventory parsing in GameStateParser (Phase 5)."""

from __future__ import annotations

import pytest

from src.bridge.emulator_bridge import GameState as RawGameState
from src.state_parser.parser import GameStateParser


def make_raw(**overrides) -> RawGameState:
    """Build a minimal RawGameState with sensible defaults."""
    defaults = dict(
        frame=100,
        map_id=0,
        player_x=10,
        player_y=20,
        ninten_hp=68,
        ninten_max_hp=68,
        ninten_level=5,
        ninten_pp=20,
        ninten_max_pp=30,
        ninten_exp=500,
        ninten_status=0,
        combat_active=0,
        enemy_group_id=0,
        menu_state=0,
        dialog_active=0,
        movement_state=0,
        player_direction=0,
    )
    defaults.update(overrides)
    return RawGameState(**defaults)


PARSER = GameStateParser()


# ---------------------------------------------------------------------------
# Party building
# ---------------------------------------------------------------------------

class TestBuildParty:
    def test_empty_party_returns_empty_list(self):
        raw = make_raw()  # All party slots default to 0
        state = PARSER.build_state(raw)
        assert state.party == []

    def test_single_ally_ana(self):
        raw = make_raw(
            party_0=1,  # Ana
            ana_hp=30, ana_max_hp=40, ana_pp=20, ana_max_pp=35,
            ana_level=4, ana_status=0,
        )
        state = PARSER.build_state(raw)
        assert len(state.party) == 1
        assert state.party[0].name == "Ana"
        assert state.party[0].hp == 30
        assert state.party[0].max_hp == 40
        assert state.party[0].level == 4

    def test_single_ally_lloyd(self):
        raw = make_raw(
            party_1=2,  # Lloyd
            lloyd_hp=25, lloyd_max_hp=35, lloyd_pp=0, lloyd_max_pp=0,
            lloyd_level=3, lloyd_status=0,
        )
        state = PARSER.build_state(raw)
        assert len(state.party) == 1
        assert state.party[0].name == "Lloyd"

    def test_single_ally_teddy(self):
        raw = make_raw(
            party_2=3,  # Teddy
            teddy_hp=50, teddy_max_hp=60, teddy_pp=0, teddy_max_pp=0,
            teddy_level=6, teddy_status=0,
        )
        state = PARSER.build_state(raw)
        assert len(state.party) == 1
        assert state.party[0].name == "Teddy"

    def test_full_party_three_allies(self):
        raw = make_raw(
            party_0=1, ana_hp=30, ana_max_hp=40, ana_pp=20, ana_max_pp=35,
                       ana_level=4, ana_status=0,
            party_1=2, lloyd_hp=25, lloyd_max_hp=35, lloyd_pp=0, lloyd_max_pp=0,
                       lloyd_level=3, lloyd_status=0,
            party_2=3, teddy_hp=50, teddy_max_hp=60, teddy_pp=0, teddy_max_pp=0,
                       teddy_level=6, teddy_status=0,
        )
        state = PARSER.build_state(raw)
        assert len(state.party) == 3
        names = [m.name for m in state.party]
        assert "Ana" in names
        assert "Lloyd" in names
        assert "Teddy" in names

    def test_ally_with_zero_max_hp_excluded(self):
        # An ally ID set but max_hp=0 means not yet recruited — skip them
        raw = make_raw(party_0=1, ana_hp=0, ana_max_hp=0, ana_level=0, ana_status=0,
                       ana_pp=0, ana_max_pp=0)
        state = PARSER.build_state(raw)
        assert state.party == []

    def test_ally_status_decoded(self):
        # Bit 1 = poisoned
        raw = make_raw(
            party_0=1,
            ana_hp=30, ana_max_hp=40, ana_pp=10, ana_max_pp=20,
            ana_level=3, ana_status=0b00000010,  # poisoned
        )
        state = PARSER.build_state(raw)
        assert state.party[0].status == "poisoned"

    def test_unknown_party_id_ignored(self):
        # ID 99 is not in _ALLY_INFO — should be silently skipped
        raw = make_raw(party_0=99)
        state = PARSER.build_state(raw)
        assert state.party == []


# ---------------------------------------------------------------------------
# Inventory building
# ---------------------------------------------------------------------------

class TestBuildInventory:
    def test_empty_inventory_returns_empty_list(self):
        raw = make_raw()  # All inv_* default to 0
        state = PARSER.build_state(raw)
        assert state.inventory == []

    def test_single_item_in_slot_0(self):
        raw = make_raw(inv_0=1)  # 1 = Bread
        state = PARSER.build_state(raw)
        assert "Bread" in state.inventory

    def test_multiple_items(self):
        raw = make_raw(inv_0=1, inv_1=2)  # Bread, Hamburger
        state = PARSER.build_state(raw)
        assert len(state.inventory) == 2

    def test_items_from_ally_slots(self):
        # inv_8 = Ana's first slot
        raw = make_raw(inv_8=10)  # 10 = Orange Juice
        state = PARSER.build_state(raw)
        assert "Orange Juice" in state.inventory

    def test_all_32_slots_scanned(self):
        # Put an item only in the last Teddy slot (inv_31)
        raw = make_raw(inv_31=1)
        state = PARSER.build_state(raw)
        assert len(state.inventory) == 1

    def test_unknown_item_id_shows_fallback(self):
        raw = make_raw(inv_0=200)
        state = PARSER.build_state(raw)
        assert "Item #200" in state.inventory


# ---------------------------------------------------------------------------
# Money and melodies in FullGameState
# ---------------------------------------------------------------------------

class TestMoneyAndMelodies:
    def test_money_included_in_state(self):
        raw = make_raw(money=500)
        state = PARSER.build_state(raw)
        assert state.money == 500

    def test_melodies_collected_count(self):
        # 3 melodies = 3 bits set: 0b00000111 = 7
        raw = make_raw(melodies=0b00000111)
        state = PARSER.build_state(raw)
        assert state.melodies_collected == 3

    def test_all_melodies_count(self):
        # 8 melodies = all 8 bits set: 0b11111111 = 255
        raw = make_raw(melodies=0xFF)
        state = PARSER.build_state(raw)
        assert state.melodies_collected == 8

    def test_no_melodies(self):
        raw = make_raw(melodies=0)
        state = PARSER.build_state(raw)
        assert state.melodies_collected == 0

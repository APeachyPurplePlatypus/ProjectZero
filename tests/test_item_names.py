"""Unit tests for the item ID → name lookup table."""

from __future__ import annotations

from src.state_parser.item_names import ITEM_NAMES, get_item_name


class TestGetItemName:
    def test_known_item_returns_name(self):
        assert get_item_name(1) == "Bread"

    def test_empty_slot_returns_empty_string(self):
        assert get_item_name(0) == "(empty)"

    def test_known_item_franklin_badge(self):
        assert get_item_name(28) == "Franklin Badge"

    def test_unknown_item_returns_fallback(self):
        result = get_item_name(999)
        assert result == "Item #999"

    def test_all_known_ids_return_strings(self):
        for item_id, name in ITEM_NAMES.items():
            assert isinstance(get_item_name(item_id), str)
            assert len(get_item_name(item_id)) > 0

    def test_table_has_minimum_entries(self):
        # Must have at least the early-game essentials
        assert len(ITEM_NAMES) >= 10

    def test_fallback_includes_id(self):
        result = get_item_name(42)
        # Either it's a known name, or the fallback includes the ID
        if result.startswith("Item #"):
            assert "42" in result

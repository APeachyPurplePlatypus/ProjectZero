"""Unit tests for the KnowledgeBase class."""

from __future__ import annotations

import json
import pytest

from src.knowledge_base.kb import KnowledgeBase, VALID_SECTIONS


@pytest.fixture
def kb(tmp_path):
    return KnowledgeBase(tmp_path / "kb.json")


class TestReadWrite:
    def test_write_and_read(self, kb):
        kb.write("map_data", "podunk_layout", "Small town, store to east.")
        assert kb.read("map_data", "podunk_layout") == "Small town, store to east."

    def test_read_missing_key_returns_none(self, kb):
        assert kb.read("map_data", "nonexistent") is None

    def test_write_overwrites_existing(self, kb):
        kb.write("objectives", "goal", "Find the melody.")
        kb.write("objectives", "goal", "Reach Podunk.")
        assert kb.read("objectives", "goal") == "Reach Podunk."

    def test_multiple_sections_independent(self, kb):
        kb.write("map_data", "key", "map value")
        kb.write("npc_notes", "key", "npc value")
        assert kb.read("map_data", "key") == "map value"
        assert kb.read("npc_notes", "key") == "npc value"


class TestDelete:
    def test_delete_existing_key_returns_true(self, kb):
        kb.write("death_log", "death_001", "Died to snake.")
        assert kb.delete("death_log", "death_001") is True
        assert kb.read("death_log", "death_001") is None

    def test_delete_missing_key_returns_false(self, kb):
        assert kb.delete("death_log", "never_existed") is False

    def test_delete_does_not_affect_other_keys(self, kb):
        kb.write("npc_notes", "mom", "She worries.")
        kb.write("npc_notes", "dad", "He works abroad.")
        kb.delete("npc_notes", "mom")
        assert kb.read("npc_notes", "dad") == "He works abroad."


class TestListSections:
    def test_list_sections_returns_all_sections(self, kb):
        sections = kb.list_sections()
        assert set(sections.keys()) == VALID_SECTIONS

    def test_list_sections_counts_entries(self, kb):
        kb.write("battle_strategies", "lamps", "Use BASH.")
        kb.write("battle_strategies", "crows", "Use BASH twice.")
        counts = kb.list_sections()
        assert counts["battle_strategies"] == 2
        assert counts["map_data"] == 0

    def test_get_all_section(self, kb):
        kb.write("inventory", "items", "Bread, OJ")
        kb.write("inventory", "money", "50G")
        all_items = kb.get_all("inventory")
        assert all_items == {"items": "Bread, OJ", "money": "50G"}

    def test_get_all_returns_copy(self, kb):
        kb.write("objectives", "main", "Find all 8 melodies.")
        result = kb.get_all("objectives")
        result["main"] = "Modified"
        assert kb.read("objectives", "main") == "Find all 8 melodies."


class TestPersistence:
    def test_data_persists_across_instances(self, tmp_path):
        path = tmp_path / "kb.json"
        kb1 = KnowledgeBase(path)
        kb1.write("map_data", "ninten_house", "Starting location.")

        kb2 = KnowledgeBase(path)
        assert kb2.read("map_data", "ninten_house") == "Starting location."

    def test_file_is_valid_json(self, tmp_path):
        path = tmp_path / "kb.json"
        kb = KnowledgeBase(path)
        kb.write("objectives", "test", "value")
        data = json.loads(path.read_text())
        assert data["objectives"]["test"] == "value"

    def test_empty_kb_creates_no_file(self, tmp_path):
        path = tmp_path / "kb.json"
        KnowledgeBase(path)
        assert not path.exists()

    def test_corrupt_file_starts_fresh(self, tmp_path):
        path = tmp_path / "kb.json"
        path.write_text("not valid json")
        kb = KnowledgeBase(path)
        assert kb.read("map_data", "anything") is None


class TestValidation:
    def test_invalid_section_read_raises(self, kb):
        with pytest.raises(ValueError, match="Invalid section"):
            kb.read("invalid_section", "key")

    def test_invalid_section_write_raises(self, kb):
        with pytest.raises(ValueError, match="Invalid section"):
            kb.write("invalid_section", "key", "value")

    def test_invalid_section_delete_raises(self, kb):
        with pytest.raises(ValueError, match="Invalid section"):
            kb.delete("invalid_section", "key")

    def test_invalid_section_get_all_raises(self, kb):
        with pytest.raises(ValueError, match="Invalid section"):
            kb.get_all("invalid_section")

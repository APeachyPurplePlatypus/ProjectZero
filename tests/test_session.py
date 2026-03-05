"""Unit tests for SessionManager — progressive summarization and session save/restore."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.knowledge_base.kb import KnowledgeBase
from src.knowledge_base.session import SessionData, SessionManager


@pytest.fixture
def kb(tmp_path):
    return KnowledgeBase(tmp_path / "kb.json")


@pytest.fixture
def session_mgr(tmp_path, kb):
    return SessionManager(
        sessions_dir=tmp_path / "sessions",
        kb=kb,
        summarization_threshold=50,
    )


class TestToolCallTracking:
    def test_initial_count_is_zero(self, session_mgr):
        assert session_mgr.tool_call_count == 0

    def test_increment_returns_new_count(self, session_mgr):
        assert session_mgr.increment_tool_calls() == 1
        assert session_mgr.increment_tool_calls() == 2

    def test_count_property_after_increments(self, session_mgr):
        session_mgr.increment_tool_calls()
        session_mgr.increment_tool_calls()
        assert session_mgr.tool_call_count == 2

    def test_should_summarize_false_below_threshold(self, session_mgr):
        for _ in range(49):
            session_mgr.increment_tool_calls()
        assert session_mgr.should_summarize is False

    def test_should_summarize_true_at_threshold(self, session_mgr):
        for _ in range(50):
            session_mgr.increment_tool_calls()
        assert session_mgr.should_summarize is True

    def test_should_summarize_true_above_threshold(self, session_mgr):
        for _ in range(75):
            session_mgr.increment_tool_calls()
        assert session_mgr.should_summarize is True

    def test_get_session_stats_shape(self, session_mgr):
        session_mgr.increment_tool_calls()
        stats = session_mgr.get_session_stats()
        assert stats["tool_call_count"] == 1
        assert stats["summarization_threshold"] == 50
        assert stats["should_summarize"] is False

    def test_get_session_stats_should_summarize_true(self, session_mgr):
        for _ in range(50):
            session_mgr.increment_tool_calls()
        stats = session_mgr.get_session_stats()
        assert stats["should_summarize"] is True


class TestProgressSummary:
    def test_write_and_read_summary(self, session_mgr):
        session_mgr.write_progress_summary("At Podunk, level 5, heading east.")
        assert session_mgr.get_last_summary() == "At Podunk, level 5, heading east."

    def test_write_overwrites_previous(self, session_mgr):
        session_mgr.write_progress_summary("First summary.")
        session_mgr.write_progress_summary("Second summary.")
        assert session_mgr.get_last_summary() == "Second summary."

    def test_summary_persists_to_disk(self, tmp_path, kb):
        mgr1 = SessionManager(tmp_path / "sessions", kb, 50)
        mgr1.write_progress_summary("Persisted summary.")

        mgr2 = SessionManager(tmp_path / "sessions", kb, 50)
        assert mgr2.get_last_summary() == "Persisted summary."

    def test_no_summary_returns_none(self, session_mgr):
        assert session_mgr.get_last_summary() is None

    def test_in_memory_takes_priority_over_disk(self, tmp_path, kb):
        mgr = SessionManager(tmp_path / "sessions", kb, 50)
        mgr.write_progress_summary("Disk summary.")

        # Simulate a second manager with in-memory state (as if write was called)
        mgr2 = SessionManager(tmp_path / "sessions", kb, 50)
        mgr2.write_progress_summary("In-memory summary.")
        assert mgr2.get_last_summary() == "In-memory summary."


class TestSessionSave:
    def test_save_creates_file(self, session_mgr, tmp_path):
        session = session_mgr.save_session(
            name="test_save",
            save_state_id="ss_test",
            game_state_summary="Ninten Lv5 HP:68/68 at Podunk",
        )
        session_path = tmp_path / "sessions" / f"{session.session_id}.json"
        assert session_path.exists()

    def test_save_captures_kb_snapshot(self, session_mgr, kb):
        kb.write("map_data", "podunk", "Small town")
        session = session_mgr.save_session(
            name="with_kb",
            save_state_id=None,
            game_state_summary="test",
        )
        assert session.knowledge_base_snapshot["map_data"]["podunk"] == "Small town"

    def test_save_includes_tool_call_count(self, session_mgr):
        for _ in range(10):
            session_mgr.increment_tool_calls()
        session = session_mgr.save_session(
            name="counted",
            save_state_id=None,
            game_state_summary="test",
        )
        assert session.tool_call_count == 10

    def test_save_includes_progress_summary(self, session_mgr):
        session_mgr.write_progress_summary("My progress")
        session = session_mgr.save_session(
            name="with_summary",
            save_state_id=None,
            game_state_summary="test",
        )
        assert session.progress_summary == "My progress"

    def test_save_with_no_emulator_state(self, session_mgr):
        session = session_mgr.save_session(
            name="no_emu",
            save_state_id=None,
            game_state_summary="offline",
        )
        assert session.save_state_id is None

    def test_session_id_contains_name(self, session_mgr):
        session = session_mgr.save_session(
            name="my_label",
            save_state_id=None,
            game_state_summary="test",
        )
        assert "my_label" in session.session_id

    def test_session_file_is_valid_json(self, session_mgr, tmp_path):
        session = session_mgr.save_session(
            name="json_check",
            save_state_id="ss_x",
            game_state_summary="test",
        )
        path = tmp_path / "sessions" / f"{session.session_id}.json"
        data = json.loads(path.read_text())
        assert data["session_id"] == session.session_id

    def test_save_stores_save_state_id(self, session_mgr):
        session = session_mgr.save_session(
            name="with_emu",
            save_state_id="ss_20260305_abc",
            game_state_summary="test",
        )
        assert session.save_state_id == "ss_20260305_abc"


class TestSessionList:
    def test_list_empty_returns_empty(self, session_mgr):
        assert session_mgr.list_sessions() == []

    def test_list_returns_saved_sessions(self, session_mgr):
        session_mgr.save_session("a", None, "test_a")
        session_mgr.save_session("b", None, "test_b")
        sessions = session_mgr.list_sessions()
        assert len(sessions) == 2

    def test_list_sorted_newest_first(self, session_mgr):
        session_mgr.save_session("first", None, "test1")
        time.sleep(0.02)
        session_mgr.save_session("second", None, "test2")
        sessions = session_mgr.list_sessions()
        assert sessions[0]["game_state_summary"] == "test2"

    def test_list_entry_shape(self, session_mgr):
        session_mgr.save_session("shape_test", None, "summary")
        entry = session_mgr.list_sessions()[0]
        assert "session_id" in entry
        assert "timestamp" in entry
        assert "game_state_summary" in entry
        assert "tool_call_count" in entry

    def test_list_excludes_underscore_files(self, session_mgr, tmp_path):
        session_mgr.save_session("real", None, "test")
        sessions = session_mgr.list_sessions()
        # _last_summary.json should not appear in the list
        assert all(not s["session_id"].startswith("_") for s in sessions)


class TestSessionRestore:
    def test_restore_loads_kb_snapshot(self, session_mgr, kb):
        kb.write("objectives", "goal", "Find melody 1")
        session = session_mgr.save_session("restore_test", None, "test")

        # Modify KB after save
        kb.write("objectives", "goal", "MODIFIED")
        kb.write("objectives", "new_key", "new_value")

        # Restore should revert to snapshot state
        session_mgr.restore_session(session.session_id)
        assert kb.read("objectives", "goal") == "Find melody 1"

    def test_restore_returns_session_data(self, session_mgr, kb):
        session_mgr.write_progress_summary("Progress text")
        session = session_mgr.save_session("data_test", "ss_123", "Lv5 Podunk")

        restored = session_mgr.restore_session(session.session_id)
        assert restored.progress_summary == "Progress text"
        assert restored.save_state_id == "ss_123"
        assert restored.game_state_summary == "Lv5 Podunk"

    def test_restore_nonexistent_raises(self, session_mgr):
        with pytest.raises(FileNotFoundError):
            session_mgr.restore_session("nonexistent_id")

    def test_restore_cleans_extra_kb_keys(self, session_mgr, kb):
        """Keys in live KB but not in snapshot should be removed on restore."""
        session = session_mgr.save_session("clean_test", None, "test")

        kb.write("npc_notes", "extra", "should be removed")
        session_mgr.restore_session(session.session_id)
        assert kb.read("npc_notes", "extra") is None

    def test_restore_updates_in_memory_summary(self, session_mgr):
        session_mgr.write_progress_summary("Saved summary")
        session = session_mgr.save_session("summary_restore", None, "test")

        # Clear in-memory state via new manager using same dir and kb
        session_mgr._latest_summary = None
        session_mgr.restore_session(session.session_id)
        assert session_mgr.get_last_summary() == "Saved summary"


class TestSessionData:
    def test_round_trip_serialization(self):
        sd = SessionData(
            session_id="session_20260305_143022_000000_test",
            timestamp="2026-03-05T14:30:22+00:00",
            save_state_id="ss_123",
            progress_summary="At Podunk",
            knowledge_base_snapshot={"map_data": {"town": "notes"}},
            game_state_summary="Ninten Lv5",
            tool_call_count=42,
        )
        data = sd.to_dict()
        restored = SessionData.from_dict(data)
        assert restored.session_id == sd.session_id
        assert restored.knowledge_base_snapshot == sd.knowledge_base_snapshot
        assert restored.tool_call_count == sd.tool_call_count

    def test_from_dict_with_none_save_state(self):
        data = {
            "session_id": "test",
            "timestamp": "now",
            "save_state_id": None,
            "progress_summary": "",
            "knowledge_base_snapshot": {},
            "game_state_summary": "",
            "tool_call_count": 0,
        }
        sd = SessionData.from_dict(data)
        assert sd.save_state_id is None

    def test_to_dict_contains_all_fields(self):
        sd = SessionData(
            session_id="sid",
            timestamp="ts",
            save_state_id=None,
            progress_summary="",
            knowledge_base_snapshot={},
            game_state_summary="",
            tool_call_count=0,
        )
        d = sd.to_dict()
        assert set(d.keys()) == {
            "session_id", "timestamp", "save_state_id", "progress_summary",
            "knowledge_base_snapshot", "game_state_summary", "tool_call_count",
        }

"""Session save/restore and progressive summarization support.

A 'session' bundles:
  - Emulator save state ID (references EmulatorBridge slot)
  - Knowledge base snapshot (full copy of all sections)
  - Progress summary text (written by Claude when context is getting long)
  - Metadata: timestamp, tool call count, game state summary

Persisted to data/sessions/<session_id>.json with atomic writes.
The latest progress summary is also stored standalone at
data/sessions/_last_summary.json for fast retrieval on new conversations.

Tool call counting resets each time Claude Desktop spawns a fresh MCP server
process (i.e., per conversation). This is the intended behavior — we track
conversation length, not cumulative lifetime tool calls.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.knowledge_base.kb import VALID_SECTIONS, KnowledgeBase


@dataclass
class SessionData:
    """Serializable session bundle."""

    session_id: str
    timestamp: str
    save_state_id: str | None
    progress_summary: str
    knowledge_base_snapshot: dict[str, dict[str, str]]
    game_state_summary: str
    tool_call_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionData:
        return cls(
            session_id=data["session_id"],
            timestamp=data["timestamp"],
            save_state_id=data.get("save_state_id"),
            progress_summary=data.get("progress_summary", ""),
            knowledge_base_snapshot=data.get("knowledge_base_snapshot", {}),
            game_state_summary=data.get("game_state_summary", ""),
            tool_call_count=data.get("tool_call_count", 0),
        )


class SessionManager:
    """Manages session persistence and tool call counting."""

    def __init__(
        self,
        sessions_dir: str | Path,
        kb: KnowledgeBase,
        summarization_threshold: int = 50,
    ) -> None:
        self._sessions_dir = Path(sessions_dir)
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._kb = kb
        self._summarization_threshold = summarization_threshold
        self._tool_call_count: int = 0
        self._latest_summary: str | None = None

    # -- Tool call tracking ---------------------------------------------------

    def increment_tool_calls(self) -> int:
        """Increment and return the current tool call count."""
        self._tool_call_count += 1
        return self._tool_call_count

    @property
    def tool_call_count(self) -> int:
        return self._tool_call_count

    @property
    def should_summarize(self) -> bool:
        return self._tool_call_count >= self._summarization_threshold

    def get_session_stats(self) -> dict[str, Any]:
        return {
            "tool_call_count": self._tool_call_count,
            "summarization_threshold": self._summarization_threshold,
            "should_summarize": self.should_summarize,
        }

    # -- Progress summary -----------------------------------------------------

    def write_progress_summary(self, summary: str) -> None:
        """Store the latest progress summary in memory and persist to disk."""
        self._latest_summary = summary
        self._save_summary_standalone(summary)

    def get_last_summary(self) -> str | None:
        """Return the most recent progress summary from memory or disk."""
        if self._latest_summary is not None:
            return self._latest_summary
        return self._load_summary_standalone()

    # -- Session save/restore -------------------------------------------------

    def save_session(
        self,
        name: str,
        save_state_id: str | None,
        game_state_summary: str,
    ) -> SessionData:
        """Bundle current state into a session file on disk."""
        timestamp = datetime.now(timezone.utc)
        ts_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")
        session_id = f"session_{ts_str}_{name}"

        snapshot: dict[str, dict[str, str]] = {}
        for section in VALID_SECTIONS:
            snapshot[section] = self._kb.get_all(section)

        session = SessionData(
            session_id=session_id,
            timestamp=timestamp.isoformat(),
            save_state_id=save_state_id,
            progress_summary=self._latest_summary or self._load_summary_standalone() or "",
            knowledge_base_snapshot=snapshot,
            game_state_summary=game_state_summary,
            tool_call_count=self._tool_call_count,
        )

        self._write_atomic(self._session_path(session_id), session.to_dict())
        return session

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return metadata for all saved sessions, sorted newest first."""
        results: list[dict[str, Any]] = []
        for path in self._sessions_dir.glob("session_*.json"):
            try:
                data = json.loads(path.read_text())
                results.append({
                    "session_id": data.get("session_id", path.stem),
                    "timestamp": data.get("timestamp", ""),
                    "game_state_summary": data.get("game_state_summary", ""),
                    "tool_call_count": data.get("tool_call_count", 0),
                })
            except (json.JSONDecodeError, OSError):
                continue
        results.sort(key=lambda x: x["timestamp"], reverse=True)
        return results

    def load_session(self, session_id: str) -> SessionData:
        """Load a session bundle from disk."""
        path = self._session_path(session_id)
        if not path.exists():
            raise FileNotFoundError(f"Session '{session_id}' not found at {path}")
        data = json.loads(path.read_text())
        return SessionData.from_dict(data)

    def restore_session(self, session_id: str) -> SessionData:
        """Load a session and restore its KB snapshot into the live KB.

        Overwrites all current KB data with the snapshot. The caller (MCP tool)
        is responsible for also calling bridge.restore_save_state().
        """
        session = self.load_session(session_id)
        snapshot = session.knowledge_base_snapshot

        for section in VALID_SECTIONS:
            current = self._kb.get_all(section)
            snapshot_section = snapshot.get(section, {})

            # Delete keys in live KB that aren't in the snapshot
            for key in list(current.keys()):
                if key not in snapshot_section:
                    self._kb.delete(section, key)

            # Write all keys from the snapshot
            for key, value in snapshot_section.items():
                self._kb.write(section, key, value)

        # Restore the progress summary in memory
        if session.progress_summary:
            self._latest_summary = session.progress_summary

        return session

    # -- Internal -------------------------------------------------------------

    def _session_path(self, session_id: str) -> Path:
        return self._sessions_dir / f"{session_id}.json"

    def _write_atomic(self, path: Path, data: dict[str, Any]) -> None:
        """Atomic JSON write: write to tmp, then os.replace."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(str(tmp), str(path))

    def _save_summary_standalone(self, summary: str) -> None:
        """Persist the latest summary to data/sessions/_last_summary.json."""
        path = self._sessions_dir / "_last_summary.json"
        self._write_atomic(path, {"summary": summary})

    def _load_summary_standalone(self) -> str | None:
        """Load from data/sessions/_last_summary.json if it exists."""
        path = self._sessions_dir / "_last_summary.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return data.get("summary")
        except (json.JSONDecodeError, OSError):
            return None

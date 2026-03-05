"""Persistent knowledge base for Claude's long-term game memory.

Sections: map_data, npc_notes, battle_strategies, inventory, objectives, death_log.
Values are natural language strings written by Claude during gameplay.
Persisted to data/knowledge_base.json with atomic writes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

VALID_SECTIONS: frozenset[str] = frozenset({
    "map_data",
    "npc_notes",
    "battle_strategies",
    "inventory",
    "objectives",
    "death_log",
})


class KnowledgeBase:
    """Dict-backed persistent knowledge base with JSON file storage."""

    def __init__(self, save_path: str | Path) -> None:
        self._path = Path(save_path)
        self._data: dict[str, dict[str, str]] = {s: {} for s in VALID_SECTIONS}
        self._load()

    # -- Public API -----------------------------------------------------------

    def read(self, section: str, key: str) -> str | None:
        """Return the value for a key in a section, or None if not found."""
        self._validate_section(section)
        return self._data[section].get(key)

    def write(self, section: str, key: str, value: str) -> None:
        """Write a value to a section and persist to disk."""
        self._validate_section(section)
        self._data[section][key] = value
        self._save()

    def delete(self, section: str, key: str) -> bool:
        """Delete a key from a section. Returns True if the key existed."""
        self._validate_section(section)
        if key in self._data[section]:
            del self._data[section][key]
            self._save()
            return True
        return False

    def list_sections(self) -> dict[str, int]:
        """Return section names with their entry counts."""
        return {s: len(self._data[s]) for s in VALID_SECTIONS}

    def get_all(self, section: str) -> dict[str, str]:
        """Return all key-value pairs in a section."""
        self._validate_section(section)
        return dict(self._data[section])

    # -- Internal -------------------------------------------------------------

    def _validate_section(self, section: str) -> None:
        if section not in VALID_SECTIONS:
            raise ValueError(
                f"Invalid section '{section}'. Valid sections: {sorted(VALID_SECTIONS)}"
            )

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path) as f:
                loaded = json.load(f)
            for section in VALID_SECTIONS:
                if section in loaded and isinstance(loaded[section], dict):
                    self._data[section] = loaded[section]
        except (json.JSONDecodeError, OSError):
            pass  # Start with empty KB on corrupt file

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(self._data, f, indent=2)
        os.replace(str(tmp), str(self._path))

# MCP Tool Definitions

## Tool: get_game_state

Returns the complete current game state.

**Parameters:** None

**Returns:**
```json
{
  "frame": 123456,
  "game_mode": "overworld | battle | menu | dialog | transition",
  "player": {
    "name": "Ninten",
    "level": 5,
    "hp": 42,
    "max_hp": 68,
    "pp": 15,
    "max_pp": 30,
    "experience": 234,
    "status": "normal | poisoned | asleep | confused | paralyzed | stone",
    "learned_psi": ["Healing a", "PSI Shield a", "Telepathy"]
  },
  "party": [
    { "name": "Ana", "level": 3, "hp": 28, "max_hp": 35, "pp": 20, "max_pp": 40, "status": "normal", "learned_psi": ["PK Fire a", "PK Freeze a"] }
  ],
  "location": {
    "map_id": 12,
    "map_name": "Podunk",
    "x": 45,
    "y": 78
  },
  "inventory": ["Bread", "Orange Juice", "Wooden Bat"],
  "battle_state": {
    "enemy_name": "Lamp",
    "enemy_hp": 18,
    "turn": 2,
    "available_actions": ["BASH", "PSI", "GOODS", "RUN"],
    "menu_cursor": "BASH",
    "available_psi": ["Healing a", "PSI Shield a", "PK Fire a", "PK Freeze a"]
  },
  "dialog_state": {
    "text": "Welcome to Podunk!",
    "can_advance": true
  },
  "money": 500,
  "melodies_collected": 2,
  "current_objective": "Head east to Merrysville and find the next melody.",
  "screenshot_base64": "<base64 PNG data, omitted unless requested>"
}
```

**Notes:**
- `battle_state` is null when game_mode != "battle"
- `dialog_state` is null when game_mode != "dialog"
- `screenshot_base64` is included by default; pass `include_screenshot: false` to skip and save tokens. When smart screenshot policy is enabled, `include_screenshot: true` (default) lets the policy decide whether to actually capture
- `map_name` is resolved from map_id via a lookup table in `src/state_parser/map_names.py`
- `learned_psi` lists known PSI abilities for each character (empty for Lloyd/Teddy)
- `available_psi` in `battle_state` aggregates PSI from all party members with PSI
- `current_objective` provides a contextual hint based on melody count and current location
- `money` is cash on hand; `melodies_collected` tracks story progress (0–8)

**Latency target:** < 200ms

---

## Tool: execute_action

Sends a controller action to the emulator and returns the resulting state.

**Parameters:**
```json
{
  "action_type": "move | button | menu_navigate | text_advance | wait",
  "direction": "up | down | left | right",
  "button": "A | B | Start | Select",
  "menu_path": ["GOODS", "Bread"],
  "duration_frames": 15,
  "include_screenshot": true
}
```

**Field usage by action_type:**
| action_type | Required fields | Optional |
|---|---|---|
| move | direction, duration_frames | include_screenshot |
| button | button | duration_frames (default 2), include_screenshot |
| menu_navigate | menu_path | include_screenshot |
| text_advance | (none) | include_screenshot |
| wait | duration_frames | include_screenshot |

**Returns:**
```json
{
  "success": true,
  "action_performed": "move right for 15 frames",
  "game_state": { ... }
}
```

**Validation rules:**
- Cannot send `move` during battle mode
- Cannot send battle actions during overworld mode
- `duration_frames` max 120 (2 seconds at 60fps)
- `menu_path` entries must be valid menu option strings

**Latency target:** < 500ms (includes action execution + state capture)

---

## Tool: create_save_state

Creates an emulator save state checkpoint.

**Parameters:**
```json
{
  "label": "before_boss_fight"
}
```

**Returns:**
```json
{
  "save_state_id": "ss_20260305_143022_before_boss_fight",
  "timestamp": "2026-03-05T14:30:22Z",
  "game_state_summary": "Ninten Lv5 HP:68/68 at Podunk (45,78)"
}
```

---

## Tool: restore_save_state

Restores the emulator to a previous checkpoint.

**Parameters:**
```json
{
  "save_state_id": "ss_20260305_143022_before_boss_fight"
}
```

**Returns:**
```json
{
  "success": true,
  "restored_state": { ... }
}
```

---

## Tool: get_memory_value

Reads raw NES RAM. For debugging only — prefer get_game_state for gameplay.

**Parameters:**
```json
{
  "address": "0x0045",
  "length": 2
}
```

**Returns:**
```json
{
  "address": "0x0045",
  "hex": "2A00",
  "decimal": [42, 0]
}
```

---

## Tool: update_knowledge_base

Reads or writes to Claude's persistent knowledge base.

**Parameters:**
```json
{
  "operation": "read | write | delete | list_sections",
  "section": "map_data | npc_notes | battle_strategies | inventory | objectives | death_log",
  "key": "podunk_layout",
  "value": "Podunk is a small town. Department store to the east, mayor's office to the north."
}
```

**Returns (read):**
```json
{
  "section": "map_data",
  "key": "podunk_layout",
  "value": "Podunk is a small town. Department store to the east, mayor's office to the north."
}
```

**Returns (list_sections):**
```json
{
  "sections": {
    "map_data": 12,
    "npc_notes": 5,
    "battle_strategies": 3,
    "inventory": 1,
    "objectives": 2,
    "death_log": 0
  }
}
```

**Notes:**
- Values are strings (Claude writes natural language notes)
- Keys should be descriptive and snake_case
- Knowledge base persists across sessions via JSON file

---

## Tool: get_session_stats

Returns session statistics for context management.

**Parameters:** None

**Returns:**
```json
{
  "tool_call_count": 42,
  "summarization_threshold": 50,
  "should_summarize": false
}
```

---

## Tool: write_progress_summary

Writes a progress summary for continuity across conversations.

**Parameters:**
```json
{
  "summary": "At Podunk, Lv5, 2 melodies collected. Heading to Merrysville next."
}
```

---

## Tool: get_last_summary

Retrieves the most recent progress summary from a previous session.

**Parameters:** None

---

## Tool: save_session / list_sessions / restore_session

Session persistence tools — save/restore emulator state + knowledge base + progress summary.

---

## Tool: get_performance_dashboard

Returns gameplay performance metrics for the current session.

**Parameters:** None

**Returns:**
```json
{
  "session_elapsed_minutes": 12.5,
  "battles_won": 8,
  "battles_lost": 1,
  "battles_fled": 2,
  "total_battles": 11,
  "win_rate": 0.727,
  "deaths": 1,
  "distance_traveled_tiles": 340,
  "distance_per_minute": 27.2,
  "death_analysis": {
    "total_deaths": 1,
    "deaths_by_enemy": {"Gang Zombie": 1},
    "deaths_by_location": {"Podunk": 1},
    "deadliest_enemy": "Gang Zombie",
    "deadliest_area": "Podunk",
    "suggestions": ["Review enemy patterns and stock healing items."],
    "recent_deaths": [{"enemy": "Gang Zombie", "location": "Podunk", "hp_at_death": 0}]
  }
}
```

**Notes:**
- `death_analysis` is only included when deaths have been recorded with context
- `suggestions` are auto-generated: repeated enemy deaths trigger strategy advice, low-HP deaths suggest more aggressive healing
- `win_rate` is battles_won / total_battles (0.0 when no battles fought)

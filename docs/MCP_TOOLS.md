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
    "status": "normal | poisoned | asleep | confused | paralyzed | stone"
  },
  "party": [
    { "name": "Ana", "level": 3, "hp": 28, "max_hp": 35, "pp": 20, "max_pp": 40, "status": "normal" }
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
    "menu_cursor": "BASH"
  },
  "dialog_state": {
    "text": "Welcome to Podunk!",
    "can_advance": true
  },
  "screenshot_base64": "<base64 PNG data, omitted unless requested>"
}
```

**Notes:**
- `battle_state` is null when game_mode != "battle"
- `dialog_state` is null when game_mode != "dialog"
- `screenshot_base64` is included by default; pass `include_screenshot: false` to skip and save tokens
- `map_name` is resolved from map_id via a lookup table in `src/state_parser/map_names.py`

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

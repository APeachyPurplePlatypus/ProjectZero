# Implementation Specification

## Overview
Build an MCP server that bridges Claude with FCEUX (NES emulator) to play EarthBound Zero autonomously. The system has four layers: Lua scripts inside FCEUX, a Python emulator bridge, an MCP server, and a knowledge base for persistent memory.

## Phase 1: Emulator Bridge (Weeks 1–2)

### Goal
Establish two-way programmatic control of FCEUX running EarthBound Zero.

### Tasks
1. **Lua state exporter** (`lua/state_exporter.lua`)
   - Every frame, read critical memory addresses and write to `shared/state.json`
   - Fields: player_x, player_y, map_id, ninten_hp, ninten_max_hp, ninten_pp, ninten_max_pp, battle_flag, menu_state, dialog_active
   - Write frame number as monotonic counter so Python can detect staleness

2. **Lua input reader** (`lua/input_reader.lua`)
   - Every frame, check `shared/input.json` for pending commands
   - Apply via `joypad.set(1, {A=true})` etc.
   - Support: directional (up/down/left/right), buttons (A, B, Start, Select), hold duration (frames)
   - Clear command after applying

3. **Lua frame capture** (`lua/frame_capture.lua`)
   - On demand (triggered by flag in input.json), save screenshot to `shared/screenshot.png`
   - Use `gui.screenshot(path)` or `client.screenshot(path)`

4. **Lua main script** (`lua/main.lua`)
   - Loads and orchestrates the three modules above
   - Runs in FCEUX's emu.frameadvance() loop

5. **Python bridge** (`src/bridge/emulator_bridge.py`)
   - `class EmulatorBridge` with methods:
     - `start(rom_path)` — launches FCEUX subprocess with lua script
     - `get_state() -> GameState` — reads shared/state.json, returns parsed state
     - `send_input(button, duration_frames)` — writes to shared/input.json
     - `capture_screenshot() -> bytes` — triggers capture, reads PNG, returns base64
     - `create_save_state(label) -> str` — sends save state command
     - `restore_save_state(state_id)` — sends restore command
     - `is_alive() -> bool` — health check on FCEUX process
   - Handle file locking to prevent read/write races
   - Timeout and retry logic for stale state reads

6. **Validate memory addresses**
   - Use FCEUX memory viewer to confirm addresses from @docs/MEMORY_MAP.md
   - Write `scripts/validate_memory.py` that reads known values at game start

### Success Criteria
- Python can read Ninten's HP while game runs
- Python can make Ninten walk 10 steps in any direction
- Screenshot captured and saved as PNG from running game

---

## Phase 2: MCP Server & State Parser (Weeks 3–4)

### Goal
Wrap the emulator bridge in an MCP server with well-defined tools.

### Tasks
1. **MCP server** (`src/mcp_server/server.py`)
   - Use the MCP Python SDK (`mcp` package)
   - Register tools defined in @docs/MCP_TOOLS.md
   - Each tool calls EmulatorBridge methods
   - Handle errors gracefully (emulator crash, timeout, invalid action)
   - Rate limit: max 1 action per 100ms to prevent input flooding

2. **Game state parser** (`src/state_parser/parser.py`)
   - `class GameStateParser` with method:
     - `build_state(raw_memory: dict, screenshot: bytes | None) -> GameState`
   - Combines raw memory values into structured GameState dataclass
   - Detects game mode: overworld, battle, menu, dialog, transition
   - Mode detection logic:
     - battle_flag != 0 → battle
     - menu_state != 0 → menu
     - dialog_active != 0 → dialog
     - else → overworld

3. **GameState dataclass** (`src/state_parser/models.py`)
   - Fields per @docs/MCP_TOOLS.md get_game_state return schema
   - Use Pydantic for validation and JSON serialization

4. **Input validation** (`src/mcp_server/validation.py`)
   - Reject movement commands during battle
   - Reject battle commands during overworld
   - Validate button names and directions
   - Return helpful error messages

### Success Criteria
- Claude Code / Claude Desktop connects to MCP server
- `get_game_state` returns valid JSON with correct HP, position, game mode
- `execute_action` moves character and returns updated state
- Save state round-trip works

---

## Phase 3: First Playthrough Milestone (Weeks 5–6)

### Goal
Claude autonomously plays from title screen through first battle victory.

### Tasks
1. **System prompt** (`docs/system_prompt.md`)
   - Describes Claude's role as a game player
   - Explains available tools and when to use them
   - Provides EarthBound Zero basic mechanics summary
   - Instructs: observe → think → act loop
   - Battle strategy hints: use BASH for basic attacks, heal when HP < 30%

2. **Title screen automation** — test that Claude can:
   - Press Start at title screen
   - Navigate "NEW GAME" selection
   - Advance through intro dialog (repeated A presses)

3. **Overworld navigation** — test that Claude can:
   - Identify current location from state
   - Move in cardinal directions
   - Recognize when entering a building or new area

4. **Battle handling** — test that Claude can:
   - Detect battle start from game mode change
   - Navigate battle menu (BASH / PSI / GOODS / RUN)
   - Select BASH and confirm target
   - Recognize battle end and return to overworld

5. **Save state checkpointing**
   - Auto-save before entering new areas
   - Auto-save when HP is full after healing
   - Restore on game over

### Success Criteria
- Claude completes title → first battle sequence unassisted
- Claude wins 5 consecutive random encounters
- System runs 15+ minutes without crashing

---

## Phase 4: Knowledge Base & Context Management (Weeks 7–8)

### Goal
Persistent memory system so Claude can play extended sessions.

### Tasks
1. **Knowledge base** (`src/knowledge_base/kb.py`)
   - Python dict with sections: map_data, npc_notes, battle_strategies, inventory, objectives, death_log
   - JSON persistence to `data/knowledge_base.json`
   - MCP tool `update_knowledge_base` for read/write/delete operations
   - Claude writes observations, strategies, and progress notes here

2. **Progressive summarization**
   - When conversation history exceeds threshold (~50 tool calls), trigger summarization
   - Claude writes a progress summary
   - History is cleared; summary becomes the first assistant message
   - Knowledge base persists across summarizations

3. **Session save/restore**
   - Save: emulator save state + knowledge_base.json + last summary
   - Restore: reload all three components, Claude resumes from summary

### Success Criteria
- Claude maintains coherent play across context window resets
- Knowledge base grows with useful observations
- Session can be paused and resumed

---

## Phase 5: Extended Play & Optimization (Weeks 9–12)

### Goal
Claude plays for 30+ minutes, handling full game mechanics.

### Tasks (Items 1–7 implemented, Item 8 is testing/validation)

1. **Multi-party management** — `src/state_parser/parser.py` builds `party` list from SRAM ally slots; `FullGameState.party` returns each ally's name, level, HP, PP, status, and learned PSI. Equipment tracking via inventory.

2. **PSI system usage in battles** — `src/state_parser/psi_names.py` maps ~28 PSI ability IDs to names, PP costs, and types (offense/defense/healing/assist). Lua reads 8 PSI slots per character (Ninten + Ana). `PlayerState.learned_psi` lists each character's known PSI; `BattleState.available_psi` aggregates all party PSI for battle decisions.

3. **Inventory management** — `src/state_parser/parser.py` reads 32 item slots (8 per character) from SRAM. `FullGameState.inventory` returns item display names via `item_names.py`. Money tracked in `FullGameState.money`.

4. **Navigation toward story objectives** — `src/state_parser/story_objectives.py` provides contextual hints based on melody count (0–8) and current map ID. `FullGameState.current_objective` gives Claude a one-line hint for what to do next. Map-specific overrides provide location-aware guidance.

5. **Death recovery with strategy adaptation** — `DeathContext` dataclass captures enemy name, map name, HP at death, and party HP. `PerformanceTracker.record_death_with_context()` stores context; `get_death_analysis()` identifies deadliest enemies/areas and generates suggestions (repeated enemy → update strategy, low HP deaths → heal more aggressively). Deaths auto-logged to KB `death_log` section.

6. **Performance dashboard** — `PerformanceTracker` in `src/mcp_server/performance.py` tracks battle wins/losses/fled, deaths, Manhattan distance traveled, and session elapsed time. `get_performance_dashboard` MCP tool returns all metrics including death analysis when deaths have context.

7. **Cost optimization (screenshot policy)** — `ScreenshotPolicy` in `src/mcp_server/screenshot_policy.py` intelligently skips screenshots for routine same-map/same-mode actions. Includes screenshots on first action, mode transitions, new map entry, and periodically (every N actions). Explicit `include_screenshot=false` always skips. Configured via `config.json` gameplay settings.

8. **Testing & validation** — Comprehensive unit test suite covering all Phase 5 features. Target: 250+ tests across PSI names, story objectives, party/inventory parsing, performance tracking, death analysis, screenshot policy, and MCP integration.

### Success Criteria
- 30-minute autonomous sessions without crashes
- Reaches first major story milestone (Podunk → Merrysville progression)
- Random encounter win rate > 80%
- 250+ unit tests passing
- Death analysis produces actionable strategy suggestions

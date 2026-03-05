# EarthBound Zero AI Player

## What This Is
An autonomous AI system that enables Claude to play EarthBound Zero (Mother 1) on the NES. Claude observes game state through memory reads + screenshots, makes strategic decisions, and executes actions via programmatic controller input — all connected through an MCP server.

## Architecture
```
Claude <-> MCP Server (Python) <-> Emulator Bridge (Python/Lua) <-> FCEUX (NES emulator)
                                        ├── Memory Reader (Lua)
                                        ├── Frame Capturer (Lua)
                                        └── Input Controller (Lua)
```

**IPC pattern:** FCEUX runs a Lua script that reads/writes shared JSON files. Python bridge reads state files and writes input files. MCP server wraps the bridge and exposes tools to Claude.

## Tech Stack
- **Emulator:** FCEUX 2.6+ (Lua 5.1 scripting)
- **MCP Server:** Python 3.11+ with MCP Python SDK
- **IPC:** File-based JSON (state.json, input.json)
- **Vision:** Pillow for screenshots, Claude vision API for OCR fallback
- **Knowledge Base:** Python dict with JSON persistence

## Key Directories
- `lua/` — FCEUX Lua scripts (memory reader, input injector, frame capture)
- `src/bridge/` — Python emulator bridge (reads state, writes input, manages FCEUX process)
- `src/mcp-server/` — MCP server implementation (tool definitions, request handling)
- `src/state-parser/` — Game state JSON builder (combines memory + vision)
- `src/knowledge-base/` — Persistent knowledge base for long-term game memory
- `scripts/` — Setup, testing, and utility scripts
- `docs/` — Specs, memory maps, architecture decisions

## Commands
- `python scripts/setup.py` — Install dependencies and verify FCEUX
- `python scripts/test_bridge.py` — Test emulator bridge IPC round-trip
- `python scripts/start_game.py <rom_path>` — Launch FCEUX + Lua bridge (run before Claude Desktop)
- `python -m src.mcp_server` — Start the MCP server manually (Claude Desktop does this automatically)

## Playing with Claude Desktop

1. **Start the game** (Terminal):
   ```
   python scripts/start_game.py <rom_path>
   ```
   Or set `emulator.rom_path` in `config.json` and run without arguments.

2. **Open Claude Desktop** — the `earthbound-zero` MCP server connects automatically.

3. **Start playing** — paste `docs/system_prompt.md` as your first message, then let Claude play.

The MCP server is registered in `claude_desktop_config.json` pointing to `scripts/mcp_entry.py`.

## Code Style
- Python: Use type hints everywhere. Async where needed (MCP SDK). `ruff` for linting.
- Lua: FCEUX Lua 5.1 — no external modules. Keep scripts under 200 lines each.
- All config via environment variables or `config.json` in project root.
- Prefer composition over inheritance. Small functions, clear names.

## Testing
- `pytest tests/` for Python unit tests
- `python scripts/test_bridge.py` for integration tests against live emulator
- Test memory reads against known game states (save states in `tests/fixtures/`)

## Important Constraints
- FCEUX Lua API is synchronous and runs per-frame — do not block the emulator loop
- MCP tool responses must be < 200ms for get_game_state, < 500ms for execute_action
- Screenshots are expensive tokens — use memory-only state for routine observations
- The NES RAM map addresses MUST be validated against the specific ROM version
- Knowledge base sections: map_data, npc_notes, battle_strategies, inventory, objectives, death_log

## Specs
- @docs/SPEC.md — Full implementation specification
- @docs/MEMORY_MAP.md — NES RAM address reference
- @docs/MCP_TOOLS.md — MCP tool definitions and schemas
- @docs/ARCHITECTURE.md — Architecture decisions and rationale

Implement Phase 2: MCP Server & State Parser. Read @docs/SPEC.md and @docs/MCP_TOOLS.md for full specifications.

Your tasks:
1. Create `src/state_parser/models.py` — Pydantic models for GameState, PlayerState, BattleState, DialogState, Location
2. Create `src/state_parser/parser.py` — GameStateParser class that builds GameState from raw memory dict
3. Create `src/state_parser/map_names.py` — map_id → map_name lookup table
4. Create `src/mcp_server/validation.py` — input validation (reject invalid actions for current game mode)
5. Create `src/mcp_server/server.py` — MCP server with all 6 tools from @docs/MCP_TOOLS.md
6. Create `src/mcp_server/__main__.py` — entry point for `python -m src.mcp_server`
7. Create `tests/test_state_parser.py` — unit tests for state parser with mock memory data
8. Create `tests/test_validation.py` — unit tests for input validation logic

Use the MCP Python SDK (`mcp` package). Each tool function should call EmulatorBridge methods from Phase 1.

Rate limit execute_action to max 1 call per 100ms. Return helpful error messages for invalid actions.

Include type hints on all functions. Use async where the MCP SDK requires it.

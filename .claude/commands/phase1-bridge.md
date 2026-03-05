Implement Phase 1: Emulator Bridge. Read @docs/SPEC.md for the full specification.

Your tasks:
1. Create `lua/state_exporter.lua` — reads memory addresses from @docs/MEMORY_MAP.md every frame, writes JSON to `shared/state.json`
2. Create `lua/input_reader.lua` — reads `shared/input.json` every frame, applies button presses via joypad.set()
3. Create `lua/frame_capture.lua` — captures screenshot on demand to `shared/screenshot.png`
4. Create `lua/main.lua` — orchestrates the three modules in an emu.frameadvance() loop
5. Create `src/bridge/emulator_bridge.py` — Python class that launches FCEUX, reads state, writes input, captures screenshots
6. Create `scripts/test_bridge.py` — integration test that starts emulator, reads HP, sends input, captures screenshot

Use atomic file writes (write temp, rename) to prevent read/write races. Include a monotonic frame counter in state.json for staleness detection.

For memory addresses that are TBD, use placeholder values and add a TODO comment. The validation script will fill these in later.

Start with the Lua scripts, then the Python bridge, then the test script. Verify each layer works before moving to the next.

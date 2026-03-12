# Implementation Summary: Name Entry Navigation + Lua Console Output

## Context
Claude plays EarthBound Zero by sending IPC commands to FCEUX via JSON files.
Two problems were observed during the first play session:

1. **Lua console is silent** — FCEUX's Lua console shows nothing. The scripts only
   call `emu.message()` (on-screen overlay, 3-second flash) and never `print()`
   (which goes to the persistent Lua console window).

2. **Name entry produced gibberish** — During new-game setup the name-entry screen
   shows a letter grid. Pressing A selects the currently highlighted letter (starts
   at 'A'), so rapid A-presses filled every name with "AAAAAAA". Characters then
   have unrecognizable names, making it impossible to track party members by name.

---

## Fix 1 — Lua Console Output

Add `print()` calls to the three Lua scripts. Do **not** print every frame; use
throttling or event-driven prints only.

### `lua/main.lua`
After `write_ready_marker()` and the existing `emu.message(...)`:
```lua
print("[EB0] Lua bridge initialized. Shared dir: " .. SHARED_DIR)
print("[EB0] Listening for commands...")
```

Inside the `while true` loop, add a heartbeat every 300 frames (~5 s):
```lua
if frame % 300 == 0 then
    print(string.format("[EB0] frame=%d map=%d hp=%d",
        frame,
        memory.readbyte(0x0015),
        memory.readword(0x7454)))
end
```

When the screenshot relay fires:
```lua
print("[EB0] Screenshot captured at frame " .. frame)
```

### `lua/input_reader.lua`
When a new command is received (inside `if cmd then`):
```lua
print(string.format("[EB0] CMD: %s btn=%s dir=%s frames=%d id=%d",
    cmd.command or "?",
    tostring(cmd.button),
    tostring(cmd.direction),
    cmd.duration_frames or 0,
    cmd.frame_id or 0))
```

When the command completes (just before `write_done`):
```lua
print("[EB0] CMD done: frame_id=" .. current_frame_id)
```

### `lua/frame_capture.lua`
When capture fires (inside `if M.capture_requested`):
```lua
print("[EB0] Saving screenshot to " .. path)
```

---

## Fix 2 — Name Entry Navigation

### How the name-entry screen works
The cursor starts at letter **'A'** (row 0, col 0) in a 14-column × 4-row grid:

```
Row 0:  A B C D E F G   H I J K L M N   cols 0-13
Row 1:  O P Q R S T U   V W X Y Z . '   cols 0-13
Row 2:  a b c d e f g   h i j k l m n   cols 0-13
Row 3:  o p q r s t u   v w x y z - :   cols 0-13
Row 4:  ◄Back  (col 0)    ▲End (col 7)
Row 5:  ▲Previous (col ~4)
```

- **D-pad** moves the cursor one cell at a time.
- **A** selects the highlighted letter (appends to name) or activates Back/End.
- **Start** accepts whatever is currently in the name buffer and advances to the
  next screen — this is why pressing Start left "AAAAAAA" in the buffer.

### Letter position table (row, col)
```python
LETTER_GRID = {}
upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ.'"
lower = "abcdefghijklmnopqrstuvwxyz-:"
for i, ch in enumerate(upper):
    row = i // 14         # 0 or 1
    col = i % 14
    LETTER_GRID[ch] = (row, col)
for i, ch in enumerate(lower):
    row = 2 + i // 14     # 2 or 3
    col = i % 14
    LETTER_GRID[ch] = (row, col)
LETTER_GRID["End"]  = (4, 7)
LETTER_GRID["Back"] = (4, 0)
```

### Algorithm: `navigate_to(target, current_pos) -> list[actions]`
Compute `dr = target_row - cur_row`, `dc = target_col - cur_col`.
Emit the required number of up/down/left/right move commands (1 frame each),
then emit an A press.

Wrap-around: the grid wraps horizontally (col 13 → col 0 via right) and
vertically (row 5 → row 0 via up). Always take the shorter path.

### `type_name(name: str, bridge)` — Python helper function
```python
def type_name(name: str, bridge, send_fn):
    """Navigate the name-entry cursor to spell out `name` then select End."""
    cur = (0, 0)                          # cursor starts at 'A'
    for ch in name:
        target = LETTER_GRID[ch]
        _move_cursor(cur, target, send_fn)
        send_fn('button', button='A', duration_frames=3)
        send_fn('wait', duration_frames=8)
        cur = target
    # Navigate to End and confirm
    _move_cursor(cur, LETTER_GRID["End"], send_fn)
    send_fn('button', button='A', duration_frames=3)
    send_fn('wait', duration_frames=30)   # wait for screen to advance

def _move_cursor(cur, target, send_fn):
    r0, c0 = cur
    r1, c1 = target
    # Vertical movement
    dr = r1 - r0
    direction = 'down' if dr > 0 else 'up'
    for _ in range(abs(dr)):
        send_fn('move', direction=direction, duration_frames=2)
        send_fn('wait', duration_frames=4)
    # Horizontal movement
    dc = c1 - c0
    direction = 'right' if dc > 0 else 'left'
    for _ in range(abs(dc)):
        send_fn('move', direction=direction, duration_frames=2)
        send_fn('wait', duration_frames=4)
```

### `start_new_game(names: dict, bridge, send_fn)`
Called once after the game reaches the first name-entry screen.

```python
DEFAULT_NAMES = {
    "boy":   "Ninten",   # protagonist
    "girl":  "Ana",
    "boy2":  "Lloyd",
    "boy3":  "Teddy",
    "food":  "Steak",    # favorite food (affects a PSI move's name)
}

def start_new_game(names: dict, bridge, send_fn):
    for key in ["boy", "girl", "boy2", "boy3", "food"]:
        # Wait for name screen to settle
        send_fn('wait', duration_frames=60)
        type_name(names.get(key, ""), bridge, send_fn)
    # Confirmation screen: "Is this OK? Yes / No" — move to Yes and press A
    send_fn('wait', duration_frames=60)
    send_fn('button', button='A', duration_frames=5)   # Yes is selected by default
    send_fn('wait', duration_frames=120)               # wait for intro to start
```

### Where to put this code
- Add `LETTER_GRID`, `type_name`, `_move_cursor`, `start_new_game`, and
  `DEFAULT_NAMES` to a new file: **`scripts/play_utils.py`**.
- Import from `scripts/play_utils.py` in any play/test scripts.
- The `send_fn` parameter matches the `send()` helper used in the play session.

---

---

## Fix 3 — Overworld Menu Interrupt (A button)

### Problem
On the overworld, pressing **A** opens the Command menu (Talk / Check / Goods /
State / PSI / Setup), which freezes movement until dismissed. During the play
session, A-presses intended to advance battle/dialog text were landing on the
overworld and blocking all subsequent movement commands.

### Rule
**Never press A on the overworld.** D-pad alone is sufficient for movement.
After every battle or dialog sequence, always press **B** once before issuing
any move commands, to ensure any lingering menu state is cleared.

### Implementation in `scripts/play_utils.py`
Add a `safe_move(bridge, send_fn, direction, frames)` wrapper that:
1. Reads current `menu_state` and `dialog_active` from `bridge.get_state()`.
2. If either is nonzero, calls `send_fn('button', button='B', duration_frames=3)`
   then waits 15 frames before moving.
3. Only then issues the move command.

```python
def safe_move(bridge, send_fn, direction, frames=15):
    """Move with automatic menu-close guard."""
    state = bridge.get_state()
    if state.menu_state != 0 or state.dialog_active != 0:
        send_fn('button', button='B', duration_frames=3)
        send_fn('wait', duration_frames=15)
    send_fn('move', direction=direction, duration_frames=frames)
```

> **Note**: `menu_state` and `dialog_active` are currently hardcoded to 0 in
> `state_exporter.lua` (addresses TBD — see MEMORY_MAP.md). Until those addresses
> are found, the guard must rely on visual inspection (screenshot) or a post-battle
> B-press convention rather than memory values.

---

## Fix 4 — MCP Server Attach Mode (already implemented, needs restart)

### Problem
The `earthbound-zero` MCP tools (used by Claude Code) all return
`"Emulator not running"` because the MCP server's `EmulatorBridge` instance is
created without calling `start()`, leaving `_process = None` and `is_alive()`
returning False.

### What was already implemented (session of 2026-03-11)
- **`src/bridge/emulator_bridge.py`** — Added `attach(timeout)` method that checks
  for `lua_ready.json` and `state.json` in the shared dir (no process ownership
  required). Updated `is_alive()` to return `True` when attached and `state.json`
  exists.
- **`src/mcp_server/server.py`** — Added auto-attach in `app_lifespan`: if
  `bridge.is_alive()` is False after construction, call `bridge.attach(timeout=5.0)`
  so the server connects to an already-running FCEUX.

### What still needs to happen
The MCP server process must be **restarted** for these changes to take effect.
After restarting:
1. Run `python scripts/start_game.py <rom_path>` (starts FCEUX + Lua).
2. Claude Code reconnects to MCP — the server now auto-attaches.
3. `mcp__earthbound-zero__get_game_state` should return real state instead of error.

### No further code changes needed for Fix 4.

---

## Fix 5 — `combat_active` Field is Inverted in Parser

### Problem
`state_exporter.lua` line 214 correctly inverts the raw hardware flag:
```lua
combat_active = (combat_raw == 0) and 1 or 0,
```
So `combat_active=1` in `state.json` means **in battle**, and `0` means overworld.

However, during the play session `combat_active` read as `1` on the overworld,
suggesting either:
- Address `$0047` does not reliably signal battle state in the early game (before
  any real battle has been entered via a map encounter), or
- The address is only valid during active combat turns, not the full encounter.

The Python parser (`src/state_parser/parser.py`) treats `raw.combat_active != 0`
as battle mode — which is **correct** given the Lua inversion — but the underlying
address needs validation.

### Action required
1. **Validate address `$0047`** using FCEUX RAM Search:
   - Load the game, walk into a random encounter in Podunk.
   - Check `$0047` raw value during: overworld → encounter start → enemy turn →
     player turn → battle end.
   - Document the exact values at each phase.
2. Until validated, do **not** rely on `combat_active` for battle detection in
   autonomous play. Use screenshot analysis (battle UI visible) as a fallback.
3. Update `MEMORY_MAP.md` with confirmed values once tested.

### No code changes yet — validation first.

---

## Files to modify

| File | Change |
|---|---|
| `lua/main.lua` | Add `print()` on init and in frame loop (heartbeat + screenshot event) |
| `lua/input_reader.lua` | Add `print()` on command receive and command complete |
| `lua/frame_capture.lua` | Add `print()` on screenshot save |
| `scripts/play_utils.py` | **New file** — `LETTER_GRID`, `type_name`, `start_new_game`, `safe_move` |
| `src/bridge/emulator_bridge.py` | Already updated — `attach()` + `is_alive()` attach mode |
| `src/mcp_server/server.py` | Already updated — auto-attach in `app_lifespan` |
| `docs/MEMORY_MAP.md` | Update `$0047` entry after empirical validation |

---

## Testing
1. **Lua console**: Restart FCEUX with the Lua script. Open FCEUX → View → Lua
   Console. Verify `[EB0] Lua bridge initialized` appears immediately and heartbeat
   lines appear every ~5 seconds.
2. **Name entry**: Start a new game via `start_new_game(DEFAULT_NAMES, bridge, send)`.
   Verify the confirmation screen shows "Ninten / Ana / Lloyd / Teddy / Steak".
3. **MCP attach**: Restart Claude Code's MCP server. Call `get_game_state` — it
   should return real state (not the "Emulator not running" error).
4. **Overworld menu guard**: After a battle ends, verify a B-press clears the menu
   before movement commands are sent.
5. **`combat_active` validation**: Enter a random encounter in Podunk. Use
   `get_memory_value(address="0x0047")` at overworld, battle start, and battle end.
   Record and document all three values.

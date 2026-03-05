# EarthBound Zero (Mother 1) — NES RAM Map

## Status
**DRAFT — All addresses must be validated against your specific ROM version.**

Primary sources: datacrystal.romhacking.net, TASVideos, speedrun.com community docs.

## How to Validate
1. Open ROM in FCEUX
2. Open Debug → RAM Search / Hex Editor
3. Play to a known state (e.g., Ninten at home, HP full)
4. Verify values at listed addresses match expected values
5. Update this doc with confirmed addresses

Run `scripts/validate_memory.py` to automate checks against a known save state.

---

## Critical Addresses (Phase 1)

These are needed for the minimum viable game state parser.

| Category | Address | Size | Type | Notes |
|---|---|---|---|---|
| Player X (map) | TBD | 1-2B | uint | Horizontal tile position |
| Player Y (map) | TBD | 1-2B | uint | Vertical tile position |
| Current Map ID | TBD | 1B | uint | Area/room identifier |
| Ninten Current HP | TBD | 2B | uint16 LE | Little-endian |
| Ninten Max HP | TBD | 2B | uint16 LE | |
| Ninten Current PP | TBD | 2B | uint16 LE | |
| Ninten Max PP | TBD | 2B | uint16 LE | |
| Ninten Level | TBD | 1B | uint | 1–99 range |
| Ninten Experience | TBD | 2-3B | uint | |
| Battle Flag | TBD | 1B | uint | 0=overworld, nonzero=battle |
| Menu State | TBD | 1B | uint | 0=closed, varies by menu |
| Dialog Active | TBD | 1B | bool | Nonzero when text box showing |
| Ninten Status | TBD | 1B | bitfield | Poison/sleep/confuse/etc |

## Party Data (Phase 3+)

| Category | Address | Size | Notes |
|---|---|---|---|
| Party member count | TBD | 1B | 1–4 |
| Ana HP | TBD | 2B | Second party slot |
| Ana Max HP | TBD | 2B | |
| Lloyd HP | TBD | 2B | Third party slot |
| Teddy HP | TBD | 2B | Fourth party slot |

## Battle Data (Phase 3)

| Category | Address | Size | Notes |
|---|---|---|---|
| Enemy ID | TBD | 1B | Lookup for name/stats |
| Enemy Current HP | TBD | 2B | |
| Enemy Max HP | TBD | 2B | From enemy data table |
| Battle menu cursor | TBD | 1B | 0=BASH,1=PSI,2=GOODS,3=RUN |
| Turn counter | TBD | 1B | |

## Inventory (Phase 4)

| Category | Address | Size | Notes |
|---|---|---|---|
| Inventory slot 1 | TBD | 1B | Item ID |
| Inventory slot 2 | TBD | 1B | |
| ... (up to slot N) | TBD | 1B | |
| Money | TBD | 2-3B | |

## Event Flags (Phase 5)

| Category | Address | Size | Notes |
|---|---|---|---|
| Story progress | TBD | Bitfield | Key plot flags |
| Key items obtained | TBD | Bitfield | Franklin Badge, etc |
| Melodies collected | TBD | 1B | 0–8 melody count |

---

## Research Tasks
1. Search datacrystal.romhacking.net for "Mother" or "Earth Bound" RAM map
2. Search TASVideos for Mother 1 / EarthBound Zero game resources
3. Check if existing FCEUX Lua scripts for this game exist (GitHub search)
4. Use FCEUX RAM Search to find addresses empirically:
   - HP: Take damage, search for decreased value
   - Position: Move right, search for increased X
   - Battle: Enter battle, search for changed values
5. Document ROM version (header hash) for reproducibility

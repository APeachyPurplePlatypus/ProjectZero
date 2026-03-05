# EarthBound Zero (Mother 1) — NES RAM Map

## Status
**COMMUNITY-SOURCED — Addresses must be validated against your specific ROM version.**

Primary source: [DataCrystal EarthBound Beginnings/RAM map](https://datacrystal.tcrf.net/wiki/EarthBound_Beginnings/RAM_map)
Secondary: [TASVideos EarthBound Beginnings](https://tasvideos.org/527G), community cheat databases.

ROM versions referenced:
- `Earthbound (U) (Prototype).nes` — US prototype (fan-called "EarthBound Zero")
- `Mother (J).nes` — Japanese original

## How to Validate
1. Open ROM in FCEUX
2. Open Debug → RAM Search / Hex Editor
3. Play to a known state (e.g., Ninten at home, HP full)
4. Verify values at listed addresses match expected values
5. Update this doc with confirmed addresses

Run `scripts/validate_memory.py` to automate checks against a known save state.

---

## NES Memory Layout Reference

| Range | Size | Region | Notes |
|---|---|---|---|
| $0000–$07FF | 2 KB | Internal RAM | Main working RAM |
| $0800–$1FFF | — | Mirrors | Mirrors of $0000–$07FF |
| $2000–$3FFF | — | PPU Registers | Graphics hardware |
| $4000–$401F | — | APU/I/O | Audio + controller |
| $6000–$7FFF | 8 KB | SRAM (battery-backed) | Save data + game state |
| $8000–$FFFF | 32 KB | PRG-ROM (banked) | Game code (MMC3 mapper) |

---

## Critical Addresses (Phase 1)

These are needed for the minimum viable game state parser.

### Overworld State (Internal RAM)

| Category | Address | Size | Type | Notes |
|---|---|---|---|---|
| Player Direction | $000C | 1B | uint | 0=Up, 1=Up-Right, 2=Right, 3=Down-Right, 4=Down, 5=Down-Left, 6=Left, 7=Up-Left |
| Current Area/Map ID | $0015 | 1B | uint | Area identifier — use as map_id |
| Player Coordinates | $0018–$001B | 4B | special | X/Y packed non-standard — see Coordinate Decoding below |
| Player Movement State | $00A0 | 1B | uint | $88=standing still, 0–7=moving in direction (same encoding as $000C) |
| Walk Cycle Timer | $00E7 | 1B | uint | Animation frame counter |

### Coordinate Decoding

Coordinates at $0018–$001B are stored in a non-standard packed format. To decode:

```python
def decode_coordinates(b0, b1, b2, b3):
    """Decode 4 bytes at $0018-$001B into X,Y tile coordinates.

    Format is packed: each coordinate uses ~10 bits across 2 bytes.
    This formula needs empirical validation against known positions.
    """
    # Method 1: Treat as two 16-bit little-endian words, then scale
    raw_x = b0 | (b1 << 8)
    raw_y = b2 | (b3 << 8)
    tile_x = raw_x >> 4  # TODO: validate shift amount
    tile_y = raw_y >> 4  # TODO: validate shift amount
    return tile_x, tile_y
```

**VALIDATION NEEDED:** The exact bit-packing format must be confirmed empirically:
1. Stand at a known position (e.g., Ninten's house entrance)
2. Read $0018–$001B raw bytes
3. Move right 1 tile, re-read, observe which bits changed
4. Derive the actual shift/mask formula

### Combat Detection (Internal RAM)

| Category | Address | Size | Type | Notes |
|---|---|---|---|---|
| Combat Active Flag | $0047 | 1B | uint | **0=in combat, 1=combat finished** (inverted logic!) |
| Enemy Group ID | $0048 | 1B | uint | Index into enemy group table |
| Boss Flag | $0056 | 1B | uint | 0=normal encounter, nonzero=boss ID |

**Note:** The combat flag at $0047 uses **inverted logic** — 0 means combat is active. For the game state parser, use: `in_battle = (memory.read(0x0047) == 0) AND (some_confirmation)`. This needs validation — it may be that $0047 is 0 only during active combat turns.

### Controller / Input (Internal RAM)

| Category | Address | Size | Type | Notes |
|---|---|---|---|---|
| Controller Input | $00D9 | 1B | bitfield | Bit 0=Right, 1=Left, 2=Down, 3=Up, 4=Start, 5=Select, 6=B, 7=A |

### System (Internal RAM)

| Category | Address | Size | Type | Notes |
|---|---|---|---|---|
| Copy Protection | $0006 | 1B | uint | $E5 on checksum failure, $00 normal |
| RNG State | $0026–$0027 | 2B | uint16 | Random number generator seed |
| PPU Buffer | $0110–$014F | 64B | buffer | Data staging for PPU writes |

### Menu/Dialog State

**NOT YET FOUND** — No specific addresses for menu state or dialog-active flag were documented in DataCrystal. These must be found empirically:

| Category | Address | Size | Type | Empirical Approach |
|---|---|---|---|---|
| Menu State | TBD | 1B | uint | Open menu, use FCEUX RAM Search for values that changed from 0 to nonzero |
| Dialog Active | TBD | 1B | bool | Talk to NPC, search for changed bytes. Look in $0040–$00FF range |
| Battle Menu Cursor | TBD | 1B | uint | In battle, move cursor between BASH/PSI/GOODS/RUN, search for 0–3 cycle |

---

## Character Stats (SRAM)

Character data is stored in 64-byte structs within the save slot structure in SRAM ($6000–$7FFF).

### Save Slot Layout

The game maintains 4 copies of save data:

| SRAM Offset | CPU Address | Size | Description |
|---|---|---|---|
| $1400 | $7400 | 768B | "Last Save" — most recent save / possibly live game state |
| $1700 | $7700 | 768B | Save Slot 1 |
| $1A00 | $7A00 | 768B | Save Slot 2 |
| $1D00 | $7D00 | 768B | Save Slot 3 |

### Save Slot Header

| Offset | Size | Description | Notes |
|---|---|---|---|
| +$00–$01 | 2B | Checksum | Subtraction mod $10000 |
| +$02 | 1B | Slot Number | $B0=slot1, $B1=slot2, $B2=slot3 |
| +$03 | 1B | Slot State | $7E=valid, $00=deleted |
| +$04–$07 | 4B | Player Position | Coordinates at save time |
| +$08–$0B | 4B | Party Members | 0=empty, otherwise ally ID |
| +$0C–$0F | 4B | Last Save Position | Position at last Dad phone call |
| +$10–$11 | 2B | Money | Cash on hand |
| +$12–$14 | 3B | Bank Money | Money deposited at ATM |
| +$20–$30 | 17B | Player Name | Player's chosen name |

### Character Status Struct (64 bytes each)

Located within the save slot at these offsets:

| Character | Save Slot Offset | CPU Address (in "Last Save") |
|---|---|---|
| Ninten | +$40 | $7440 |
| Ana | +$80 | $7480 |
| Lloyd | +$C0 | $74C0 |
| Teddy | +$100 | $7500 |
| Pippi | +$140 | $7540 |
| EVE | +$180 | $7580 |
| Flying Man | +$1C0 | $75C0 |

### Character Struct Fields

Each character uses this 64-byte layout:

| Offset | Size | Field | Type | Notes |
|---|---|---|---|---|
| +$01 | 1B | Status Condition | bitfield | Bit 0=Cold, 1=Poison, 2=Puzzled, 3=Confused, 4=Sleep, 5=Paralysis, 6=Stone, 7=Unconscious |
| +$03–$04 | 2B | Max HP | uint16 LE | |
| +$05–$06 | 2B | Max PP | uint16 LE | |
| +$07–$08 | 2B | Offense | uint16 LE | Attack power |
| +$09–$0A | 2B | Defense | uint16 LE | |
| +$0B | 1B | Fight | uint | Combat skill rating |
| +$0C | 1B | Speed | uint | |
| +$0D | 1B | Wisdom | uint | |
| +$0E | 1B | Strength | uint | |
| +$0F | 1B | Force | uint | PSI force stat |
| +$10 | 1B | Level | uint | 1–99 |
| +$11–$13 | 3B | Experience | uint24 LE | Total XP earned |
| +$14–$15 | 2B | Current HP | uint16 LE | |
| +$16–$17 | 2B | Current PP | uint16 LE | |
| +$20–$27 | 8B | Inventory | uint[8] | Item IDs, 8 slots per character |
| +$28 | 1B | Weapon | uint | Equipped weapon ID |
| +$29 | 1B | Coin | uint | Equipped coin ID |
| +$2A | 1B | Ring | uint | Equipped ring ID |
| +$2B | 1B | Pendant | uint | Equipped pendant ID |
| +$30–$37 | 8B | Learned PSI | uint[8] | Known PSI ability IDs |
| +$38–$3E | 7B | Name | string | Character display name |

### Computed Character Addresses (Phase 1 — Ninten via "Last Save")

**IMPORTANT:** These assume the "Last Save" block ($7400) reflects live game state. This MUST be validated — it may only update on actual save. If so, the live state may be elsewhere (possibly in the unknown SRAM region $6000–$677F or mirrored in internal RAM during gameplay).

| Field | CPU Address | Size | Notes |
|---|---|---|---|
| Ninten Status | $7441 | 1B | Bitfield (see Status Condition above) |
| Ninten Max HP | $7443 | 2B | uint16 LE |
| Ninten Max PP | $7445 | 2B | uint16 LE |
| Ninten Offense | $7447 | 2B | uint16 LE |
| Ninten Defense | $7449 | 2B | uint16 LE |
| Ninten Level | $7450 | 1B | |
| Ninten Experience | $7451 | 3B | uint24 LE |
| Ninten Current HP | $7454 | 2B | uint16 LE |
| Ninten Current PP | $7456 | 2B | uint16 LE |
| Ninten Inventory | $7460 | 8B | 8 item ID slots |
| Ninten Weapon | $7468 | 1B | |

---

## Combat State (Internal RAM — Phase 3)

During battles, character and enemy state is copied to 32-byte combat structs in internal RAM.

| Entity | Address Range | Size |
|---|---|---|
| Ninten (combat) | $0600–$061F | 32B |
| Ally 1 (combat) | $0620–$063F | 32B |
| Ally 2 (combat) | $0640–$065F | 32B |
| Ally 3 (combat) | $0660–$067F | 32B |
| Enemy 1 (combat) | $0680–$069F | 32B |
| Enemy 2 (combat) | $06A0–$06BF | 32B |
| Enemy 3 (combat) | $06C0–$06DF | 32B |
| Enemy 4 (combat) | $06E0–$06FF | 32B |

### Combat Struct Fields

**NOT YET DOCUMENTED** — The internal layout of these 32-byte combat structs is not on DataCrystal. Must be reverse-engineered:

1. Enter a battle, note Ninten's HP from the SRAM struct
2. Read $0600–$061F in hex editor, find matching 2-byte value
3. Take damage, observe which bytes changed → that's the combat HP
4. Map remaining fields by experimentation

Likely layout (needs validation):

| Offset | Size | Probable Field | Approach to Confirm |
|---|---|---|---|
| TBD | 2B | Current HP | Take damage, search for decreased value in $0600–$061F |
| TBD | 2B | Current PP | Use PSI, search for decreased value |
| TBD | 1B | Status | Get poisoned, search for changed byte |
| TBD | 2B | Offense | Compare with known stat from SRAM struct |
| TBD | 2B | Defense | Compare with known stat from SRAM struct |

---

## SRAM Object Data (Internal)

| SRAM Offset | CPU Address | Size | Description |
|---|---|---|---|
| $0780–$079F | $6780–$679F | 32B | Ninten Object State (position/movement during gameplay) |
| $0800–$0D0F | $6800–$6D0F | 1296B | Misc NPC/Object state data |

---

## Event Flags (Phase 5)

Located within save slot data:

| Save Offset | CPU Address | Size | Description |
|---|---|---|---|
| +$21D | $761D | 1B | Teleport Locations unlocked (bitfield) |
| +$21E | $761E | 1B | Known Melodies (bitfield, up to 8 melodies) |

Story progress flags and key item flags are likely in the unknown region +$200–$288 within the save slot ($7600–$7688). Must be mapped empirically by triggering story events and watching for bit changes.

---

## Validation Checklist

Priority order for `scripts/validate_memory.py`:

### Must validate before Phase 1 implementation:
- [ ] $0015 — Current Area: Start game, check if value matches expected starting area
- [ ] $0018–$001B — Coordinates: Move around, derive decoding formula
- [ ] $0047 — Combat Active: Enter/exit battle, confirm 0=in-battle logic
- [ ] $7454 — Ninten Current HP: Compare displayed HP with memory value
- [ ] $7443 — Ninten Max HP: Compare at game start (known starting HP)
- [ ] $7450 — Ninten Level: Should be 1 at game start
- [ ] Verify whether $7400 block updates in real-time or only on save

### Should validate before Phase 3:
- [ ] $0048 — Enemy Group ID: Enter different battles, correlate IDs
- [ ] $0600–$061F — Combat struct: Map HP/PP/stats offsets within Ninten's combat block
- [ ] $0680–$069F — Enemy combat struct: Find enemy HP for battle tracking
- [ ] $7441 — Ninten Status: Get poisoned, check bit 1

### Nice to have (Phase 4–5):
- [ ] $7460 — Inventory: Buy/find items, watch for item IDs
- [ ] $7410 — Money: Buy something, confirm value decreases
- [ ] $761E — Melodies: Collect a melody, confirm bit change

---

## Sources

1. [DataCrystal: EarthBound Beginnings/RAM map](https://datacrystal.tcrf.net/wiki/EarthBound_Beginnings/RAM_map) — Primary source for all documented addresses
2. [DataCrystal: EarthBound Beginnings](https://datacrystal.tcrf.net/wiki/EarthBound_Beginnings) — ROM/game info and external data links
3. [TASVideos: EarthBound Beginnings](https://tasvideos.org/527G) — Speedrun resources, glitch documentation
4. [NESdev: CPU Memory Map](https://www.nesdev.org/wiki/CPU_memory_map) — NES hardware memory layout reference
5. [FCEUX: NES RAM Mapping](https://fceux.com/web/help/NESRAMMappingFindingValues.html) — How to find values with FCEUX tools

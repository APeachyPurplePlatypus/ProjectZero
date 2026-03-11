-- state_exporter.lua — Read NES RAM and write game state to shared/state.json
-- Runs inside FCEUX's per-frame loop. Writes every WRITE_INTERVAL frames.

local json = require("json")

local M = {}

-- Configuration (set by init)
local SHARED_DIR = ""
local STATE_FILE = "state.json"
local WRITE_INTERVAL = 4  -- Write every 4 frames (~15 Hz)

-- Memory addresses (from docs/MEMORY_MAP.md — DataCrystal source)
-- Internal RAM
local ADDR_DIRECTION    = 0x000C  -- 1B: player facing (0-7)
local ADDR_MAP_ID       = 0x0015  -- 1B: current area
local ADDR_COORD_BASE   = 0x0018  -- 4B: packed X/Y coordinates
local ADDR_MOVEMENT     = 0x00A0  -- 1B: $88=still, 0-7=moving
local ADDR_COMBAT_FLAG  = 0x0047  -- 1B: 0=in-battle (inverted!)
local ADDR_ENEMY_GROUP  = 0x0048  -- 1B: enemy group ID

-- SRAM header (Last Save block at $7400)
local ADDR_MONEY        = 0x7410  -- 2B: money (LE)
local ADDR_PARTY_SLOTS  = 0x7408  -- 4B: party member IDs

-- SRAM character data — via "Last Save" block ($7400)
-- Character struct offsets relative to character base:
--   +$01 = status, +$03 = max_hp (2B LE), +$05 = max_pp (2B LE)
--   +$10 = level, +$14 = current_hp (2B LE), +$16 = current_pp (2B LE)
--   +$20 = inventory (8 x 1B)
local ADDR_NINTEN_BASE  = 0x7440
local ADDR_ANA_BASE     = 0x7480
local ADDR_LLOYD_BASE   = 0x74C0
local ADDR_TEDDY_BASE   = 0x7500

-- Ninten's experience (3-byte LE at base+$11)
local ADDR_NINTEN_EXP   = 0x7451  -- 3B: experience (LE)

-- Event flags
local ADDR_MELODIES     = 0x761E  -- 1B: known melodies bitfield (Phase 5)

function M.init(shared_dir)
    SHARED_DIR = shared_dir
end

-- Decode packed coordinates at $0018-$001B
-- Format: two 16-bit LE values, shift right by 4 for tile position
-- TODO: validate shift amount empirically with FCEUX RAM Search
local function read_coordinates()
    local b0 = memory.readbyte(ADDR_COORD_BASE)
    local b1 = memory.readbyte(ADDR_COORD_BASE + 1)
    local b2 = memory.readbyte(ADDR_COORD_BASE + 2)
    local b3 = memory.readbyte(ADDR_COORD_BASE + 3)
    local raw_x = b0 + (b1 * 256)
    local raw_y = b2 + (b3 * 256)
    return math.floor(raw_x / 16), math.floor(raw_y / 16)
end

-- Read 3-byte little-endian unsigned integer (for experience)
local function read_uint24(addr)
    local lo  = memory.readbyte(addr)
    local mid = memory.readbyte(addr + 1)
    local hi  = memory.readbyte(addr + 2)
    return lo + (mid * 256) + (hi * 65536)
end

-- Read character stat block from base address.
-- Returns a table with hp, max_hp, pp, max_pp, level, status fields.
local function read_char_stats(base)
    return {
        status  = memory.readbyte(base + 0x01),
        max_hp  = memory.readword(base + 0x03),
        max_pp  = memory.readword(base + 0x05),
        level   = memory.readbyte(base + 0x10),
        hp      = memory.readword(base + 0x14),
        pp      = memory.readword(base + 0x16),
    }
end

-- Read 8 inventory slots starting at base+$20.
-- Slots are 1-byte item IDs; 0 = empty.
local function read_inventory(base)
    local slots = {}
    for i = 0, 7 do
        slots[i] = memory.readbyte(base + 0x20 + i)
    end
    return slots
end

-- Read 8 learned PSI ability IDs starting at base+$30.
-- Slots are 1-byte PSI IDs; 0 = unlearned.
local function read_psi(base)
    local slots = {}
    for i = 0, 7 do
        slots[i] = memory.readbyte(base + 0x30 + i)
    end
    return slots
end

-- Force an export on the next call (used for screenshot sync)
M.force_next = false

function M.export_state()
    local frame = emu.framecount()

    -- Throttle: only write every WRITE_INTERVAL frames unless forced
    if not M.force_next and (frame % WRITE_INTERVAL ~= 0) then
        return
    end
    M.force_next = false

    local px, py = read_coordinates()
    local combat_raw = memory.readbyte(ADDR_COMBAT_FLAG)

    -- Ninten stats
    local ninten = read_char_stats(ADDR_NINTEN_BASE)

    -- Party allies
    local ana   = read_char_stats(ADDR_ANA_BASE)
    local lloyd = read_char_stats(ADDR_LLOYD_BASE)
    local teddy = read_char_stats(ADDR_TEDDY_BASE)

    -- Ninten inventory (slots 0-7 = prefix inv_0..inv_7)
    local ninten_inv = read_inventory(ADDR_NINTEN_BASE)
    -- Ally inventories (slots 8-31, prefixed inv_8..inv_31)
    local ana_inv   = read_inventory(ADDR_ANA_BASE)
    local lloyd_inv = read_inventory(ADDR_LLOYD_BASE)
    local teddy_inv = read_inventory(ADDR_TEDDY_BASE)

    -- PSI abilities (8 slots per character; only Ninten and Ana have PSI)
    local ninten_psi = read_psi(ADDR_NINTEN_BASE)
    local ana_psi    = read_psi(ADDR_ANA_BASE)

    local state = {
        frame           = frame,
        map_id          = memory.readbyte(ADDR_MAP_ID),
        player_x        = px,
        player_y        = py,
        player_direction = memory.readbyte(ADDR_DIRECTION),
        movement_state  = memory.readbyte(ADDR_MOVEMENT),

        -- Ninten
        ninten_hp       = ninten.hp,
        ninten_max_hp   = ninten.max_hp,
        ninten_pp       = ninten.pp,
        ninten_max_pp   = ninten.max_pp,
        ninten_level    = ninten.level,
        ninten_exp      = read_uint24(ADDR_NINTEN_EXP),
        ninten_status   = ninten.status,

        -- Ana
        ana_hp          = ana.hp,
        ana_max_hp      = ana.max_hp,
        ana_pp          = ana.pp,
        ana_max_pp      = ana.max_pp,
        ana_level       = ana.level,
        ana_status      = ana.status,

        -- Lloyd
        lloyd_hp        = lloyd.hp,
        lloyd_max_hp    = lloyd.max_hp,
        lloyd_pp        = lloyd.pp,
        lloyd_max_pp    = lloyd.max_pp,
        lloyd_level     = lloyd.level,
        lloyd_status    = lloyd.status,

        -- Teddy
        teddy_hp        = teddy.hp,
        teddy_max_hp    = teddy.max_hp,
        teddy_pp        = teddy.pp,
        teddy_max_pp    = teddy.max_pp,
        teddy_level     = teddy.level,
        teddy_status    = teddy.status,

        -- Inventory (flat: Ninten inv_0..7, Ana inv_8..15, Lloyd inv_16..23, Teddy inv_24..31)
        inv_0  = ninten_inv[0], inv_1  = ninten_inv[1],
        inv_2  = ninten_inv[2], inv_3  = ninten_inv[3],
        inv_4  = ninten_inv[4], inv_5  = ninten_inv[5],
        inv_6  = ninten_inv[6], inv_7  = ninten_inv[7],
        inv_8  = ana_inv[0],    inv_9  = ana_inv[1],
        inv_10 = ana_inv[2],    inv_11 = ana_inv[3],
        inv_12 = ana_inv[4],    inv_13 = ana_inv[5],
        inv_14 = ana_inv[6],    inv_15 = ana_inv[7],
        inv_16 = lloyd_inv[0],  inv_17 = lloyd_inv[1],
        inv_18 = lloyd_inv[2],  inv_19 = lloyd_inv[3],
        inv_20 = lloyd_inv[4],  inv_21 = lloyd_inv[5],
        inv_22 = lloyd_inv[6],  inv_23 = lloyd_inv[7],
        inv_24 = teddy_inv[0],  inv_25 = teddy_inv[1],
        inv_26 = teddy_inv[2],  inv_27 = teddy_inv[3],
        inv_28 = teddy_inv[4],  inv_29 = teddy_inv[5],
        inv_30 = teddy_inv[6],  inv_31 = teddy_inv[7],

        -- PSI abilities (Ninten psi_0..7, Ana psi_8..15)
        psi_0  = ninten_psi[0], psi_1  = ninten_psi[1],
        psi_2  = ninten_psi[2], psi_3  = ninten_psi[3],
        psi_4  = ninten_psi[4], psi_5  = ninten_psi[5],
        psi_6  = ninten_psi[6], psi_7  = ninten_psi[7],
        psi_8  = ana_psi[0],    psi_9  = ana_psi[1],
        psi_10 = ana_psi[2],    psi_11 = ana_psi[3],
        psi_12 = ana_psi[4],    psi_13 = ana_psi[5],
        psi_14 = ana_psi[6],    psi_15 = ana_psi[7],

        -- Party composition (ally IDs; 0 = empty slot)
        party_0 = memory.readbyte(ADDR_PARTY_SLOTS),
        party_1 = memory.readbyte(ADDR_PARTY_SLOTS + 1),
        party_2 = memory.readbyte(ADDR_PARTY_SLOTS + 2),
        party_3 = memory.readbyte(ADDR_PARTY_SLOTS + 3),

        -- Economy / progress
        money       = memory.readword(ADDR_MONEY),
        melodies    = memory.readbyte(ADDR_MELODIES),

        -- Combat
        combat_active   = (combat_raw == 0) and 1 or 0,
        enemy_group_id  = memory.readbyte(ADDR_ENEMY_GROUP),
        menu_state      = 0,  -- TBD: address not yet found
        dialog_active   = 0,  -- TBD: address not yet found
    }

    -- Atomic write: write to temp file, remove target, rename
    local tmp_path   = SHARED_DIR .. "/state.json.tmp"
    local final_path = SHARED_DIR .. "/" .. STATE_FILE

    local f, err = io.open(tmp_path, "w")
    if f then
        f:write(json.encode(state))
        f:close()
        os.remove(final_path)
        os.rename(tmp_path, final_path)
    end
end

return M

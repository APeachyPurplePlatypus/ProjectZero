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

-- SRAM character data — Ninten via "Last Save" block
-- CPU address = SRAM offset + $6000; save slot at $1400; Ninten struct at +$40
local ADDR_NINTEN_STATUS  = 0x7441  -- 1B: status bitfield
local ADDR_NINTEN_MAX_HP  = 0x7443  -- 2B: max HP (LE)
local ADDR_NINTEN_MAX_PP  = 0x7445  -- 2B: max PP (LE)
local ADDR_NINTEN_LEVEL   = 0x7450  -- 1B: level
local ADDR_NINTEN_EXP     = 0x7451  -- 3B: experience (LE)
local ADDR_NINTEN_HP      = 0x7454  -- 2B: current HP (LE)
local ADDR_NINTEN_PP      = 0x7456  -- 2B: current PP (LE)

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

    local state = {
        frame           = frame,
        map_id          = memory.readbyte(ADDR_MAP_ID),
        player_x        = px,
        player_y        = py,
        player_direction = memory.readbyte(ADDR_DIRECTION),
        movement_state  = memory.readbyte(ADDR_MOVEMENT),
        ninten_hp       = memory.readword(ADDR_NINTEN_HP),
        ninten_max_hp   = memory.readword(ADDR_NINTEN_MAX_HP),
        ninten_pp       = memory.readword(ADDR_NINTEN_PP),
        ninten_max_pp   = memory.readword(ADDR_NINTEN_MAX_PP),
        ninten_level    = memory.readbyte(ADDR_NINTEN_LEVEL),
        ninten_exp      = read_uint24(ADDR_NINTEN_EXP),
        ninten_status   = memory.readbyte(ADDR_NINTEN_STATUS),
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

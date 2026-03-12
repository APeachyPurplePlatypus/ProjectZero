-- main.lua — EarthBound Zero AI Player: FCEUX Lua orchestrator
-- Loads modules and runs the per-frame IPC loop.
-- Launch: fceux -lua lua/main.lua <rom_path>

-- Set up module path so require() finds sibling .lua files
local script_dir = debug.getinfo(1, "S").source:match("@?(.*[\\/])")
if script_dir then
    package.path = script_dir .. "?.lua;" .. package.path
end

-- Shared directory: one level up from lua/ into shared/
local SHARED_DIR = script_dir and (script_dir .. "../shared") or "../shared"

-- Normalize path separators for Windows
SHARED_DIR = SHARED_DIR:gsub("\\", "/")

-- Load modules
local json           = require("json")
local state_exporter = require("state_exporter")
local input_reader   = require("input_reader")
local frame_capture  = require("frame_capture")

-- Initialize modules
state_exporter.init(SHARED_DIR)
input_reader.init(SHARED_DIR)
frame_capture.init(SHARED_DIR)

-- Ensure shared directory exists (create marker file to verify path works)
local function write_ready_marker()
    local f = io.open(SHARED_DIR .. "/lua_ready.json", "w")
    if f then
        f:write(json.encode({
            status  = "ready",
            frame   = emu.framecount(),
            version = "0.1.0",
        }))
        f:close()
    else
        emu.message("ERROR: Cannot write to " .. SHARED_DIR)
    end
end

-- Verify emulation is active
if not emu.emulating() then
    error("No ROM loaded. Launch FCEUX with: fceux -lua lua/main.lua <rom_path>")
end

write_ready_marker()
emu.message("EB0 AI Bridge: Lua initialized")
print("[EB0] Lua bridge initialized. Shared dir: " .. SHARED_DIR)
print("[EB0] Listening for commands...")

-- Main per-frame loop
while true do
    local frame = emu.framecount()

    -- 1. Export game state (throttled to every 4 frames internally)
    state_exporter.export_state()

    -- 2. Process pending input commands
    input_reader.process_input()

    -- 3. Relay screenshot request from input_reader to frame_capture
    if input_reader.screenshot_pending then
        frame_capture.capture_requested = true
        input_reader.screenshot_pending = false
        -- Force a state export on screenshot frame for synchronization
        state_exporter.force_next = true
        print("[EB0] Screenshot captured at frame " .. frame)
    end

    -- 4. Handle screenshot capture
    frame_capture.process()

    -- 5. Heartbeat log every 300 frames (~5 seconds)
    if frame % 300 == 0 then
        print(string.format("[EB0] frame=%d map=%d hp=%d",
            frame,
            memory.readbyte(0x0015),
            memory.readword(0x7454)))
    end

    -- Advance one emulated frame
    emu.frameadvance()
end

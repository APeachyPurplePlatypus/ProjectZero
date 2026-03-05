-- input_reader.lua — Read input commands from shared/input.json and apply via joypad
-- Uses three-file IPC: input.json (Python writes) → input_done.json (Lua writes on completion)

local json = require("json")

local M = {}

-- Configuration (set by init)
local SHARED_DIR = ""
local INPUT_FILE = "input.json"
local DONE_FILE  = "input_done.json"

-- Internal state
local active_command = nil
local remaining_frames = 0
local current_frame_id = 0

-- Flag for main.lua to relay to frame_capture
M.screenshot_pending = false

-- Key name normalization: input.json uses mixed case, FCEUX needs specific casing
local KEY_MAP = {
    A       = "A",
    B       = "B",
    Start   = "start",
    Select  = "select",
    start   = "start",
    select  = "select",
    up      = "up",
    down    = "down",
    left    = "left",
    right   = "right",
    Up      = "up",
    Down    = "down",
    Left    = "left",
    Right   = "right",
}

function M.init(shared_dir)
    SHARED_DIR = shared_dir
end

local function read_input_file()
    local path = SHARED_DIR .. "/" .. INPUT_FILE
    local f = io.open(path, "r")
    if not f then return nil end

    local content = f:read("*all")
    f:close()

    -- Delete immediately to acknowledge receipt
    os.remove(path)

    if not content or content == "" then return nil end

    local ok, cmd = pcall(json.decode, content)
    if not ok or not cmd then return nil end
    return cmd
end

local function write_done(frame_id)
    local path = SHARED_DIR .. "/" .. DONE_FILE
    local f = io.open(path, "w")
    if f then
        f:write(json.encode({status = "done", frame_id = frame_id}))
        f:close()
    end
end

local function build_joypad_table(cmd)
    local joy = {}
    if cmd.command == "button" and cmd.button then
        local key = KEY_MAP[cmd.button]
        if key then joy[key] = true end
    elseif cmd.command == "move" and cmd.direction then
        local key = KEY_MAP[cmd.direction]
        if key then joy[key] = true end
    end
    -- "wait" command: empty joypad table (no buttons pressed)
    return joy
end

function M.process_input()
    -- If no active command, check for a new one
    if active_command == nil then
        local cmd = read_input_file()
        if cmd then
            -- Handle instant savestate commands (no multi-frame hold)
            if cmd.command == "savestate_save" then
                local slot = cmd.slot or 1
                savestate.save(slot)
                write_done(cmd.frame_id or 0)
                return
            end
            if cmd.command == "savestate_load" then
                local slot = cmd.slot or 1
                savestate.load(slot)
                write_done(cmd.frame_id or 0)
                return
            end

            active_command = cmd
            remaining_frames = cmd.duration_frames or 2
            current_frame_id = cmd.frame_id or 0

            -- Check for screenshot request
            if cmd.capture_screenshot then
                M.screenshot_pending = true
            end
        end
    end

    -- Apply active command's joypad input
    if active_command then
        local joy = build_joypad_table(active_command)
        -- Only call joypad.set if there are buttons to press
        if next(joy) then
            joypad.set(1, joy)
        end

        remaining_frames = remaining_frames - 1
        if remaining_frames <= 0 then
            write_done(current_frame_id)
            active_command = nil
        end
    end
end

return M

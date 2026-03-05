-- frame_capture.lua — On-demand screenshot capture to shared/screenshot.png

local M = {}

local SHARED_DIR = ""
local SCREENSHOT_FILE = "screenshot.png"

-- Set by main.lua when input_reader signals a screenshot request
M.capture_requested = false

function M.init(shared_dir)
    SHARED_DIR = shared_dir
end

function M.process()
    if not M.capture_requested then return end

    local path = SHARED_DIR .. "/" .. SCREENSHOT_FILE
    -- gui.savescreenshotas() saves the current emulated frame as PNG
    gui.savescreenshotas(path)
    M.capture_requested = false
end

return M

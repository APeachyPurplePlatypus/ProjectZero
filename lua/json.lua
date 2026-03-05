-- json.lua — Minimal JSON encoder/decoder for FCEUX Lua 5.1
-- Handles flat objects with string/number/boolean/null values.
-- No nested objects or arrays (not needed for IPC protocol).

local json = {}

-- Sentinel for JSON null (Lua tables can't store nil)
json.null = setmetatable({}, {__tostring = function() return "null" end})

-------------------------------------------------------------------------------
-- Encoder
-------------------------------------------------------------------------------

local escape_map = {
    ['"']  = '\\"',
    ['\\'] = '\\\\',
    ['\n'] = '\\n',
    ['\r'] = '\\r',
    ['\t'] = '\\t',
}

local function escape_string(s)
    return s:gsub('["\\\n\r\t]', escape_map)
end

local function encode_value(v)
    local t = type(v)
    if t == "number" then
        if v ~= v then return "null" end          -- NaN
        if v == math.huge then return "1e999" end
        if v == -math.huge then return "-1e999" end
        -- Use integer format when possible
        if v == math.floor(v) and math.abs(v) < 2^53 then
            return string.format("%.0f", v)
        end
        return tostring(v)
    elseif t == "string" then
        return '"' .. escape_string(v) .. '"'
    elseif t == "boolean" then
        return v and "true" or "false"
    elseif t == "table" and v == json.null then
        return "null"
    elseif v == nil then
        return "null"
    end
    return '"' .. tostring(v) .. '"'
end

function json.encode(tbl)
    if type(tbl) ~= "table" then
        return encode_value(tbl)
    end
    local parts = {}
    for k, v in pairs(tbl) do
        if type(k) == "string" then
            parts[#parts + 1] = '"' .. escape_string(k) .. '":' .. encode_value(v)
        end
    end
    return "{" .. table.concat(parts, ",") .. "}"
end

-------------------------------------------------------------------------------
-- Decoder
-------------------------------------------------------------------------------

local function skip_whitespace(str, pos)
    return str:match("^%s*()", pos)
end

local function decode_string(str, pos)
    -- pos should point to the opening quote
    if str:sub(pos, pos) ~= '"' then
        return nil, "expected '\"' at position " .. pos
    end
    pos = pos + 1
    local result = {}
    while pos <= #str do
        local c = str:sub(pos, pos)
        if c == '"' then
            return table.concat(result), pos + 1
        elseif c == '\\' then
            pos = pos + 1
            local esc = str:sub(pos, pos)
            if esc == '"' then result[#result + 1] = '"'
            elseif esc == '\\' then result[#result + 1] = '\\'
            elseif esc == 'n' then result[#result + 1] = '\n'
            elseif esc == 'r' then result[#result + 1] = '\r'
            elseif esc == 't' then result[#result + 1] = '\t'
            elseif esc == '/' then result[#result + 1] = '/'
            else result[#result + 1] = esc end
            pos = pos + 1
        else
            result[#result + 1] = c
            pos = pos + 1
        end
    end
    return nil, "unterminated string"
end

local function decode_number(str, pos)
    local num_str = str:match("^-?%d+%.?%d*[eE]?[+-]?%d*", pos)
    if not num_str then
        return nil, "invalid number at position " .. pos
    end
    local val = tonumber(num_str)
    if not val then
        return nil, "invalid number: " .. num_str
    end
    return val, pos + #num_str
end

local function decode_value(str, pos)
    pos = skip_whitespace(str, pos)
    if pos > #str then
        return nil, "unexpected end of input"
    end

    local c = str:sub(pos, pos)

    -- String
    if c == '"' then
        return decode_string(str, pos)
    end

    -- Number
    if c == '-' or (c >= '0' and c <= '9') then
        return decode_number(str, pos)
    end

    -- Boolean / null
    if str:sub(pos, pos + 3) == "true" then
        return true, pos + 4
    end
    if str:sub(pos, pos + 4) == "false" then
        return false, pos + 5
    end
    if str:sub(pos, pos + 3) == "null" then
        return json.null, pos + 4
    end

    -- Object
    if c == '{' then
        local obj = {}
        pos = skip_whitespace(str, pos + 1)
        if str:sub(pos, pos) == '}' then
            return obj, pos + 1
        end
        while true do
            pos = skip_whitespace(str, pos)
            local key, val
            key, pos = decode_string(str, pos)
            if not key then return nil, "expected string key" end
            pos = skip_whitespace(str, pos)
            if str:sub(pos, pos) ~= ':' then
                return nil, "expected ':' at position " .. pos
            end
            pos = pos + 1
            val, pos = decode_value(str, pos)
            if val == json.null then val = json.null end
            obj[key] = val
            pos = skip_whitespace(str, pos)
            local sep = str:sub(pos, pos)
            if sep == '}' then
                return obj, pos + 1
            elseif sep == ',' then
                pos = pos + 1
            else
                return nil, "expected ',' or '}' at position " .. pos
            end
        end
    end

    return nil, "unexpected character '" .. c .. "' at position " .. pos
end

function json.decode(str)
    if type(str) ~= "string" or str == "" then
        return nil, "empty input"
    end
    local val, pos = decode_value(str, 1)
    return val, pos
end

return json

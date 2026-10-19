-- macOS already swaps Command/Option and maps Caps Lock to Control.
-- Physical Command (logical Option) owns desktop navigation.
-- Physical Option (logical Command) keeps normal application shortcuts.
-- See docs/keyboard-layout.md for the cross-platform contract.

local event = hs.eventtap.event
local types = event.types
local tab, grave, space = 48, 50, 49 -- virtual key codes, independent of input language
local switching = false
local translatedKeys = {}

-- Replaces the previous skhd config: prevent accidental application hiding.
hideAppGuard = hs.hotkey.bind({ "cmd" }, "h", function() end)

local function commandFlags(flags)
    -- Preserve Caps Lock and other raw flags while replacing Option with Command.
    local raw = flags & ~0x00080000 -- NX_ALTERNATEMASK
    -- Strip device-specific left/right Option bits as well.
    return (raw & ~0x60) | 0x00100000 -- NX_COMMANDMASK
end

-- Keep a global reference so Lua cannot collect the active event tap.
desktopSwitching = hs.eventtap.new({
    types.keyDown, types.keyUp, types.flagsChanged,
    types.leftMouseDown, types.leftMouseUp, types.rightMouseDown,
    types.rightMouseUp, types.mouseMoved, types.scrollWheel,
}, function(e)
    local kind, code = e:getType(), e:getKeyCode()
    local flags = e:getFlags()

    if switching then
        if not flags.alt then
            -- The real desktop modifier was released. Let macOS commit the selection.
            switching = false
        else
            -- This includes Shift changes and mouse movement, so Command stays
            -- logically held between Tab presses. Escape remains native cancel.
            e:rawFlags(commandFlags(e:rawFlags()))
            if kind == types.keyDown then translatedKeys[code] = true end
            if kind == types.keyUp then translatedKeys[code] = nil end
            return false
        end
    end

    -- Match key-up to its translated key-down even if Option was released first.
    if kind == types.keyUp and translatedKeys[code] then
        translatedKeys[code] = nil
        if flags.alt then e:rawFlags(commandFlags(e:rawFlags())) end
        return false
    end

    if kind == types.keyDown and flags.alt and not (flags.cmd or flags.ctrl or flags.fn)
        and (code == tab or code == grave or (code == space and not flags.shift)) then
        translatedKeys[code] = true
        switching = code == tab
        e:rawFlags(commandFlags(e:rawFlags()))
    end
    return false
end):start()

-- Local CLI is useful for checking that the configuration loaded successfully.
require("hs.ipc")

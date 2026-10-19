-- Run inside Hammerspoon: hs -c 'dofile(".../dotfiles/hammerspoon/test.lua")'
-- All input is mocked: this does not send keyboard events or register hotkeys.
local source = debug.getinfo(1, "S").source:sub(2):match("(.*/)") .. "init.lua"
local callback
local types = {
    keyDown = 1, keyUp = 2, flagsChanged = 3, leftMouseDown = 4,
    leftMouseUp = 5, rightMouseDown = 6, rightMouseUp = 7,
    mouseMoved = 8, scrollWheel = 9,
}
local fakeHS = {
    hotkey = { bind = function() return {} end },
    eventtap = {
        event = { types = types },
        new = function(_, fn)
            callback = fn
            return { start = function(self) return self end }
        end,
    },
}
local env = setmetatable({ hs = fakeHS, require = function() return {} end }, { __index = _G })
assert(loadfile(source, "t", env))()

local alt, cmd, shift, ctrl, caps = 0x80000, 0x100000, 0x20000, 0x40000, 0x10000
local function input(kind, code, raw)
    local e = { raw = raw }
    function e:getType() return kind end
    function e:getKeyCode() return code end
    function e:getFlags()
        return { alt = self.raw & alt ~= 0, cmd = self.raw & cmd ~= 0,
            shift = self.raw & shift ~= 0, ctrl = self.raw & ctrl ~= 0 }
    end
    function e:rawFlags(value)
        if value then self.raw = value; return self end
        return self.raw
    end
    assert(callback(e) == false, "events must continue to macOS")
    return e.raw
end

-- Ordinary navigation and modified application/desktop chords stay untouched.
assert(input(types.keyDown, 4, alt) == alt) -- H
assert(input(types.keyDown, 48, alt | ctrl) == alt | ctrl)
assert(input(types.keyDown, 48, alt | cmd) == alt | cmd)

-- Tab release must NOT end switching; Shift and mouse events keep Command held.
assert(input(types.keyDown, 48, alt) == cmd)
assert(input(types.keyUp, 48, alt) == cmd)
assert(input(types.flagsChanged, 56, alt | shift) == cmd | shift)
assert(input(types.mouseMoved, 0, alt | shift) == cmd | shift)
assert(input(types.keyDown, 48, alt | shift) == cmd | shift)
assert(input(types.keyUp, 48, alt | shift) == cmd | shift)
assert(input(types.flagsChanged, 58, shift) == shift)
assert(input(types.keyDown, 4, alt) == alt)

-- Releasing the desktop modifier before Tab must not leave Command stuck.
assert(input(types.keyDown, 48, alt) == cmd)
assert(input(types.flagsChanged, 58, 0) == 0)
assert(input(types.keyUp, 48, 0) == 0)

-- Backtick supports reversal and Caps Lock without latching desktop navigation.
assert(input(types.keyDown, 50, alt | shift | caps | 0x20) == cmd | shift | caps)
assert(input(types.keyUp, 50, alt | shift | caps) == cmd | shift | caps)
assert(input(types.keyDown, 4, alt) == alt)

-- Spotlight is a one-shot shortcut and must not latch Command for navigation.
assert(input(types.keyDown, 49, alt) == cmd)
assert(input(types.keyUp, 49, alt) == cmd)
assert(input(types.keyDown, 4, alt) == alt)
assert(input(types.keyDown, 49, alt | ctrl) == alt | ctrl)
assert(input(types.keyDown, 49, alt | shift) == alt | shift)

-- Escape is passed through to the native switcher, then release ends the hold.
assert(input(types.keyDown, 48, alt) == cmd)
assert(input(types.keyUp, 48, alt) == cmd)
assert(input(types.keyDown, 53, alt) == cmd)
assert(input(types.keyUp, 53, alt) == cmd)
assert(input(types.flagsChanged, 58, 0) == 0)
print("PASS: desktop switching event sequences")

-- Run with Hammerspoon's hs CLI; all notification and app APIs are mocked.
local path = debug.getinfo(1, "S").source:sub(2):match("(.*/)") .. "notify.lua"
local stored, callback, sends, opens = nil, nil, 0, 0
local payload = { id = "first", task = "Measure throughput", question = "What throughput did you measure?", python = "/usr/bin/python3",
    script = "/a path/buddy.py", data = "/private/data" }
local fake = {
    settings = { get = function() return stored end, set = function(_, value) stored = value end },
    json = { decode = function() return payload end },
    application = { applicationsForBundleID = function() return {} end },
    alert = { show = function(message) error(message) end },
    task = { new = function(command, _, args)
        assert(command == "/usr/bin/open")
        assert(args[8] == payload.script and args[9] == "--data-dir" and args[10] == payload.data)
        opens = opens + 1
        return { start = function() return true end }
    end },
    notify = {
        register = function(_, fn) callback = fn end,
        deliveredNotifications = function() return {} end,
        new = function(tag, attributes)
            assert(tag == "buddy-check-in" and attributes.informativeText == payload.question)
            return { send = function() sends = sends + 1 end }
        end,
    },
}
local env = setmetatable({ hs = fake, io = { open = function()
    return { read = function() return "{}" end, close = function() end }
end } }, { __index = _G })
local bridge = assert(loadfile(path, "t", env))()
bridge.send("/private/payload.json")
bridge.send("/private/payload.json")
assert(sends == 1, "retry must not duplicate a notification")
callback()
assert(opens == 1, "click should launch Buddy")
local focused = false
fake.application.applicationsForBundleID = function()
    return {{ allWindows = function() return {{ title = function() return "Buddy" end,
        focus = function() focused = true end }} end }}
end
callback()
assert(focused and opens == 1, "existing Buddy window should be focused")
-- Reloading the Lua module restores callbacks for existing notifications.
assert(loadfile(path, "t", env))()
callback()
assert(focused)
print("PASS: Buddy notification deduplication, launch, focus, and callback reload")

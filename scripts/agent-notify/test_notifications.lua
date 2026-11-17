-- Run with hs -c 'dofile(".../test_notifications.lua")'. All effects are mocked.
local source = debug.getinfo(1, "S").source:sub(2):match("(.*/)") .. "notifications.lua"
local saved, payload, now = nil, nil, 100
local callbacks, delivered, bindings, windows = {}, {}, {}, {}
local focused, front, alerts, opened = nil, nil, {}, {}
local function window(id, title, pid, bundle)
    return {
        id = function() return id end,
        title = function() return title end,
        application = function() return { pid = function() return pid end,
            bundleID = function() return bundle end } end,
        unminimize = function() end,
        focus = function(self) focused = id; return self end,
    }
end
local fake = {
    settings = { get = function() return saved end, set = function(_, v) saved = v end },
    timer = { secondsSinceEpoch = function() return now end },
    json = { decode = function() return payload end },
    window = {
        allWindows = function() return windows end,
        frontmostWindow = function() return front end,
        get = function(id)
            for _, w in ipairs(windows) do if w:id() == id then return w end end
        end,
    },
    alert = { show = function(message) alerts[#alerts + 1] = message end },
    task = { new = function(command, callback, args)
        assert(command == "/usr/bin/open")
        return { start = function()
            opened[#opened + 1] = args
            callback(0)
            return true
        end }
    end },
    hotkey = { bind = function(mods, key, fn)
        bindings[table.concat(mods, "+") .. "+" .. key] = fn
        return {}
    end },
    notify = {
        register = function(tag, fn) callbacks[tag] = fn end,
        deliveredNotifications = function()
            local result = {}
            for _, n in pairs(delivered) do result[#result + 1] = n end
            return result
        end,
        new = function(tag, attributes)
            assert(attributes.autoWithdraw == false and attributes.withdrawAfter == 0)
            local object = {
                getFunctionTag = function() return tag end,
                withdraw = function() delivered[tag] = nil end,
                send = function(self) delivered[tag] = self end,
            }
            return object
        end,
    },
}
local env = setmetatable({ hs = fake, io = { open = function()
    return { read = function() return "{}" end, close = function() end }
end } }, { __index = _G })
local function loadBridge() return assert(loadfile(source, "t", env))() end
local bridge = loadBridge()
local a, b, c = string.rep("a", 32), string.rep("b", 32), string.rep("c", 32)
local ghostty = { bundle = "com.mitchellh.ghostty", pid = 10 }
local function send(id, options)
    payload = options or {}
    payload.id, payload.title = id, "Agent · example"
    bridge.send("fixture")
    now = now + 3
end
delivered.buddy = { getFunctionTag = function() return "buddy-check-in" end,
    withdraw = function() error("must not dismiss Buddy") end }
bridge.bind()
assert(bindings["alt+n"] and bindings["alt+shift+n"])
send(a)
send(b)
bindings["alt+n"]()
assert(not saved.pending[b] and saved.pending[a] and delivered.buddy)
assert(not focused, "dismiss must not focus a window")

-- Repeated completions replace the session's earlier notification.
send(a)
assert(#saved.order == 1)
send(b)
delivered["agent-notify:" .. b] = nil -- dismissed manually
bindings["alt+n"]()
assert(#saved.order == 0, "skip notifications already dismissed with the mouse")

-- Capture at prompt time, then focus the captured window, not the foreground one.
windows = { window(1, "Claude", 10, ghostty.bundle), window(2, "Other", 10, ghostty.bundle) }
front = windows[1]
payload = { id = a, terminal = ghostty }
bridge.capture("fixture")
front = windows[2]
send(a, { agent = "claude", terminal = ghostty })
bindings["alt+shift+n"]()
assert(focused == 1 and not saved.pending[a])

-- A closed window must not redirect to another terminal or consume the item.
send(a, { agent = "claude", terminal = ghostty })
windows = { windows[2] }
bridge.openLatest()
assert(saved.pending[a] and #alerts == 1)
bridge.dismissLatest()

-- Codex CLI title resolves the correct window without a prompt hook.
windows = { window(3, "⠙ Respond to greeting | user", 10, ghostty.bundle), windows[1] }
send(b, { agent = "codex", terminal = ghostty, sessionTitle = "Respond to greeting", threadID = "abc-123" })
bridge.openLatest()
assert(focused == 3 and not saved.pending[b] and #opened == 0)

-- Desktop Codex opens a precise chat; clicks survive module reloads.
send(c, { agent = "codex", threadID = "abc-123" })
bridge = loadBridge()
callbacks["agent-notify:" .. c]()
assert(opened[1][3] == "codex://threads/abc-123" and not saved.pending[c])

-- Duplicate titles must not focus a random window.
windows[2] = window(4, "Respond to greeting | user", 10, ghostty.bundle)
send(b, { agent = "codex", terminal = ghostty, sessionTitle = "Respond to greeting" })
bridge.openLatest()
assert(saved.pending[b] and #alerts == 2)
print("PASS: shortcuts, queue order, deduplication, manual dismissal, captured focus, closed/ambiguous windows, deep links, reload, unrelated notifications")

-- Own only agent notifications; leave Buddy and other applications untouched.
local M = {}
local prefix, settingsKey = "agent-notify:", "agentNotifications.v1"
local state = hs.settings.get(settingsKey) or { order = {}, pending = {}, origins = {} }
local shortcuts = {}
local function save() hs.settings.set(settingsKey, state) end
local function tag(id) return prefix .. id end
local function read(path)
    local file = assert(io.open(path, "r"))
    local value = hs.json.decode(file:read("*a"))
    file:close()
    assert(type(value) == "table" and type(value.id) == "string")
    assert(value.id:match("^[a-f0-9]+$") and #value.id == 32)
    return value
end

local function remove(id)
    for _, notification in ipairs(hs.notify.deliveredNotifications()) do
        if notification:getFunctionTag() == tag(id) then notification:withdraw() end
    end
    state.pending[id] = nil
    for i = #state.order, 1, -1 do
        if state.order[i] == id then table.remove(state.order, i) end
    end
end

local function windowTarget(window, terminal)
    if not window or not terminal then return nil end
    local app = window:application()
    if app:bundleID() == terminal.bundle and app:pid() == terminal.pid then
        return { kind = "window", id = window:id(), bundle = terminal.bundle, pid = terminal.pid }
    end
end

local function findTarget(payload)
    local origin = state.origins[payload.id]
    if origin and payload.terminal and origin.pid == payload.terminal.pid then
        return origin
    end
    -- CLI Codex puts its chat title in the terminal title. Match only one window;
    -- never choose an arbitrary terminal or the foreground app at completion.
    if payload.terminal and payload.sessionTitle and payload.sessionTitle ~= "" then
        local found
        for _, window in ipairs(hs.window.allWindows()) do
            local target = windowTarget(window, payload.terminal)
            local title = window:title()
            if target and (title == payload.sessionTitle
                or title:find(payload.sessionTitle .. " | ", 1, true)) then
                if found then return nil end
                found = target
            end
        end
        if found then return found end
    end
    -- Official local-chat link also works when a CLI window cannot be identified.
    if payload.agent == "codex" and type(payload.threadID) == "string"
        and payload.threadID:match("^[a-fA-F0-9%-]+$") then
        return { kind = "codex", threadID = payload.threadID }
    end
end

function M.capture(path)
    local payload = read(path)
    local target = windowTarget(hs.window.frontmostWindow(), payload.terminal)
    if target then
        target.capturedAt = hs.timer.secondsSinceEpoch()
        state.origins[payload.id] = target
        -- Keep prompt captures bounded without disturbing pending notifications.
        local entries = {}
        for id, value in pairs(state.origins) do
            entries[#entries + 1] = { id = id, at = value.capturedAt or 0 }
        end
        table.sort(entries, function(a, b) return a.at > b.at end)
        for i = 201, #entries do state.origins[entries[i].id] = nil end
        save()
    end
end

function M.open(id)
    local payload = state.pending[id]
    if not payload then return end
    local target = payload.target or findTarget(payload)
    if target and target.kind == "window" then
        local window = hs.window.get(target.id)
        if window and window:application():pid() == target.pid
            and window:application():bundleID() == target.bundle then
            window:unminimize()
            if window:focus() then remove(id); save(); return end
        end
    elseif target and target.kind == "codex" then
        local task = hs.task.new("/usr/bin/open", function(code)
            if code == 0 then remove(id); save()
            else hs.alert.show("Could not open the Codex chat") end
        end, { "-b", "com.openai.codex", "codex://threads/" .. target.threadID })
        M.openTask = task
        if task and task:start() then return end
    end
    -- Retain the notification on failure so Option+N can still acknowledge it.
    hs.alert.show("The agent's original window is closed or could not be identified")
end

local function register(id)
    hs.notify.register(tag(id), function() M.open(id) end)
end

function M.send(path)
    local payload = read(path)
    assert(type(payload.title) == "string")
    remove(payload.id) -- One unread notification per conversation.
    payload.target = findTarget(payload)
    payload.sentAt = hs.timer.secondsSinceEpoch()
    state.pending[payload.id] = payload
    state.order[#state.order + 1] = payload.id
    while #state.order > 100 do remove(state.order[1]) end
    register(payload.id)
    hs.notify.new(tag(payload.id), {
        title = payload.title, informativeText = "Finished responding",
        actionButtonTitle = "Open", autoWithdraw = false,
        alwaysPresent = true, withdrawAfter = 0,
    }):send()
    save()
end

local function latest()
    local delivered = {}
    for _, notification in ipairs(hs.notify.deliveredNotifications()) do
        delivered[notification:getFunctionTag()] = true
    end
    for i = #state.order, 1, -1 do
        local id = state.order[i]
        local payload = state.pending[id]
        if payload and (delivered[tag(id)] or hs.timer.secondsSinceEpoch() - payload.sentAt < 2) then
            return id
        end
        -- A notification dismissed with the mouse must not consume a shortcut.
        remove(id)
    end
    save()
end

function M.dismissLatest()
    local id = latest()
    if id then remove(id); save() end
end

function M.openLatest()
    local id = latest()
    if id then M.open(id) end
end

function M.bind()
    if #shortcuts > 0 then return end
    shortcuts[1] = hs.hotkey.bind({ "alt" }, "n", M.dismissLatest)
    shortcuts[2] = hs.hotkey.bind({ "alt", "shift" }, "n", M.openLatest)
end

-- Restore callbacks and ordering after Hammerspoon reload/restart.
for _, id in ipairs(state.order) do register(id) end
return M

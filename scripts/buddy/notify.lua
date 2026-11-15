-- Notification bridge. No model calls or code inspection happen here.
local M = {}
local tag = "buddy-check-in"
local settingsKey = "buddy.lastNotification"

function M.open()
    local payload = hs.settings.get(settingsKey)
    if not payload then return end
    for _, app in ipairs(hs.application.applicationsForBundleID("com.mitchellh.ghostty")) do
        for _, window in ipairs(app:allWindows()) do
            if window:title() == "Buddy" then
                window:focus()
                return
            end
        end
    end
    -- Pass arguments directly; task text never becomes a shell command.
    local task = hs.task.new("/usr/bin/open", function(code)
        if code ~= 0 then hs.alert.show("Open a terminal and run buddy to reply") end
    end, { "-na", "Ghostty", "--args", "--window-save-state=never", "--title=Buddy",
        "-e", payload.python, payload.script, "--data-dir", payload.data, "chat" })
    M.openTask = task
    if not task:start() then hs.alert.show("Open a terminal and run buddy to reply") end
end

hs.notify.register(tag, M.open)

function M.send(path)
    local file = assert(io.open(path, "r"))
    local payload = hs.json.decode(file:read("*a"))
    file:close()
    assert(type(payload) == "table" and type(payload.id) == "string")
    for _, key in ipairs({ "task", "python", "script", "data" }) do
        assert(type(payload[key]) == "string")
    end
    local previous = hs.settings.get(settingsKey)
    if previous and previous.id == payload.id then return end
    -- Replacing a reminder must not withdraw notifications from unrelated utilities.
    for _, notification in ipairs(hs.notify.deliveredNotifications()) do
        if notification:getFunctionTag() == tag then notification:withdraw() end
    end
    local notification = hs.notify.new(tag, {
        title = "Buddy · time to check in",
        informativeText = payload.question or ("How did it go with: " .. payload.task .. "?"),
        actionButtonTitle = "Open Buddy",
        withdrawAfter = 0,
    })
    notification:send()
    hs.settings.set(settingsKey, payload)
end

return M

# Agent completion notifications

The Mac Home Manager module `home/agent-notifications.nix` installs a shared
`~/.local/bin/agent-notify` command and a Pi extension. During activation it
merges Codex's `notify` and Claude Code's `Stop` and `UserPromptSubmit` hooks into their writable configs.
Existing settings and Claude hooks are retained. Original config files are
backed up once beside the originals with the suffix `.pre-agent-notify`.

An existing Codex notification command is saved in
`~/.local/state/agent-notify/codex-notify.json` and called with the original event
before showing the banner. This preserves the desktop computer-use callback.

The banner contains the agent name and session name, or the project directory
when no name is available. Codex names are read from its local SQLite database
in read-only mode. Claude names are best-effort, from `custom-title` transcript
metadata (or `session_title` if supplied). Pi uses `getSessionName()` and waits
for `agent_settled`, after automatic retries and queued follow-ups. Internal
Codex/Claude metadata may change; missing metadata falls back to the directory.
Pi notifications are limited to interactive sessions.

## Shortcuts and opening sessions

Hammerspoon owns the agent notifications and implements the same shortcuts as
Linux's Mako configuration:

| macOS shortcut | Action |
| --- | --- |
| Option+N | Dismiss the latest unread agent notification, without changing focus |
| Option+Shift+N | Open its originating window or chat, then dismiss it |
| Click the notification / Open | Same as Option+Shift+N |

With the Mac's existing Command/Option swap, Option means the physical Command
key beside Space. These shortcuts only handle our agent notifications; Buddy
and other applications are untouched. Repeated completions in a conversation
replace its previous unread notification. Older conversations remain queued.
The queue and click callbacks survive Hammerspoon restarts. Mouse-dismissed
notifications are skipped, and notifications remain in Notification Center
after their banners disappear.

Claude's prompt hook and Pi's interactive input event record the frontmost
terminal window before work begins. Only a window belonging to the agent's
actual terminal ancestor process is eligible; inherited environment variables
alone cannot select a terminal. This captures a window, not an individual tab
or split pane. The user must submit another prompt after installing these hooks
to record a window for an already running session.

Codex CLI windows are matched by their session title, requiring a unique match.
Desktop Codex uses the documented
[`codex://threads/<thread-id>` link](https://learn.chatgpt.com/docs/reference/commands#deep-links),
also used as a fallback when a CLI window cannot be identified. This fallback
opens the conversation in the desktop app. If a captured window has closed or
the match is ambiguous, the shortcut keeps the notification and shows an error
instead of jumping to an arbitrary window. Terminal sessions detached from their
terminal process (for example some tmux setups) may not be identifiable.

## Apply

From this repository, build or activate with the explicit `path:` flake source
to include newly created files even before they have been added to git:

```sh
home-manager build --flake "path:$PWD#eliassimojoki"
home-manager switch --flake "path:$PWD#eliassimojoki"
```

Restart existing Codex/Claude sessions after activation; in Pi, use `/reload`
or restart. Reload Hammerspoon's configuration to install the shortcuts. Allow
notifications for Hammerspoon in macOS settings, choose Banners, and check Focus
settings if the banner does not appear. No sound is requested by the script.
Hammerspoon must be running, with its existing Accessibility permission and
`hs.ipc` enabled by `dotfiles/hammerspoon/init.lua`.

Test a banner without invoking an LLM:

```sh
~/.local/bin/agent-notify pi '{"title":"Notification test"}'
```

Tests use Python with `tomlkit` (the module supplies both):

```sh
python3 scripts/agent-notify/test_notify.py
"$HOME/Applications/Home Manager Apps/Hammerspoon.app/Contents/Frameworks/hs/hs" \
  -c 'dofile(os.getenv("HOME") .. "/eNix-config/scripts/agent-notify/test_notifications.lua")'
```

## Remove

Remove the module import and Hammerspoon loader/bind calls, activate Home Manager,
and reload Hammerspoon. Remove its Stop and UserPromptSubmit hooks
from `~/.claude/settings.json` and restore Codex's previous `notify` array from
`~/.local/state/agent-notify/codex-notify.json` (or remove `notify` if there was
none). Runtime merges intentionally are not undone automatically; don't restore
whole backup configs if you've changed other settings since installation.

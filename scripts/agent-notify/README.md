# Agent completion notifications

The Mac Home Manager module `home/agent-notifications.nix` installs a shared
`~/.local/bin/agent-notify` command and a Pi extension. During activation it
merges Codex's `notify` and Claude Code's `Stop` hook into their writable configs.
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

## Apply

From this repository, build or activate with the explicit `path:` flake source
to include newly created files even before they have been added to git:

```sh
home-manager build --flake "path:$PWD#eliassimojoki"
home-manager switch --flake "path:$PWD#eliassimojoki"
```

Restart existing Codex/Claude sessions after activation; in Pi, use `/reload`
or restart. Allow notifications for the sender shown by macOS (AppleScript
usually appears as Script Editor), choose Banners, and check Focus settings if
the banner does not appear. No sound is requested by the script.

Test a banner without invoking an LLM:

```sh
~/.local/bin/agent-notify pi '{"title":"Notification test"}'
```

Tests use Python with `tomlkit` (the module supplies both):

```sh
python3 scripts/agent-notify/test_notify.py
```

## Remove

Remove the module import and activate Home Manager, then remove its Stop hook
from `~/.claude/settings.json` and restore Codex's previous `notify` array from
`~/.local/state/agent-notify/codex-notify.json` (or remove `notify` if there was
none). Runtime merges intentionally are not undone automatically; don't restore
whole backup configs if you've changed other settings since installation.

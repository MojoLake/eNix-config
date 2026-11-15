# Buddy

A terminal accountability partner for one commitment at a time. Run `buddy`, say what
you want to get working or understand, and press Enter to accept the proposed outcome
and check-in time. You can close the terminal while you work. Click the notification
to return to the conversation. Say `done for today` to stop reminders.

At the deadline, Buddy writes one specific question about what to report. The question
appears in the notification and in the chat, including when the chat is already open.
It stays available when you reopen Buddy and is included in the conversation so the
AI can follow up on your answer. If Codex is unavailable, a task-specific built-in
question still asks what you got working, learned, or got stuck on.

## Commands

```sh
buddy
buddy status
buddy start "Measure throughput at three batch sizes" --minutes 45
buddy snooze 20
buddy done
buddy notify-test
```

Inside chat, `/start 45 TASK`, `/snooze 20`, `/status`, `/done`, `/quit`, and `/help`
work without a model call. `/quit` and closing the terminal keep the reminder active.
Accepting a new proposal replaces the current commitment. Finishing clears it.

## Installation

The Mac Home Manager configuration includes `home/buddy.nix`. Build and activate it
using the repository's normal Home Manager workflow. Reload Hammerspoon once after
the initial installation to register the notification callback. Then run
`buddy notify-test` and click the notification. Allow Hammerspoon notifications in
macOS Settings if needed; Focus modes can silence notifications. A successful send
means macOS accepted the notification, not that the user saw it.

The launcher is `~/.local/bin/buddy`, linked to `scripts/buddy/buddy` in this checkout,
and uses the Home Manager Python interpreter. Code/prompt edits take effect on the
next invocation. To activate only Buddy without applying other Home Manager changes,
build the configuration, create that launcher symlink, copy only
`result/LaunchAgents/org.nix-community.home.buddy.plist` to `~/Library/LaunchAgents/`,
and bootstrap that plist in the user's launchd GUI domain. This matches the files
that normal Home Manager activation manages. For untracked new files, build with
`home-manager build --flake path:$HOME/eNix-config#eliassimojoki`.

The launchd agent `org.nix-community.home.buddy` checks for a due reminder every
30 seconds, independently of the terminal and Codex. It sends one notification per
agreed deadline. Failed delivery is retried. After sleep it sends one overdue
check-in once the worker runs again. It does not wake the Mac. At the deadline it
makes one model call to write the question (up to 20 seconds), then saves it so
notification retries and reopening the chat don't repeat that call.
The worker's errors go to `~/Library/Logs/buddy.log`.

Notification clicks focus an existing Ghostty window titled Buddy, or launch a new
Ghostty instance with session restoration disabled. Hammerspoon must be running for
callbacks. If a click fails, simply run `buddy` again. Only one chat can run at a time.

## Storage and model

Conversation, active commitment, and proposed commitment live in
`~/Library/Application Support/Buddy/buddy.sqlite3`, outside this repository.
Directories/files created by Buddy are user-only. `--data-dir PATH` selects an isolated
store (useful for testing). History is retained locally; the latest 24 messages and
current commitment are sent to Codex for a reply. This is not a fully local model.

Buddy uses the signed-in Codex CLI, with a temporary working directory, user/project
configuration and tools disabled, and structured responses. It receives only the
conversation and commitment, not work files. Chat calls have a 90-second timeout. Model
failures leave the deadline intact. `BUDDY_CODEX` overrides the CLI executable;
`BUDDY_MODEL` optionally selects a model. The prompt is `scripts/buddy/prompt.txt`.

## Verification

```sh
python3 -m unittest discover -s scripts/buddy -p 'test_*.py' -v
"$HOME/Applications/Home Manager Apps/Hammerspoon.app/Contents/Frameworks/hs/hs" \
  -c 'dofile(os.getenv("HOME") .. "/eNix-config/scripts/buddy/test_notify.lua")'
```

The tests cover restart/sleep catch-up, duplicate suppression, failure/retry,
rescheduling, finishing, proposal acceptance, concurrent state changes, model
outages, notification argument handling, and callback restoration. For a live check,
use an isolated store, start a one-minute commitment, and invoke `worker` after it is
due. A separate worker invocation verifies no second notification is sent.

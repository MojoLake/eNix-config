# FocusGuard

A small native macOS website blocker. Policy lives in `home/focusguard.nix`;
the installed root service maintains `/etc/hosts`. No Rosetta, account, cloud,
browser extension, or subscription is needed. The interface is a terminal command.

## Current policy

- YouTube, LinkedIn, and X (including the configured mobile/alternate hostnames).
- Unblocking one service requires a reason and typing one educational passage
  (roughly 250 words), followed by an ungraded recall question.
- Thirty offline passages cover six topics: KV cache, cache offloading, GPU
  performance, scheduling, parallelism and networks, and measurement and operations.
- Passages are shuffled without repeats until the set is complete. Each passage
  has two recall questions, alternating on later visits.
- Default exception: 20 minutes; maximum: 30 minutes.
- Other services remain blocked during the exception.
- Exceptions expire automatically and survive service restarts. Sleep counts
  toward the expiry; rolling the clock backwards closes exceptions.
- The reason is recorded locally, not assessed by AI.

## Install

Review `home/focusguard.nix`, then rebuild Home Manager and explicitly install:

```sh
cd ~/eNix-config
home-manager switch --flake path:$PWD#eliassimojoki
focusguard install
focusguard status
```

The `path:` form includes new files before they have been added to Git. Once
tracked, the usual `home-manager switch --flake .#eliassimojoki` works too.

`focusguard install` compiles the Swift source using Apple's command-line tools
(`xcrun swiftc`), signs the executable locally, and requests `sudo` to install it.
This builds natively for the current Mac; the compiler itself is not pinned by Nix.
Home Manager installs the command and references the policy/source, but **does not
activate or update the privileged service automatically**. After changing policy,
rebuild Home Manager and run `focusguard install` again. Reinstallation closes
existing exceptions. The passage rotation and completed-visit history are retained.
The previously installed random-character challenge remains active until both
the rebuild and `focusguard install` have completed.

Installation backs up the original hosts file, adopts mappings for the configured
domains (including the earlier manual blocks), and preserves other mappings.
It refuses a symlinked `/etc/hosts` rather than competing with another manager.
An activation failure attempts to restore the previous files and service.

## Use

```sh
focusguard unlock youtube       # defaults to 20 minutes
focusguard unlock linkedin 10
focusguard unlock x 5
focusguard status
focusguard lock youtube         # end one exception early
focusguard lock                 # end all exceptions
```

These commands use administrator authentication. The passage appears one paragraph
at a time, with a prompt to type one short line and press Enter. Paragraph,
line, and word progress are shown. Left/Right move the cursor; Backspace removes
the preceding character and forward Delete removes the character at the cursor.
Home/End (or Ctrl-A/Ctrl-E) move to the ends; Option-B/Option-F and common modified
arrow sequences move by word. Ctrl-U clears the current line. Ctrl-D deletes at
the cursor instead of canceling. A mismatch identifies the first differing word
and preserves your input.
Case, extra whitespace, straight/curly apostrophes, and ordinary punctuation are
flexible. Decimal values remain distinct. Escape, Up/Down, and unsupported escape
sequences are ignored without ending the session.

After typing, the passage is cleared from an alternate terminal screen before
the recall question appears. Write a short answer, or type `skip`. The explanation
and source links appear for self-checking; press Enter to finish. Recall is never
graded, and answers are not saved or sent anywhere. The unlock timer starts only
after the challenge and self-check are finished.

Ctrl-C cancels without unlocking. The same passage remains next, although partial
typing is not saved. Only one unlock challenge can run at a time, while the daemon
continues enforcing blocks and expiry. Bracketed paste is discarded in full,
including embedded newlines, with a notice. It does not cancel the session,
change already typed text, or reset completed lines. Only Ctrl-C deliberately
cancels; terminal disconnection and actual I/O failures can still end a session.
There is no typing-speed heuristic: buffered or fast typing is accepted. Paste
from a terminal that does not send bracketed-paste markers cannot reliably be
distinguished from typing. This is friction, not human verification.

## Passage library

`scripts/focusguard/passages.json` contains the generated passages, stable IDs,
topics, paragraphs, two recall question/answer pairs per passage, and primary-source
links. The initial set was written around the learning notes on cache offloading,
inference performance, and serving metrics. Numerical examples state their
assumptions rather than claiming live production capacities.

Generation happens ahead of time: unlocking needs no network, API key, or model.
To refresh the collection, edit this JSON, validate it with the tests below, rebuild
Home Manager, and reinstall. The policy embeds the collection so the privileged
service does not depend on writable files in your home directory. Passages must
have 200–300 words, 3–6 paragraphs, at least two recall questions, and source links.
Changing the set of IDs starts a new shuffle; keeping IDs retains visit counts.
This rotation is only for unlock variety, not a replacement for Anki scheduling.

## What runs

`/Library/LaunchDaemons/local.focusguard.plist` starts one root service at boot.
launchd restarts it if it exits. Every two seconds it checks the hosts file, restores
owned mappings, and expires exceptions. DNS caches are flushed when hosts changes.
The service reads only its installed, root-owned policy and state, not files in
your home directory. File locking serializes exceptions with service updates.
It never blocks Terminal, Activity Monitor, or system settings.

Files under `/Library/Application Support/FocusGuard/`:

- `focusguard`: native executable.
- `policy.json`: installed policy.
- `state.json`: exceptions and their expiry (root-only).
- `learning.json`: pending rotation and completed-visit counts (root-only).
- `challenge.lock`: serializes interactive challenges without blocking the daemon.
- `requests.jsonl`: reasons and durations (root-only).
- `hosts.before-install`: initial backup (root-only).
- `service.log`: daemon errors.

## Limits

This enforces hostname mappings, not a firewall. Existing browser connections,
cached results, proxies, or applications that bypass the system resolver may
continue accessing a site. Subdomains must be listed explicitly; hosts files do
not support wildcards. It cannot allow one YouTube lecture while blocking the feed.
Restart your browser when checking block/unblock behavior. This version has no
menu-bar UI or browser integration.

Administrator access can disable the service, change policy, or uninstall it.
Reinstalling a different policy is also an administrative bypass. The service
makes casual hosts edits ineffective; it does not remove control of your Mac.
Deleting/damaging the managed-block markers makes the service report an error
rather than risk deleting unrelated hosts content. Fix the markers or restore
the affected block if this occurs. This is another intentional recovery escape.

## Uninstall and recovery

```sh
focusguard uninstall
```

This unloads the daemon, removes its launchd plist and owned hosts mappings, and
refreshes DNS. Other hosts entries are preserved. It deliberately retains the
executable, policy, original backup, and logs for inspection/recovery. The manual
blocks adopted on installation are **not** re-added. Remove the retained directory
only after checking that you no longer need its backup. Remove the module import
from `home/darwin.nix` and rebuild to remove the command from Home Manager.

If the wrapper is unavailable:

```sh
sudo '/Library/Application Support/FocusGuard/focusguard' uninstall
```

If the executable is broken, unload it with
`sudo launchctl bootout system/local.focusguard`, remove its plist, and edit
`/etc/hosts` to remove the section between `# BEGIN FOCUSGUARD MANAGED BLOCK` and
`# END FOCUSGUARD MANAGED BLOCK`. Flush DNS with `sudo dscacheutil -flushcache`
and `sudo killall -HUP mDNSResponder`. Compare the saved backup instead of blindly
overwriting hosts: other software may have added entries since installation.

## Validation

```sh
bash scripts/focusguard/test.sh
nix build --no-link path:$PWD#homeConfigurations.eliassimojoki.activationPackage
```

Tests use temporary files and pseudo-terminals without modifying `/etc/hosts` or
loading a daemon. They cover expiry/restart/clock handling, corruption, preserving
unrelated hosts entries, repairs, cleanup, input validation, and the actual typing
challenge. They also validate the entire passage library, two rotation cycles,
history persistence, legacy policy decoding, prose normalization, editable mistakes,
normal fast keystrokes, cursor navigation and deletion, split escape sequences,
nonfatal paste with preserved text/progress, recall/skip/cancel, a complete real
passage, narrow-terminal wrapping, and terminal restoration. A production binary is compiled and checked
for native architecture.
Privileged launchd installation and browser behavior require a separate live check
after installation; automated tests do not claim to cover them.

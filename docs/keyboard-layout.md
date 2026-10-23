# Keyboard layout and NixOS implementation handoff

Elias wants the same physical modifier positions for desktop management and
application shortcuts on the work MacBook and personal NixOS laptop. The key
immediately left of Space is the desktop modifier. The next key outward is the
application modifier. Keep window navigation easy and preserve normal terminal
control sequences. This decision was made on 19 October 2026.

The current task implements macOS only. A future agent on the NixOS machine
should implement the Linux side after checking its live configuration. Do not
copy macOS modifier names directly into niri: keyd already remaps the keys.

## Physical layout

| Role | Mac keycap | Linux laptop keycap | Purpose |
| --- | --- | --- | --- |
| DESKTOP | Left Command, beside Space | Left Alt, beside Space | Windows, workspaces, monitors, desktop switching |
| APP | Left Option, one key outward | Left Super, one key outward | Copy, paste, undo, find, save, application tabs |
| CTRL | Caps Lock | Caps Lock | Terminal control sequences and existing secondary desktop bindings |

These names describe physical roles, not the modifier events sent to programs.
Application tab switching, editor pane navigation, and text movement stay with
the application; do not migrate every action described as navigation to DESKTOP.
Preserve existing desktop movement chords instead of changing the whole layout.

## Shortcut contract

| Physical chord | Intended action |
| --- | --- |
| DESKTOP + H / L | Focus left / right column |
| DESKTOP + J / K | Focus window or workspace down / up |
| DESKTOP + CTRL + direction | Existing move-window or move-column action |
| DESKTOP + Shift + direction | Existing monitor-focus action |
| DESKTOP + number | Select workspace |
| DESKTOP + Space | Spotlight on macOS; application launcher on NixOS |
| DESKTOP + D | New Ghostty window beside the current window |
| DESKTOP + Tab | Native app switcher on macOS; hold DESKTOP and repeat Tab to cycle |
| DESKTOP + Shift + Tab | Cycle the switcher backward |
| DESKTOP + backtick | Cycle windows of the current app |
| DESKTOP + Shift + backtick | Cycle those windows backward |
| APP + C / V / X | Copy / paste / cut |
| APP + Z / Shift+Z | Undo / redo, using the application's actual shortcuts |
| APP + A / F / S | Select all / find / save |
| APP + T / W | Application new tab / close tab |
| CTRL + C / D / Z | Terminal interrupt / EOF / suspend, unchanged |

Elias has never used OmniWM's old Option+Tab (previous window) or Option+Grave
(quake terminal) bindings. They can be unassigned without replacement.

## macOS implementation

macOS Modifier Keys already swaps Command and Option on both sides and maps
Caps Lock to Control. Thus physical DESKTOP emits logical Option, and APP emits
logical Command. The host preference is
`com.apple.keyboard.modifiermapping.0-0-0` in the current-host global domain.
This is an existing system setting, not currently managed by Nix. On a fresh Mac,
configure the same mappings in System Settings before using these bindings.

`dotfiles/omniwm/settings.toml` is linked into the live OmniWM config and reloads
when edited. Keep its Option-based spatial navigation. Free Option+Tab and
Option+Grave before enabling the desktop switcher exceptions.

The Hammerspoon configuration in `dotfiles/hammerspoon/init.lua`
translates logical Option+Tab, Option+Grave, and Option+Space to native Command
equivalents. Option+Space opens Spotlight without latching the modifier;
Control+Option+Space remains OmniWM's command palette.
It preserves Shift and holds the translated Command flag throughout app
switching until Option is released. This preserves native application switching
rather than silently substituting a window switcher. `home/darwin.nix` pins the
upstream signed Hammerspoon release and configures startup at login.
Startup opens `~/Applications/Home Manager Apps/Hammerspoon.app`, the installed
copy approved in macOS privacy settings, rather than the Nix store copy.

Hammerspoon replaces skhd and also blocks accidental Command+H application
hiding, the only binding previously provided by skhd. Do not run both daemons.

Logical Option+D (physical Command+D) opens a new Ghostty window. Hammerspoon
selects Ghostty's File > New Window menu item without first activating an
existing terminal, so OmniWM inserts the new window beside the current column
on the current workspace. If Ghostty is not running, it launches the app instead.
This uses Hammerspoon's existing Accessibility permission; no Ghostty global
binding, AppleScript Automation permission, or OmniWM IPC is required.
The Hammerspoon config is linked to the repository; reload Hammerspoon after edits.

Hammerspoon needs macOS Accessibility permission. Secure Input can prevent
event-tap shortcuts from working. The outer APP key's native Command+Tab and
Command+backtick remain fallback shortcuts. The normal application shortcuts
continue using macOS Command without per-application translation.

## Existing Linux configuration

Read `AGENTS.md`, `configuration.nix`, `home/linux.nix`,
`dotfiles/niri/config.kdl`, and `scripts/macos-key` first. Recheck the actual
NixOS machine; the checked-in files may lag its active configuration.

The checked-in keyd mappings are:

```nix
capslock = "layer(control)";
leftalt = "layer(meta)";
leftmeta = "layer(alt)";
rightalt = "layer(meta)";
leftcontrol = "layer(altgr)";
```

Consequently physical DESKTOP currently emits Super/Meta, while physical APP
emits Alt. niri uses `Mod` (normally Super in a desktop session) for both window
management and several application shortcuts. Physical Alt working as the
desktop key does not imply that niri receives logical Alt.

`Mod+A/C/V` call `scripts/macos-key`, which emits Ctrl shortcuts in ordinary
applications and Ctrl+Shift shortcuts in Ghostty. `Mod+T/W` currently inject
Ctrl+T/W unconditionally. Review those terminal cases instead of copying them
blindly. Preserve real Ctrl+C for interrupting terminal programs.

## Work for the NixOS agent

1. Confirm physical key positions and emitted modifiers with keyd/niri tools.
   Choose one consistent implementation. Keeping keyd's existing left-hand
   mapping and moving application bindings to logical Alt is a small change.
   Alternatively make physical Alt emit Alt and Super emit Super, explicitly
   set niri's desktop modifier, and translate selected Super application chords.
   Do not mix these approaches or apply the swap twice.
2. Keep desktop focus/movement/workspace chords on physical DESKTOP. Move the
   current application A/C/V/T/W bindings off niri's desktop modifier. Add the
   agreed common APP actions with correct behavior for the applications Elias
   uses. A narrow translation is preferable to a global APP-to-Control swap.
3. Preserve terminal Ctrl sequences and use Ghostty's actual clipboard and tab
   actions. Check undo/redo and select-all semantics instead of assuming every
   terminal/editor shortcut matches a browser.
4. Implement DESKTOP+Tab cycling, Shift reversal, and release-to-select using
   capabilities of the installed niri version. macOS switches applications;
   a compositor switcher may switch individual windows. Explain any semantic
   difference rather than silently claiming exact parity. Implement same-app
   window cycling for DESKTOP+backtick if practical.
   Put the application launcher on physical DESKTOP+Space to match Spotlight.
5. Preserve access to symbols on the configured US, Finnish, and Spanish
   layouts. Inspect right Alt and physical Left Control carefully: keyd
   currently repurposes them. Any right-side redesign should be deliberate.
6. Build and activate the appropriate Home Manager and NixOS configurations
   when requested. keyd changes require the system configuration; niri changes
   are in Home Manager. Follow repository commands and activation rules.

## Acceptance checks

Check spatial navigation; application copy/paste, undo, find and save; terminal
copy/paste and Ctrl+C; new/close tabs; and language-specific symbols. For the
switcher, hold DESKTOP, press and release Tab repeatedly, reverse with Shift,
cancel with Escape, and release DESKTOP to select. Also test releasing DESKTOP
before Tab so no modifier gets stuck. Same-app window cycling should work in
both directions with two windows of the same application.

Check configuration reload and login startup. Keep the native fallback chords
available during rollout. Do not commit changes unless Elias asks.

The Mac Home Manager configuration has been built and activated. Hammerspoon
reports Accessibility granted and its event tap enabled; skhd is no longer
running. `dotfiles/hammerspoon/test.lua` checks held Tab cycling, Shift reversal,
modifier release order, Escape, backtick, and unaffected shortcuts using mocked
events. Run it with Hammerspoon's bundled CLI:

```sh
"$HOME/Applications/Home Manager Apps/Hammerspoon.app/Contents/Frameworks/hs/hs" \
  -c 'dofile(os.getenv("HOME") .. "/eNix-config/dotfiles/hammerspoon/test.lua")'
```

The event tests do not replace trying the physical keys or testing a new login.

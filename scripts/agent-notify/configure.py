"""Merge only our settings into writable app configs during HM activation."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import tempfile

import tomlkit


def write(path, text):
    if path.exists() and path.read_text() == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_name(path.name + ".pre-agent-notify")
    if path.exists() and not backup.exists():
        shutil.copyfile(path, backup)
        backup.chmod(0o600)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            output.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def merge(target, source):
    for key, value in source.items():
        if isinstance(value, dict):
            if key not in target:
                target[key] = {}
            merge(target[key], value)
        else:
            target[key] = value


def without_self_callback(arguments, notification_command):
    """Keep the desktop callback without forwarding back into our own hook."""
    arguments = list(arguments)
    if (len(arguments) >= 2 and Path(arguments[0]).name == "SkyComputerUseClient"
            and arguments[1] == "turn-ended" and "--previous-notify" in arguments):
        index = arguments.index("--previous-notify")
        if index + 1 < len(arguments):
            try:
                nested = json.loads(arguments[index + 1])
            except ValueError:
                return arguments
            if nested == notification_command:
                del arguments[index:index + 2]
    return arguments


def configure(home, command, settings):
    codex_path = home / ".codex/config.toml"
    codex = tomlkit.parse(codex_path.read_text()) if codex_path.exists() else tomlkit.document()
    claude_path = home / ".claude/settings.json"
    claude = json.loads(claude_path.read_text()) if claude_path.exists() else {}
    notification_command = [command, "codex"]
    previous = codex.get("notify")
    saved_callback = home / ".local/state/agent-notify/codex-notify.json"
    # Save the existing desktop computer-use callback before replacing it.
    if previous and list(previous) != notification_command:
        if not isinstance(previous, list) or not all(isinstance(arg, str) for arg in previous):
            raise ValueError("Codex notify must be an array of command arguments")
        write(saved_callback, json.dumps(without_self_callback(previous, notification_command)) + "\n")
    elif saved_callback.exists():
        # Repair callbacks saved by an older activation, too.
        saved = json.loads(saved_callback.read_text())
        write(saved_callback, json.dumps(without_self_callback(saved, notification_command)) + "\n")
    merge(codex, settings)
    codex["notify"] = notification_command

    for event, arguments in [("Stop", " claude"), ("UserPromptSubmit", " capture claude")]:
        groups = claude.setdefault("hooks", {}).setdefault(event, [])
        hook_command = shlex.quote(command) + arguments
        if not any(hook.get("command") == hook_command
                   for group in groups for hook in group.get("hooks", [])):
            groups.append({"hooks": [{"type": "command", "command": hook_command, "timeout": 10}]})
    write(codex_path, tomlkit.dumps(codex))
    write(claude_path, json.dumps(claude, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--codex-settings", type=Path, required=True)
    args = parser.parse_args()
    configure(args.home, args.command, json.loads(args.codex_settings.read_text()))

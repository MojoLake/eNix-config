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


def configure(home, command, settings):
    codex_path = home / ".codex/config.toml"
    codex = tomlkit.parse(codex_path.read_text()) if codex_path.exists() else tomlkit.document()
    claude_path = home / ".claude/settings.json"
    claude = json.loads(claude_path.read_text()) if claude_path.exists() else {}
    notification_command = [command, "codex"]
    previous = codex.get("notify")
    # Save the existing desktop computer-use callback before replacing it.
    if previous and list(previous) != notification_command:
        if not isinstance(previous, list) or not all(isinstance(arg, str) for arg in previous):
            raise ValueError("Codex notify must be an array of command arguments")
        write(home / ".local/state/agent-notify/codex-notify.json", json.dumps(list(previous)) + "\n")
    merge(codex, settings)
    codex["notify"] = notification_command

    stop = claude.setdefault("hooks", {}).setdefault("Stop", [])
    hook_command = shlex.quote(command) + " claude"
    if not any(hook.get("command") == hook_command
               for group in stop for hook in group.get("hooks", [])):
        stop.append({"hooks": [{"type": "command", "command": hook_command, "timeout": 10}]})
    write(codex_path, tomlkit.dumps(codex))
    write(claude_path, json.dumps(claude, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--codex-settings", type=Path, required=True)
    args = parser.parse_args()
    configure(args.home, args.command, json.loads(args.codex_settings.read_text()))

"""Native completion banners; session contents never become executable code."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


HOME = Path.home()
APPLESCRIPT = '''on run argv
    display notification (item 2 of argv) with title (item 1 of argv)
end run'''


def codex_title(thread_id):
    if not thread_id:
        return None
    directory = Path(os.environ.get("CODEX_HOME", HOME / ".codex"))
    databases = sorted(directory.glob("state_*.sqlite"),
                       key=lambda p: int(p.stem.split("_")[-1]) if p.stem.split("_")[-1].isdigit() else -1,
                       reverse=True)
    for path in databases:
        try:
            connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0.2)
            try:
                columns = {row[1] for row in connection.execute("PRAGMA table_info(threads)")}
                # Current desktop titles are in `name`; older versions use `title`.
                field = "COALESCE(NULLIF(name, ''), title)" if "name" in columns else "title"
                row = connection.execute(f"SELECT {field} FROM threads WHERE id = ?", (thread_id,)).fetchone()
                if row and row[0]:
                    return row[0]
            finally:
                connection.close()
        except sqlite3.Error:
            continue
    return None


def claude_title(event):
    if event.get("session_title"):
        return event["session_title"]
    transcript = event.get("transcript_path")
    if not transcript:
        return None
    try:
        # Best effort: transcript metadata is internal and may change. Limit IO
        # even for very long sessions; the project name remains a safe fallback.
        with open(transcript, "rb") as source:
            source.seek(0, 2)
            source.seek(max(0, source.tell() - 1024 * 1024))
            lines = source.read().decode("utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if item.get("type") == "custom-title" and item.get("customTitle"):
                return item["customTitle"]
    except OSError:
        pass
    return None


def forward_codex(raw):
    path = HOME / ".local/state/agent-notify/codex-notify.json"
    if path.exists():
        command = json.loads(path.read_text())
        subprocess.run([*command, raw], timeout=5, check=False, stdout=subprocess.DEVNULL)


def label(agent, event):
    title = None
    if agent == "codex":
        title = codex_title(event.get("thread-id"))
    elif agent == "claude":
        title = claude_title(event)
    elif agent == "pi":
        title = event.get("title")
    title = title or Path(event.get("cwd") or str(HOME)).name
    title = " ".join(str(title).split())[:160]
    return f"{ {'codex': 'Codex', 'claude': 'Claude Code', 'pi': 'Pi'}[agent]} · {title}"


def main():
    agent = sys.argv[1]
    raw = sys.stdin.read() if agent == "claude" else sys.argv[2]
    if agent == "codex":
        try:
            forward_codex(raw)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            print(f"agent-notify: existing Codex callback: {error}", file=sys.stderr)
    event = json.loads(raw)
    if agent == "codex" and event.get("type") != "agent-turn-complete":
        return
    subprocess.run(["/usr/bin/osascript", "-e", APPLESCRIPT, label(agent, event), "Finished responding"],
                   timeout=3, check=True, stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # A desktop banner must never block an agent's completion.
        print(f"agent-notify: {error}", file=sys.stderr)

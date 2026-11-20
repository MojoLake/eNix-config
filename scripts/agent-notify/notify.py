"""Native completion banners; session contents never become executable code."""
import json
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


HOME = Path.home()
HERE = Path(__file__).resolve().parent


def codex_thread(thread_id):
    """Read persisted metadata; temporary background tasks have no thread row."""
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
                connection.row_factory = sqlite3.Row
                row = connection.execute("SELECT * FROM threads WHERE id = ?", (thread_id,)).fetchone()
                if row is not None:
                    return dict(row)
            finally:
                connection.close()
        except sqlite3.Error:
            continue
    return None


def codex_title(thread_id):
    thread = codex_thread(thread_id) or {}
    # Current desktop titles are in `name`; older versions use `title`.
    return thread.get("name") or thread.get("title")


def codex_should_notify(thread_id):
    thread = codex_thread(thread_id)
    if not thread:
        return False
    # Persisted subagents also finish turns, but are not standalone user chats.
    source = thread.get("source")
    try:
        source = json.loads(source)
    except (TypeError, ValueError):
        pass
    if source == "subagent" or isinstance(source, dict) and "subagent" in source:
        return False
    return thread.get("agent_path") in (None, "", "/root")


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


def session_title(agent, event):
    title = None
    if agent == "codex":
        title = codex_title(event.get("thread-id"))
    elif agent == "claude":
        title = claude_title(event)
    elif agent == "pi":
        title = event.get("title")
    return title


def label(agent, event):
    title = session_title(agent, event) or Path(event.get("cwd") or str(HOME)).name
    title = " ".join(str(title).split())[:160]
    return f"{ {'codex': 'Codex', 'claude': 'Claude Code', 'pi': 'Pi'}[agent]} · {title}"


def terminal_context():
    """Find the actual terminal ancestor, not an inherited TERM_PROGRAM value."""
    result = subprocess.run(["/bin/ps", "-axo", "pid=,ppid=,comm="],
                            capture_output=True, text=True, timeout=2, check=True)
    processes = {}
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) == 3:
            processes[int(fields[0])] = (int(fields[1]), fields[2])
    bundles = {"ghostty": "com.mitchellh.ghostty", "Terminal": "com.apple.Terminal",
               "iTerm2": "com.googlecode.iterm2"}
    pid = os.getppid()
    for _ in range(40):
        if pid not in processes:
            break
        parent, command = processes[pid]
        bundle = bundles.get(Path(command).name)
        if bundle:
            return {"bundle": bundle, "pid": pid}
        if parent == pid:
            break
        pid = parent
    return None


def payload(agent, event):
    session = event.get("thread-id") or event.get("session_id") or event.get("cwd") or "manual"
    return {
        "id": hashlib.sha256(f"{agent}:{session}".encode()).hexdigest()[:32],
        "agent": agent,
        "title": label(agent, event),
        "sessionTitle": session_title(agent, event),
        "threadID": event.get("thread-id") if agent == "codex" else None,
        "terminal": terminal_context(),
    }


def lua_string(value):
    return '"' + "".join(f"\\{byte:03d}" for byte in str(value).encode()) + '"'


def send_to_hammerspoon(data, capture=False):
    hs = HOME / "Applications/Home Manager Apps/Hammerspoon.app/Contents/Frameworks/hs/hs"
    directory = HOME / ".local/state/agent-notify"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir=directory) as stream:
        json.dump(data, stream)
        stream.flush()
        # All variable text travels in a private JSON file, never as Lua code.
        method = "capture" if capture else "send"
        code = ("if not agentNotifications then agentNotifications=dofile("
                + lua_string(HERE / "notifications.lua")
                + "); agentNotifications.bind() end; agentNotifications."
                + method + "(" + lua_string(stream.name) + "); print('AGENT_NOTIFY_OK')")
        result = subprocess.run([str(hs), "-c", code], capture_output=True, text=True, timeout=3)
        if result.returncode or "AGENT_NOTIFY_OK" not in result.stdout:
            raise RuntimeError("Hammerspoon notification bridge unavailable: " + result.stderr.strip())


def main():
    capture = sys.argv[1] == "capture"
    args = sys.argv[2:] if capture else sys.argv[1:]
    agent = args[0]
    # Claude reviews launched by Codex inherit its thread marker. They are
    # background work within that chat, so neither capture a window nor notify.
    if agent == "claude" and os.environ.get("CODEX_THREAD_ID"):
        return
    raw = sys.stdin.read() if agent == "claude" else args[1]
    if agent == "codex" and not capture:
        try:
            forward_codex(raw)
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            print(f"agent-notify: existing Codex callback: {error}", file=sys.stderr)
    event = json.loads(raw)
    if agent == "codex" and not capture:
        if event.get("type") != "agent-turn-complete" or not codex_should_notify(event.get("thread-id")):
            return
    send_to_hammerspoon(payload(agent, event), capture=capture)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # A desktop banner must never block an agent's completion.
        print(f"agent-notify: {error}", file=sys.stderr)

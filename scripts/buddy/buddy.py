#!/usr/bin/env python3
"""One commitment, a conversation, and a persistent local check-in."""
import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import readline
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
import uuid

HERE = Path(__file__).resolve().parent
DEFAULT_DATA = Path.home() / "Library/Application Support/Buddy"
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "reply": {"type": "string"},
        "action": {"type": "string", "enum": ["say", "propose", "finish"]},
        "task": {"type": "string"}, "minutes": {"type": "integer"},
    },
    "required": ["reply", "action", "task", "minutes"],
}


def clean(value):
    return "".join(c for c in str(value) if c == "\n" or not unicodedata.category(c).startswith("C"))


def minutes(value):
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
        raise ValueError("Minutes must be a whole number from 1 to 240.")
    value = int(value)
    if not 1 <= value <= 240:
        raise ValueError("Minutes must be a whole number from 1 to 240.")
    return value


def task_text(value):
    value = " ".join(clean(value).split())
    if not 1 <= len(value) <= 240:
        raise ValueError("Keep the commitment between 1 and 240 characters.")
    return value


def when(timestamp):
    return dt.datetime.fromtimestamp(timestamp).astimezone().strftime("%a %H:%M")


class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.root / "buddy.sqlite3", timeout=25)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS state (
                id INTEGER PRIMARY KEY CHECK(id=1), task TEXT,
                due REAL, notification TEXT, sent INTEGER NOT NULL DEFAULT 0,
                proposal TEXT, revision INTEGER NOT NULL DEFAULT 0
            );
            INSERT OR IGNORE INTO state(id) VALUES(1);
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY, role TEXT NOT NULL,
                content TEXT NOT NULL, created REAL NOT NULL
            );
        """)
        with self.transaction():
            columns = {row[1] for row in self.db.execute("PRAGMA table_info(state)")}
            if "checkin" not in columns:
                self.db.execute("ALTER TABLE state ADD COLUMN checkin TEXT")
            if "answered" not in columns:
                self.db.execute("ALTER TABLE state ADD COLUMN answered INTEGER NOT NULL DEFAULT 0")

    @contextlib.contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def state(self):
        result = dict(self.db.execute("SELECT * FROM state WHERE id=1").fetchone())
        result["proposal"] = json.loads(result["proposal"]) if result["proposal"] else None
        return result

    def _message(self, role, content):
        self.db.execute("INSERT INTO messages(role,content,created) VALUES(?,?,?)",
                        (role, clean(content), time.time()))

    def message(self, role, content):
        with self.transaction():
            self._message(role, content)
            if role == "user":
                self.db.execute("UPDATE state SET answered=1 WHERE checkin IS NOT NULL")

    def history(self, limit=24):
        rows = self.db.execute("SELECT role,content FROM messages ORDER BY id DESC LIMIT ?", (limit,))
        return list(reversed([dict(r) for r in rows]))

    def _start(self, task, duration, now):
        due = now + duration * 60
        self.db.execute("""UPDATE state SET task=?,due=?,notification=?,sent=0,
                           proposal=NULL,checkin=NULL,answered=0,revision=revision+1 WHERE id=1""",
                        (task, due, str(uuid.uuid4())))
        self._message("system", f"Agreed commitment: {task}. Check-in: {when(due)}.")
        return due

    def start(self, task, duration, now=None):
        task, duration = task_text(task), minutes(duration)
        with self.transaction():
            return self._start(task, duration, time.time() if now is None else now)

    def accept(self):
        with self.transaction():
            proposal = self.state()["proposal"]
            if not proposal:
                raise ValueError("There is no pending proposal.")
            return self._start(proposal["task"], proposal["minutes"], time.time())

    def snooze(self, duration, now=None):
        duration = minutes(duration)
        with self.transaction():
            task = self.state()["task"]
            if not task:
                raise ValueError("There is no active commitment to extend.")
            return self._start(task, duration, time.time() if now is None else now)

    def _finish(self):
        self.db.execute("""UPDATE state SET task=NULL,due=NULL,notification=NULL,
                           sent=0,proposal=NULL,checkin=NULL,answered=0,revision=revision+1 WHERE id=1""")
        self._message("system", "Session finished. No reminders are scheduled.")

    def finish(self):
        with self.transaction():
            self._finish()

    def reply(self, response, revision):
        with self.transaction():
            if self.state()["revision"] != revision:
                raise ValueError("The commitment changed in another window. Please check /status and try again.")
            self._message("assistant", response["reply"])
            proposal = None
            if response["action"] == "propose":
                proposal = json.dumps({"task": response["task"], "minutes": response["minutes"]})
            elif response["action"] == "finish":
                self._finish()
            self.db.execute("UPDATE state SET proposal=?,revision=revision+1 WHERE id=1", (proposal,))

    def notify_due(self, notify, now=None, model=None):
        now = time.time() if now is None else now
        snapshot = self.state()
        if not snapshot["task"] or (snapshot["sent"] and snapshot["checkin"]) or snapshot["due"] > now:
            return False
        if not snapshot["checkin"]:
            question = fallback_checkin(snapshot["task"])
            if model is not None:
                try:
                    response = model(self, event="check_in", timeout=20)
                    if response["action"] != "say" or "?" not in response["reply"] or len(response["reply"]) > 600:
                        raise ValueError("Expected one short check-in question")
                    question = response["reply"]
                except (ValueError, OSError, subprocess.TimeoutExpired):
                    print("Buddy: Using the fallback check-in question.", file=sys.stderr)
            # Model generation must not hold a database lock or resurrect a cancelled task.
            with self.transaction():
                state = self.state()
                if state["notification"] != snapshot["notification"]:
                    return False
                if not state["checkin"]:
                    self.db.execute("UPDATE state SET checkin=? WHERE id=1", (question,))
                    self._message("assistant", question)
        # Serialize send with cancellation/rescheduling. Failed sends remain pending.
        with self.transaction():
            state = self.state()
            if not state["task"] or state["sent"] or state["due"] > now:
                return False
            notify(state, self.root)
            self.db.execute("UPDATE state SET sent=1 WHERE id=1")
            return True


def validate_response(value):
    if not isinstance(value, dict) or set(value) != set(SCHEMA["required"]):
        raise ValueError("Buddy received an invalid response. Your reminder is unchanged.")
    if not all(isinstance(value[k], str) for k in ("reply", "action", "task")):
        raise ValueError("Buddy received invalid text. Your reminder is unchanged.")
    value["reply"] = clean(value["reply"]).strip()
    if not value["reply"] or len(value["reply"]) > 3000:
        raise ValueError("Buddy's response was empty or too long. Please try again.")
    if value["action"] == "propose":
        value["task"] = task_text(value["task"])
        value["minutes"] = minutes(value["minutes"])
    elif value["action"] in ("say", "finish"):
        if value["task"] != "" or type(value["minutes"]) is not int or value["minutes"] != 0:
            raise ValueError("Buddy received an invalid action. Your reminder is unchanged.")
    else:
        raise ValueError("Buddy received an unknown action. Your reminder is unchanged.")
    return value


def ask_model(store, event="user_message", timeout=90):
    local_codex = Path.home() / ".local/bin/codex"
    codex = os.environ.get("BUDDY_CODEX") or (
        str(local_codex) if local_codex.is_file() else shutil.which("codex"))
    if not codex:
        raise ValueError("Codex is unavailable. Use /start MINUTES TASK to set a reminder directly.")
    payload = {"event": event, "now": dt.datetime.now().astimezone().isoformat(),
               "state": store.state(), "conversation": store.history()}
    with tempfile.TemporaryDirectory(prefix="buddy-chat-") as directory:
        root = Path(directory)
        schema, result = root / "schema.json", root / "result.json"
        schema.write_text(json.dumps(SCHEMA))
        command = [codex, "exec", "--ignore-user-config", "--ignore-rules", "--ephemeral",
                   "--skip-git-repo-check", "--sandbox", "read-only", "--color", "never",
                   "--output-schema", str(schema), "--output-last-message", str(result),
                   "-C", directory, "-c", 'approval_policy="never"',
                   "-c", 'web_search="disabled"', "-c", "project_doc_max_bytes=0",
                   "-c", 'model_reasoning_effort="low"']
        for feature in ("shell_tool", "apps", "plugins", "hooks", "memories", "multi_agent",
                        "browser_use", "computer_use", "image_generation", "skill_search"):
            command += ["--disable", feature]
        if os.environ.get("BUDDY_MODEL"):
            command += ["--model", os.environ["BUDDY_MODEL"]]
        command.append("-")
        # Bound stderr without copying credentials or unrelated diagnostics to the chat.
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                       stderr=errors, text=True, start_new_session=True)
            try:
                process.communicate((HERE / "prompt.txt").read_text() + "\nContext:\n" + json.dumps(payload),
                                    timeout=timeout)
            except BaseException:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise
        if process.returncode or not result.exists():
            raise ValueError("Codex couldn't reply. Your reminder is unchanged. Try again or use /start MINUTES TASK.")
        return validate_response(json.loads(result.read_text()))


def lua_string(value):
    # Lua supports decimal byte escapes; JSON's Unicode escapes are not Lua syntax.
    return '"' + "".join(f"\\{b:03d}" for b in str(value).encode("utf-8")) + '"'


def notify_mac(state, root):
    hs = os.environ.get("BUDDY_HS") or str(Path.home() /
        "Applications/Home Manager Apps/Hammerspoon.app/Contents/Frameworks/hs/hs")
    payload = {"id": state["notification"], "task": state["task"],
               "question": state.get("checkin") or fallback_checkin(state["task"]),
               "python": sys.executable, "script": str(HERE / "buddy.py"), "data": str(root)}
    # A private file carries text as data, not Lua/shell source.
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir=root) as stream:
        json.dump(payload, stream)
        stream.flush()
        code = (f"local b=dofile({lua_string(HERE / 'notify.lua')}); "
                f"b.send({lua_string(stream.name)}); print('BUDDY_SENT')")
        response = subprocess.run([hs, "-c", code], capture_output=True, text=True, timeout=15)
        if response.returncode or "BUDDY_SENT" not in response.stdout:
            raise ValueError("Hammerspoon could not send the check-in; it will be retried.")


def fallback_checkin(task):
    return f'For “{task}”, what did you get working or learn, and is anything blocking you?'


class CheckinDisplay:
    """Show persisted questions in an open chat without losing the current input line."""
    def __init__(self, store):
        self.store = store
        self.seen = None

    def show(self, redraw=False):
        state = self.store.state()
        if not state["checkin"] or state["answered"] or state["notification"] == self.seen:
            return False
        self.seen = state["notification"]
        if redraw:
            sys.stdout.write("\r\033[2K")
        print("\nBuddy: " + state["checkin"], flush=True)
        if redraw:
            sys.stdout.write("\nYou> " + readline.get_line_buffer())
            sys.stdout.flush()
        return True

    def read(self):
        self.show()
        if not sys.stdin.isatty():
            return input("\nYou> ")
        def tick(signum, frame):
            self.show(redraw=True)
        previous = signal.signal(signal.SIGALRM, tick)
        previous_timer = signal.setitimer(signal.ITIMER_REAL, 1, 1)
        try:
            return input("\nYou> ")
        finally:
            signal.setitimer(signal.ITIMER_REAL, *previous_timer)
            signal.signal(signal.SIGALRM, previous)


def status(store):
    state = store.state()
    if state["task"]:
        label = "Check-in due" if state["due"] <= time.time() else "Check-in"
        print(f"\n{state['task']}\n{label}: {when(state['due'])}")
    else:
        print("\nNo active commitment.")
    if state["proposal"]:
        p = state["proposal"]
        print(f"\nProposed: {p['task']}\nCheck in in {p['minutes']} minutes? [Enter to accept; or tell me what to change]")


HELP = """/start MINUTES TASK  Set a commitment directly
/snooze MINUTES      Check back after this many minutes
/status             Show the current commitment
/done               Finish and stop reminders
/quit               Leave chat; keep the reminder
You can also just talk, or say 'done for today'."""


def handle_input(store, text, model=ask_model):
    value = clean(text).strip()
    state = store.state()
    if value.lower() in ("/quit", "/q", "exit"):
        return False
    if value.lower() in ("/done", "done for today", "done", "stop reminders"):
        store.finish()
        print("Buddy: All done. No reminders scheduled.")
        return False
    if value in ("/help", "/?"):
        print(HELP)
    elif value == "/status":
        status(store)
    elif state["proposal"] and value.lower() in ("", "y", "yes", "yep", "ok", "okay", "sure"):
        due = store.accept()
        print(f"Buddy: Agreed. I'll check back {when(due)}. You can close this chat.")
    elif value.startswith("/start "):
        parts = value.split(maxsplit=2)
        if len(parts) != 3:
            raise ValueError("Usage: /start MINUTES TASK")
        due = store.start(parts[2], parts[1])
        print(f"Buddy: I'll check back {when(due)}.")
    elif value.startswith("/snooze "):
        due = store.snooze(value.split(maxsplit=1)[1])
        print(f"Buddy: I'll check back {when(due)}.")
    elif value.startswith("/"):
        print(HELP)
    elif value:
        if len(value) > 6000:
            raise ValueError("Please keep messages under 6,000 characters.")
        store.message("user", value)
        print("Buddy: Thinking…", flush=True)
        revision = store.state()["revision"]
        response = model(store)
        store.reply(response, revision)
        print("\nBuddy: " + response["reply"])
        if response["action"] == "propose":
            status(store)
        if response["action"] == "finish":
            print("No reminders scheduled.")
            return False
    return True


def chat(store):
    with (store.root / "chat.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Buddy is already open in another terminal. Continue there, or close it first.")
        tty = sys.stdout.isatty()
        if tty:
            sys.stdout.write("\033[22;0t\033]0;Buddy\007")
            sys.stdout.flush()
        try:
            print("\nBuddy · one thing at a time\n/help for commands · /quit keeps your reminder")
            status(store)
            checkins = CheckinDisplay(store)
            if checkins.show():
                pass
            elif store.state()["task"]:
                state = store.state()
                if state["due"] <= time.time() and not state["answered"]:
                    print("\nBuddy: " + fallback_checkin(state["task"]))
                else:
                    print("\nBuddy: How is it going?")
            elif not store.state()["proposal"]:
                print("\nBuddy: What do you want to get working or understand?")
            while True:
                try:
                    if not handle_input(store, checkins.read()):
                        break
                except (ValueError, OSError, subprocess.TimeoutExpired) as error:
                    print("\n" + clean(str(error)))
        except (EOFError, KeyboardInterrupt):
            print("\nChat saved. Any agreed reminder is still active.")
        finally:
            if tty:
                sys.stdout.write("\033[23;0t")
                sys.stdout.flush()


def main(argv=None):
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("chat", help="Start or resume the conversation (default)")
    commands.add_parser("status", help="Show the active commitment")
    start = commands.add_parser("start", help="Set a reminder without a model call")
    start.add_argument("task")
    start.add_argument("--minutes", type=int, default=45)
    snooze = commands.add_parser("snooze", help="Reschedule the active reminder")
    snooze.add_argument("minutes", type=int)
    commands.add_parser("done", help="Finish and stop reminders")
    commands.add_parser("worker", help="Deliver a due check-in once (called by launchd)")
    commands.add_parser("notify-test", help="Send a test notification without changing the commitment")
    args = parser.parse_args(argv)
    store = Store(args.data_dir)
    try:
        if args.command in (None, "chat"):
            chat(store)
        elif args.command == "status":
            status(store)
        elif args.command == "start":
            store.start(args.task, args.minutes)
            status(store)
        elif args.command == "snooze":
            store.snooze(args.minutes)
            status(store)
        elif args.command == "done":
            store.finish()
            print("Done. No reminders scheduled.")
        elif args.command == "worker":
            store.notify_due(notify_mac, model=ask_model)
        elif args.command == "notify-test":
            notify_mac({"task": "Buddy is ready. Click to open the conversation.",
                        "notification": str(uuid.uuid4())}, store.root)
            print("Test notification sent to macOS. Click it to open Buddy.")
    except (ValueError, OSError, sqlite3.Error, subprocess.TimeoutExpired) as error:
        print("Buddy: " + clean(str(error)), file=sys.stderr)
        return 1
    finally:
        store.db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

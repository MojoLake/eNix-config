import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

import tomlkit

sys.dont_write_bytecode = True


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


configure = load("configure")
notify = load("notify")


class NotificationsTest(unittest.TestCase):
    def test_merge_preserves_settings_callback_comments_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            (home / ".codex").mkdir()
            (home / ".claude").mkdir()
            codex = home / ".codex/config.toml"
            original = '# Keep this comment\nnotify = ["/old helper", "turn-ended"]\nmodel = "my-model"\n'
            codex.write_text(original)
            claude = home / ".claude/settings.json"
            claude.write_text(json.dumps({"theme": "light", "hooks": {"Stop": [
                {"hooks": [{"type": "command", "command": "existing-hook"}]}]}}))
            command = str(home / ".local/bin/agent-notify")
            settings = {"projects": {str(home): {"trust_level": "trusted"}}}
            configure.configure(home, command, settings)
            first = (codex.read_text(), claude.read_text())
            configure.configure(home, command, settings)
            self.assertEqual(first, (codex.read_text(), claude.read_text()))
            parsed = tomlkit.parse(codex.read_text())
            self.assertEqual(parsed["model"], "my-model")
            self.assertEqual(parsed["notify"], [command, "codex"])
            self.assertIn("# Keep this comment", codex.read_text())
            self.assertEqual(codex.with_name("config.toml.pre-agent-notify").read_text(), original)
            saved = home / ".local/state/agent-notify/codex-notify.json"
            self.assertEqual(json.loads(saved.read_text()), ["/old helper", "turn-ended"])
            parsed = json.loads(claude.read_text())
            self.assertEqual(parsed["theme"], "light")
            self.assertEqual(len(parsed["hooks"]["Stop"]), 2)
            self.assertEqual(parsed["hooks"]["Stop"][0]["hooks"][0]["command"], "existing-hook")

    def test_current_and_older_codex_database_and_fallback(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(notify.os.environ, {"CODEX_HOME": temporary}):
            path = Path(temporary) / "state_5.sqlite"
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE threads (id TEXT, title TEXT, name TEXT)")
                db.execute("INSERT INTO threads VALUES (?, ?, ?)", ("session", "hi", "Respond to greeting"))
            self.assertEqual(notify.codex_title("session"), "Respond to greeting")
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("ALTER TABLE threads DROP COLUMN name")
            self.assertEqual(notify.codex_title("session"), "hi")
            self.assertEqual(notify.label("codex", {"thread-id": "unknown", "cwd": "/work/project"}), "Codex · project")

    def test_claude_renamed_session(self):
        with tempfile.TemporaryDirectory() as temporary:
            transcript = Path(temporary) / "session.jsonl"
            transcript.write_text('invalid line\n' + json.dumps({"type": "custom-title", "customTitle": "Debug router"}) + "\n")
            self.assertEqual(notify.claude_title({"transcript_path": str(transcript)}), "Debug router")

    def test_titles_are_data_not_lua_or_shell_code(self):
        malicious = 'Quotes " and $(touch /tmp/unwanted)'
        with patch.object(notify.sys, "argv", ["notify.py", "pi", json.dumps({"title": malicious})]), \
             patch.object(notify, "terminal_context", return_value=None), \
             patch.object(notify, "send_to_hammerspoon") as send:
            notify.main()
            self.assertEqual(send.call_args.args[0]["title"], "Pi · " + malicious)
            self.assertEqual(send.call_args.kwargs, {"capture": False})

    def test_bridge_uses_private_json_and_cleans_it_up(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(notify, "HOME", Path(temporary)):
            data = {"title": 'Unicode α and "quotes"', "id": "0" * 32}
            paths = []
            def run(args, **kwargs):
                path = next((Path(temporary) / ".local/state/agent-notify").glob("*.json"))
                paths.append(path)
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(json.loads(path.read_text()), data)
                self.assertNotIn(data["title"], args[-1])
                self.assertNotIn("shell", kwargs)
                return type("Result", (), {"returncode": 0, "stdout": "AGENT_NOTIFY_OK", "stderr": ""})()
            with patch.object(notify.subprocess, "run", side_effect=run):
                notify.send_to_hammerspoon(data)
            self.assertFalse(paths[0].exists())

    def test_terminal_ancestor_not_inherited_environment(self):
        result = type("Result", (), {"stdout": "10 20 /bin/sh\n20 30 /bin/claude\n30 1 /Applications/Ghostty.app/Contents/MacOS/ghostty\n"})()
        with patch.object(notify.os, "getppid", return_value=10), \
             patch.object(notify.subprocess, "run", return_value=result):
            self.assertEqual(notify.terminal_context(), {"bundle": "com.mitchellh.ghostty", "pid": 30})
            result.stdout = "10 1 /Applications/ChatGPT.app/Contents/MacOS/ChatGPT\n"
            self.assertIsNone(notify.terminal_context())

    def test_capture_and_completion_have_same_session_identity(self):
        event = {"session_id": "session", "cwd": "/work/a"}
        with patch.object(notify, "terminal_context", return_value=None):
            capture = notify.payload("pi", event)
            event.update({"title": "New title", "cwd": "/work/b"})
            self.assertEqual(capture["id"], notify.payload("pi", event)["id"])

    def test_original_callback_receives_exact_event(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(notify, "HOME", Path(temporary)):
            path = Path(temporary) / ".local/state/agent-notify/codex-notify.json"
            path.parent.mkdir(parents=True)
            path.write_text('["/helper with spaces", "turn-ended"]')
            raw = '{"type":"agent-turn-complete","thread-id":"example"}'
            with patch.object(notify.subprocess, "run") as run:
                notify.forward_codex(raw)
                self.assertEqual(run.call_args.args[0], ["/helper with spaces", "turn-ended", raw])


if __name__ == "__main__":
    unittest.main()

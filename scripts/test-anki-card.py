#!/usr/bin/env python3
# pyright: reportUninitializedInstanceVariable=false
"""Integration tests for anki-card using disposable collections."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from anki.collection import Collection


SCRIPT = Path(__file__).with_name("anki-card.py")


class FakeAnkiConnectHandler(BaseHTTPRequestHandler):
    actions: list[str] = []

    def do_POST(self) -> None:
        size = int(self.headers["Content-Length"])
        request = json.loads(self.rfile.read(size))
        action = request["action"]
        type(self).actions.append(action)
        responses: dict[str, Any] = {
            "version": 6,
            "getActiveProfile": "User 1",
            "deckNames": ["Default"],
            "modelNames": ["Basic"],
            "modelFieldNames": ["Front", "Back"],
            "canAddNotesWithErrorDetail": [{"canAdd": True}],
            "addNotes": [123456789],
            "sync": None,
        }
        result = responses[action]
        encoded = json.dumps({"result": result, "error": None}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        pass


class AnkiCardIntegrationTests(unittest.TestCase):
    temporary: tempfile.TemporaryDirectory[str]
    root: Path
    base: Path
    profile: Path
    environment: dict[str, str]

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="anki-card-test-")
        self.root = Path(self.temporary.name)
        self.base = self.root / "Anki2"
        self.profile = self.base / "User 1"
        self.profile.mkdir(parents=True)
        col = Collection(str(self.profile / "collection.anki2"))
        col.close()
        self.environment = os.environ.copy()
        self.environment["XDG_STATE_HOME"] = str(self.root / "state")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(
        self,
        *arguments: str,
        payload: dict[str, Any] | None = None,
        connect_url: str = "http://127.0.0.1:1",
        expected_code: int = 0,
    ) -> dict[str, Any]:
        process = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--anki-base",
                str(self.base),
                "--connect-url",
                connect_url,
                "--connect-timeout",
                "0.05",
                *arguments,
            ],
            input=json.dumps(payload) if payload is not None else None,
            text=True,
            capture_output=True,
            env=self.environment,
            check=False,
        )
        self.assertEqual(
            process.returncode,
            expected_code,
            msg=f"stdout={process.stdout}\nstderr={process.stderr}",
        )
        output = process.stdout if expected_code == 0 else process.stderr
        return json.loads(output)

    @staticmethod
    def payload(request_id: str = "test-request") -> dict[str, Any]:
        return {
            "request_id": request_id,
            "notes": [
                {
                    "deck": "Default",
                    "note_type": "Basic",
                    "fields": {"Front": "Question", "Back": "Answer"},
                }
            ],
        }

    def test_headless_add_is_idempotent_and_undoable(self) -> None:
        first = self.run_cli("add", payload=self.payload())
        self.assertEqual(first["route"], "backend")
        self.assertEqual(first["added"], 1)
        self.assertFalse(first["alreadyApplied"])
        self.assertTrue(first["backupCreated"])

        repeated = self.run_cli("add", payload=self.payload())
        self.assertEqual(repeated["added"], 0)
        self.assertTrue(repeated["alreadyApplied"])
        self.assertEqual(repeated["noteIds"], first["noteIds"])

        inspected = self.run_cli("get", str(first["noteIds"][0]))
        self.assertEqual(inspected["notes"][0]["fields"]["Front"], "Question")

        duplicate = self.run_cli(
            "add",
            payload=self.payload("different-request"),
            expected_code=1,
        )
        self.assertIn("duplicate", duplicate["error"])

        undone = self.run_cli("undo", "test-request")
        self.assertEqual(undone["deleted"], 1)
        repeated_undo = self.run_cli("undo", "test-request")
        self.assertTrue(repeated_undo["alreadyUndone"])

        col = Collection(str(self.profile / "collection.anki2"))
        try:
            self.assertEqual(col.note_count(), 0)
        finally:
            col.close()

    def test_schema_uses_disposable_backend(self) -> None:
        result = self.run_cli("schema")
        self.assertEqual(result["route"], "backend")
        self.assertIn("Default", result["decks"])
        basic = next(item for item in result["noteTypes"] if item["name"] == "Basic")
        self.assertEqual(basic["fields"], ["Front", "Back"])

    def test_batch_validation_happens_before_any_note_is_added(self) -> None:
        payload = {
            "request_id": "invalid-batch",
            "notes": [
                {
                    "deck": "Default",
                    "note_type": "Basic",
                    "fields": {"Front": "Repeated", "Back": "First"},
                },
                {
                    "deck": "Default",
                    "note_type": "Basic",
                    "fields": {"Front": "Repeated", "Back": "Second"},
                },
            ],
        }
        result = self.run_cli("add", payload=payload, expected_code=1)
        self.assertIn("duplicates an earlier note", result["error"])
        col = Collection(str(self.profile / "collection.anki2"))
        try:
            self.assertEqual(col.note_count(), 0)
        finally:
            col.close()

    def test_undo_refuses_to_delete_an_edited_note(self) -> None:
        added = self.run_cli("add", payload=self.payload("edited-request"))
        note_id = added["noteIds"][0]
        col = Collection(str(self.profile / "collection.anki2"))
        try:
            note = col.get_note(note_id)
            note["Back"] = "Manually edited"
            col.update_note(note)
        finally:
            col.close()
        result = self.run_cli("undo", "edited-request", expected_code=1)
        self.assertIn("edited after creation", result["error"])
        col = Collection(str(self.profile / "collection.anki2"))
        try:
            self.assertEqual(col.get_note(note_id)["Back"], "Manually edited")
        finally:
            col.close()

    def test_refuses_backend_access_while_collection_is_open(self) -> None:
        col = Collection(str(self.profile / "collection.anki2"))
        try:
            status = self.run_cli("status")
            self.assertTrue(status["busyProfiles"]["User 1"])
            result = self.run_cli("schema", expected_code=1)
        finally:
            col.close()
        self.assertIn("open in another process", result["error"])

    def test_uses_ankiconnect_when_available(self) -> None:
        FakeAnkiConnectHandler.actions = []
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeAnkiConnectHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            payload = self.payload("connect-request")
            payload["sync"] = True
            result = self.run_cli(
                "add",
                payload=payload,
                connect_url=f"http://127.0.0.1:{server.server_port}",
            )
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertEqual(result["route"], "ankiconnect")
        self.assertEqual(result["noteIds"], [123456789])
        self.assertEqual(
            FakeAnkiConnectHandler.actions,
            [
                "version",
                "getActiveProfile",
                "sync",
                "deckNames",
                "modelNames",
                "modelFieldNames",
                "canAddNotesWithErrorDetail",
                "addNotes",
                "sync",
            ],
        )


if __name__ == "__main__":
    unittest.main()

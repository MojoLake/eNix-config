#!/usr/bin/env python3
"""Tests for the local Kindle mail MCP server without sending real email."""

from __future__ import annotations

import importlib.util
import argparse
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("kindle-mail.py")
SPEC = importlib.util.spec_from_file_location("kindle_mail", SCRIPT)
assert SPEC and SPEC.loader
kindle_mail = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(kindle_mail)


class KindleMailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config_path = self.root / "config.json"
        self.state_home = self.root / "state"
        self.config = {
            "kindle_email": "reader_abc@kindle.com",
            "from_email": "sender@example.com",
            "transport": "resend",
            "max_attachment_bytes": 1024 * 1024,
        }
        self.config_path.write_text(json.dumps(self.config), encoding="utf-8")
        self.env = patch.dict(
            os.environ,
            {
                "KINDLE_MAIL_CONFIG": str(self.config_path),
                "XDG_STATE_HOME": str(self.state_home),
            },
            clear=False,
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def make_pdf(self, name: str = "paper.pdf") -> Path:
        path = self.root / name
        path.write_bytes(b"%PDF-1.7\nminimal test document\n%%EOF\n")
        return path

    def make_epub(self) -> Path:
        path = self.root / "book.epub"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED
            )
            archive.writestr("META-INF/container.xml", "<container/>")
        return path

    def test_load_config_and_mask_destination(self) -> None:
        cfg = kindle_mail.load_config()
        self.assertEqual(cfg["kindle_email"], "reader_abc@kindle.com")
        self.assertEqual(kindle_mail.mask_email(cfg["kindle_email"]), "re********@kindle.com")

    def test_preview_validates_pdf_and_epub(self) -> None:
        cfg = kindle_mail.load_config()
        pdf = kindle_mail.delivery_preview(
            {"file_path": str(self.make_pdf()), "title": "  A   Paper  "}, cfg
        )
        self.assertEqual(pdf["mimeType"], "application/pdf")
        self.assertEqual(pdf["subject"], "A Paper")
        epub = kindle_mail.delivery_preview({"file_path": str(self.make_epub())}, cfg)
        self.assertEqual(epub["mimeType"], "application/epub+zip")

    def test_preview_rejects_disguised_and_unsupported_files(self) -> None:
        cfg = kindle_mail.load_config()
        fake = self.root / "fake.pdf"
        fake.write_text("not a PDF", encoding="utf-8")
        with self.assertRaisesRegex(kindle_mail.KindleMailError, "PDF signature"):
            kindle_mail.delivery_preview({"file_path": str(fake)}, cfg)
        text = self.root / "notes.txt"
        text.write_text("hello", encoding="utf-8")
        with self.assertRaisesRegex(kindle_mail.KindleMailError, "only PDF and EPUB"):
            kindle_mail.delivery_preview({"file_path": str(text)}, cfg)

    def test_send_uses_fixed_recipient_and_is_idempotent(self) -> None:
        cfg = kindle_mail.load_config()
        args = {
            "file_path": str(self.make_pdf()),
            "title": "Test paper",
            "request_id": "paper:test-1",
        }
        with patch.object(
            kindle_mail, "resend_send", return_value="resend-message-123"
        ) as send:
            first = kindle_mail.send_delivery(args, cfg)
            second = kindle_mail.send_delivery(args, cfg)
        self.assertFalse(first["alreadySent"])
        self.assertTrue(second["alreadySent"])
        self.assertEqual(first["providerMessageId"], "resend-message-123")
        self.assertEqual(send.call_count, 1)
        preview, sent_cfg, request_id = send.call_args.args
        self.assertEqual(preview["subject"], "Test paper")
        self.assertEqual(sent_cfg["kindle_email"], "reader_abc@kindle.com")
        self.assertEqual(request_id, "paper:test-1")

    def test_resend_send_uses_fixed_recipient_attachment_and_idempotency(self) -> None:
        cfg = kindle_mail.load_config()
        preview = kindle_mail.delivery_preview(
            {"file_path": str(self.make_pdf()), "title": "Test paper"}, cfg
        )
        with (
            patch.object(kindle_mail, "load_resend_api_key", return_value="re_test"),
            patch.object(
                kindle_mail, "request_json", return_value={"id": "resend-message-123"}
            ) as request,
        ):
            message_id = kindle_mail.resend_send(preview, cfg, "paper:test-1")
        self.assertEqual(message_id, "resend-message-123")
        body = request.call_args.kwargs["body"]
        headers = request.call_args.kwargs["headers"]
        self.assertEqual(body["from"], "sender@example.com")
        self.assertEqual(body["to"], ["reader_abc@kindle.com"])
        self.assertEqual(body["subject"], "Test paper")
        self.assertEqual(body["attachments"][0]["filename"], "paper.pdf")
        self.assertTrue(body["attachments"][0]["content"])
        self.assertEqual(headers["Authorization"], "Bearer re_test")
        self.assertEqual(headers["Idempotency-Key"], "paper:test-1")

    def test_setup_status_requires_resend_key(self) -> None:
        with patch.object(
            kindle_mail,
            "load_resend_api_key",
            side_effect=kindle_mail.KindleMailError("API key missing"),
        ):
            missing = kindle_mail.setup_status()
        self.assertFalse(missing["configured"])
        self.assertIn("API key missing", missing["problem"])
        with patch.object(kindle_mail, "load_resend_api_key", return_value="re_test"):
            ready = kindle_mail.setup_status()
        self.assertTrue(ready["configured"])
        self.assertEqual(ready["authMethod"], "resend-api-key")
        self.assertEqual(ready["provider"], "resend")

    def test_store_resend_api_key_rejects_wrong_format(self) -> None:
        with self.assertRaisesRegex(kindle_mail.KindleMailError, "beginning with `re_`"):
            kindle_mail.store_resend_api_key("sender@example.com", "not-a-key")

    def test_setup_preserves_kindle_address_and_never_writes_api_key(self) -> None:
        args = argparse.Namespace(
            kindle_email=None,
            from_email="documents@kindle.example.com",
            max_bytes=1024 * 1024,
        )
        with (
            patch.object(kindle_mail.getpass, "getpass", return_value="re_secret"),
            patch.object(kindle_mail, "store_resend_api_key") as store,
            patch.object(kindle_mail, "secret_tool"),
        ):
            kindle_mail.configure_resend(args)
        stored = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(stored["kindle_email"], "reader_abc@kindle.com")
        self.assertEqual(stored["from_email"], "documents@kindle.example.com")
        self.assertEqual(stored["transport"], "resend")
        self.assertNotIn("api_key", stored)
        self.assertNotIn("re_secret", self.config_path.read_text(encoding="utf-8"))
        store.assert_called_once_with("documents@kindle.example.com", "re_secret")

    def test_tool_metadata_marks_only_send_as_write(self) -> None:
        tools = {tool["name"]: tool for tool in kindle_mail.tool_definitions()}
        self.assertTrue(tools["check_kindle_mail_setup"]["annotations"]["readOnlyHint"])
        self.assertTrue(tools["preview_kindle_delivery"]["annotations"]["readOnlyHint"])
        self.assertFalse(tools["send_to_kindle"]["annotations"]["readOnlyHint"])

    def test_mcp_initialize_and_list(self) -> None:
        initialized = kindle_mail.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-06-18"},
            }
        )
        assert initialized
        self.assertEqual(initialized["result"]["serverInfo"]["name"], "kindle-mail")
        listed = kindle_mail.handle_request(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        )
        assert listed
        names = {tool["name"] for tool in listed["result"]["tools"]}
        self.assertEqual(
            names,
            {"check_kindle_mail_setup", "preview_kindle_delivery", "send_to_kindle"},
        )


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""A narrowly scoped MCP server and setup utility for Send to Kindle email."""

from __future__ import annotations

import argparse
import base64
import fcntl
import getpass
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path
from typing import Any


SERVER_NAME = "kindle-mail"
SERVER_VERSION = "3.0.0"
DEFAULT_FROM_EMAIL = "documents@kindle.elias.simojoki.dev"
DEFAULT_MAX_BYTES = 18 * 1024 * 1024
RESEND_EMAILS_URL = "https://api.resend.com/emails"
RESEND_SECRET_SERVICE = "kindle-mail-resend"
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class KindleMailError(Exception):
    """An expected error safe to return to the MCP client."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def config_path() -> Path:
    if value := os.environ.get("KINDLE_MAIL_CONFIG"):
        return Path(value).expanduser()
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return config_home / "kindle-mail" / "config.json"


def state_directory() -> Path:
    state_home = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    path = state_home / "kindle-mail"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def validate_email(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise KindleMailError(f"{field} must be one email address")
    display_name, address = parseaddr(value)
    if display_name or address != value or address.count("@") != 1:
        raise KindleMailError(f"{field} must be one bare email address")
    local, domain = address.rsplit("@", 1)
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise KindleMailError(f"{field} is not a valid email address")
    return address


def load_config(path: Path | None = None) -> dict[str, Any]:
    path = path or config_path()
    if not path.is_file():
        raise KindleMailError(
            f"configuration is missing at {path}; run `kindle-mail setup`"
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KindleMailError(f"cannot read configuration at {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise KindleMailError("configuration must contain a JSON object")

    kindle_email = validate_email(raw.get("kindle_email"), "kindle_email")
    from_email = validate_email(raw.get("from_email"), "from_email")
    if raw.get("transport") != "resend":
        raise KindleMailError(
            "Resend is not configured; run `kindle-mail setup-resend`"
        )
    max_bytes = raw.get("max_attachment_bytes", DEFAULT_MAX_BYTES)
    if not isinstance(max_bytes, int) or not 1 <= max_bytes <= 50 * 1024 * 1024:
        raise KindleMailError("max_attachment_bytes must be between 1 and 52428800")
    return {
        "kindle_email": kindle_email,
        "from_email": from_email,
        "transport": "resend",
        "max_attachment_bytes": max_bytes,
    }


def sanitize_title(value: Any, fallback: str) -> str:
    if value is None or value == "":
        value = fallback
    if not isinstance(value, str):
        raise KindleMailError("title must be a string")
    value = " ".join(value.split())
    if not value or len(value) > 200:
        raise KindleMailError("title must contain between 1 and 200 characters")
    return value


def inspect_attachment(
    file_path: Any, title: Any, max_bytes: int
) -> tuple[Path, str, str, str, int]:
    if not isinstance(file_path, str) or not file_path:
        raise KindleMailError("file_path must be a non-empty absolute path")
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        raise KindleMailError("file_path must be absolute")
    try:
        resolved = path.resolve(strict=True)
        stat = resolved.stat()
    except OSError as exc:
        raise KindleMailError(f"cannot access attachment: {exc}") from exc
    if not resolved.is_file():
        raise KindleMailError("attachment must be a regular file")
    if stat.st_size <= 0:
        raise KindleMailError("attachment is empty")
    if stat.st_size > max_bytes:
        raise KindleMailError(
            f"attachment is {stat.st_size} bytes; configured limit is {max_bytes}"
        )

    suffix = resolved.suffix.lower()
    try:
        if suffix == ".pdf":
            with resolved.open("rb") as handle:
                if handle.read(5) != b"%PDF-":
                    raise KindleMailError("attachment has a .pdf suffix but no PDF signature")
            mime_type = "application/pdf"
        elif suffix == ".epub":
            with zipfile.ZipFile(resolved) as archive:
                if archive.read("mimetype") != b"application/epub+zip":
                    raise KindleMailError("attachment is not a valid EPUB archive")
            mime_type = "application/epub+zip"
        else:
            raise KindleMailError("only PDF and EPUB attachments are allowed")
    except (OSError, KeyError, zipfile.BadZipFile) as exc:
        raise KindleMailError(f"invalid {suffix or 'attachment'} file: {exc}") from exc

    digest = hashlib.sha256()
    try:
        with resolved.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise KindleMailError(f"cannot hash attachment: {exc}") from exc
    clean_title = sanitize_title(title, resolved.stem)
    return resolved, clean_title, mime_type, digest.hexdigest(), stat.st_size


def mask_email(address: str) -> str:
    local, domain = address.rsplit("@", 1)
    shown = local[:2] if len(local) > 2 else local[:1]
    return f"{shown}{'*' * max(3, len(local) - len(shown))}@{domain}"


def delivery_preview(args: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    path, title, mime_type, sha256, size = inspect_attachment(
        args.get("file_path"), args.get("title"), cfg["max_attachment_bytes"]
    )
    return {
        "attachment": str(path),
        "filename": path.name,
        "from": cfg["from_email"],
        "mimeType": mime_type,
        "sha256": sha256,
        "sizeBytes": size,
        "subject": title,
        "to": mask_email(cfg["kindle_email"]),
    }


def receipt_path() -> Path:
    return state_directory() / "sent.jsonl"


def find_receipt(request_id: str) -> dict[str, Any] | None:
    path = receipt_path()
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                event = json.loads(line)
                if event.get("requestId") == request_id:
                    return event
    except (OSError, json.JSONDecodeError) as exc:
        raise KindleMailError(f"cannot read delivery receipts: {exc}") from exc
    return None


def append_receipt(event: dict[str, Any]) -> None:
    path = receipt_path()
    encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.write(encoded + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def secret_tool(*args: str, input_value: str | None = None) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["secret-tool", *args],
            input=input_value,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise KindleMailError(f"cannot access Secret Service: {exc}") from exc


def load_resend_api_key(from_email: str) -> str:
    completed = secret_tool(
        "lookup", "service", RESEND_SECRET_SERVICE, "account", from_email
    )
    api_key = completed.stdout.strip()
    if completed.returncode != 0 or not api_key:
        raise KindleMailError(
            "Resend API key is missing; run `kindle-mail setup-resend`"
        )
    if not api_key.startswith("re_"):
        raise KindleMailError(
            "stored Resend API key has an unexpected format; run `kindle-mail setup-resend`"
        )
    return api_key


def store_resend_api_key(from_email: str, api_key: str) -> None:
    api_key = api_key.strip()
    if not api_key.startswith("re_") or any(char.isspace() for char in api_key):
        raise KindleMailError("Resend API key must be a single value beginning with `re_`")
    completed = secret_tool(
        "store",
        f"--label=Kindle mail Resend API key ({from_email})",
        "service",
        RESEND_SECRET_SERVICE,
        "account",
        from_email,
        input_value=api_key + "\n",
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip()
        raise KindleMailError(f"could not store Resend API key: {detail or 'no details'}")


def request_json(
    url: str,
    *,
    body: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any]:
    payload = json.dumps(body, separators=(",", ":")).encode()
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": f"kindle-mail/{SERVER_VERSION}",
        **headers,
    }
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            result = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read(8192).decode(errors="replace")
        try:
            error = json.loads(raw)
            if not isinstance(error, dict):
                raise TypeError
            nested = error.get("error")
            nested_message = nested.get("message") if isinstance(nested, dict) else None
            detail = error.get("message") or error.get("error_description") or nested_message
            if not isinstance(detail, str):
                detail = str(nested or "request rejected")
        except (json.JSONDecodeError, TypeError):
            detail = raw.strip() or exc.reason
        raise KindleMailError(f"Resend rejected the request ({exc.code}): {detail}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise KindleMailError(f"Resend API request failed: {exc}") from exc
    if not isinstance(result, dict):
        raise KindleMailError("Resend returned an unexpected response")
    return result


def resend_send(
    preview: dict[str, Any], cfg: dict[str, Any], request_id: str
) -> str:
    try:
        attachment = Path(preview["attachment"]).read_bytes()
    except OSError as exc:
        raise KindleMailError(f"cannot read attachment for delivery: {exc}") from exc
    result = request_json(
        RESEND_EMAILS_URL,
        body={
            "from": cfg["from_email"],
            "to": [cfg["kindle_email"]],
            "subject": preview["subject"],
            "text": "Document sent to Kindle by the local kindle-mail tool.\n",
            "attachments": [
                {
                    "filename": preview["filename"],
                    "content": base64.b64encode(attachment).decode(),
                }
            ],
        },
        headers={
            "Authorization": f"Bearer {load_resend_api_key(cfg['from_email'])}",
            "Idempotency-Key": request_id,
        },
    )
    message_id = result.get("id")
    if not isinstance(message_id, str) or not message_id:
        raise KindleMailError("Resend accepted the request but returned no message ID")
    return message_id


def send_delivery(args: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    request_id = args.get("request_id")
    if not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id):
        raise KindleMailError(
            "request_id must be 1-128 letters, digits, dots, underscores, colons, or hyphens"
        )
    lock_path = state_directory() / "send.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        os.fchmod(lock.fileno(), 0o600)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if existing := find_receipt(request_id):
            return {"alreadySent": True, **existing}

        preview = delivery_preview(args, cfg)
        provider_message_id = resend_send(preview, cfg, request_id)

        event = {
            "event": "sent",
            "filename": preview["filename"],
            "providerMessageId": provider_message_id,
            "requestId": request_id,
            "sha256": preview["sha256"],
            "sentAt": utc_now(),
            "sizeBytes": preview["sizeBytes"],
            "subject": preview["subject"],
            "to": preview["to"],
        }
        append_receipt(event)
        return {"alreadySent": False, **event}


def setup_status() -> dict[str, Any]:
    path = config_path()
    result: dict[str, Any] = {"configPath": str(path), "configured": False}
    try:
        cfg = load_config(path)
    except KindleMailError as exc:
        result["problem"] = str(exc)
        return result
    result.update(
        {
            "authMethod": "resend-api-key",
            "from": cfg["from_email"],
            "maxAttachmentBytes": cfg["max_attachment_bytes"],
            "provider": "resend",
            "to": mask_email(cfg["kindle_email"]),
        }
    )
    try:
        load_resend_api_key(cfg["from_email"])
    except KindleMailError as exc:
        result["problem"] = str(exc)
        return result
    result["configured"] = True
    return result


def tool_definitions() -> list[dict[str, Any]]:
    file_properties = {
        "file_path": {
            "type": "string",
            "description": "Absolute path to a local PDF or EPUB file.",
        },
        "title": {
            "type": "string",
            "description": "Optional Kindle document title and email subject.",
            "maxLength": 200,
        },
    }
    return [
        {
            "name": "check_kindle_mail_setup",
            "description": "Check whether local Kindle email delivery is configured. Does not send email or verify credentials.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "annotations": {"readOnlyHint": True, "openWorldHint": False},
        },
        {
            "name": "preview_kindle_delivery",
            "description": "Validate a local PDF or EPUB and preview its fixed-address Kindle delivery without sending it.",
            "inputSchema": {
                "type": "object",
                "properties": file_properties,
                "required": ["file_path"],
                "additionalProperties": False,
            },
            "annotations": {"readOnlyHint": True, "openWorldHint": False},
        },
        {
            "name": "send_to_kindle",
            "description": "Email one validated local PDF or EPUB to Elias's fixed Send-to-Kindle address. This is an external write and requires approval.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    **file_properties,
                    "request_id": {
                        "type": "string",
                        "description": "Stable unique identifier reused for safe retries.",
                        "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
                    },
                },
                "required": ["file_path", "request_id"],
                "additionalProperties": False,
            },
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            },
        },
    ]


def text_result(value: Any, *, is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True),
            }
        ],
        "isError": is_error,
    }


def call_tool(name: Any, args: Any) -> dict[str, Any]:
    if not isinstance(args, dict):
        return text_result({"error": "tool arguments must be an object"}, is_error=True)
    try:
        if name == "check_kindle_mail_setup":
            return text_result(setup_status())
        cfg = load_config()
        if name == "preview_kindle_delivery":
            return text_result(delivery_preview(args, cfg))
        if name == "send_to_kindle":
            return text_result(send_delivery(args, cfg))
        raise KindleMailError(f"unknown tool: {name}")
    except KindleMailError as exc:
        return text_result({"error": str(exc)}, is_error=True)


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if request_id is None:
        return None
    if method == "initialize":
        requested = message.get("params", {}).get("protocolVersion", "2025-06-18")
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": requested,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": (
                    "This server only delivers validated PDF or EPUB files to Elias's fixed "
                    "Kindle address. Preview first. Sending is an external write; use a stable "
                    "request_id and obtain approval immediately before send_to_kindle."
                ),
            },
        }
    if method == "ping":
        result: Any = {}
    elif method == "tools/list":
        result = {"tools": tool_definitions()}
    elif method == "tools/call":
        params = message.get("params", {})
        result = call_tool(params.get("name"), params.get("arguments", {}))
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"method not found: {method}"},
        }
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def serve_mcp() -> int:
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                raise ValueError("message must be an object")
            response = handle_request(message)
            if response is not None:
                sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
                sys.stdout.flush()
        except (json.JSONDecodeError, ValueError) as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"parse error: {exc}"},
            }
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
        except Exception as exc:  # Keep protocol output valid on unexpected failures.
            print(f"{SERVER_NAME}: unexpected error: {exc}", file=sys.stderr)
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id") if isinstance(message, dict) else None,
                "error": {"code": -32603, "message": "internal server error"},
            }
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


def read_existing_value(key: str) -> Any:
    try:
        raw = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw.get(key) if isinstance(raw, dict) else None


def write_config(cfg: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    encoded = json.dumps(cfg, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    print(f"Wrote {path}")


def configure_resend(args: argparse.Namespace) -> int:
    existing_kindle = read_existing_value("kindle_email")
    existing_from = read_existing_value("from_email")
    kindle_email = args.kindle_email or existing_kindle
    if not kindle_email:
        kindle_email = input("Send-to-Kindle email address: ").strip()
    if not 1 <= args.max_bytes <= 50 * 1024 * 1024:
        raise KindleMailError("max-bytes must be between 1 and 52428800")
    cfg = {
        "kindle_email": validate_email(kindle_email, "kindle_email"),
        "from_email": validate_email(args.from_email, "from_email"),
        "transport": "resend",
        "max_attachment_bytes": args.max_bytes,
    }
    api_key = getpass.getpass(
        f"Resend API key for {cfg['from_email']} (stored in Secret Service): "
    )
    store_resend_api_key(cfg["from_email"], api_key)
    write_config(cfg)
    if isinstance(existing_from, str):
        secret_tool(
            "clear", "service", "kindle-mail-oauth", "account", existing_from
        )
        secret_tool(
            "clear", "service", "kindle-mail-smtp", "account", existing_from
        )
    print("Stored the Resend API key in Secret Service.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="kindle-mail")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("mcp", help="run the stdio MCP server")
    subparsers.add_parser("check", help="show non-secret setup status")
    setup = subparsers.add_parser(
        "setup-resend",
        help="configure Kindle delivery and securely store a Resend API key",
    )
    setup.add_argument("--kindle-email")
    setup.add_argument("--from-email", default=DEFAULT_FROM_EMAIL)
    setup.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()
    try:
        if args.command == "mcp":
            return serve_mcp()
        if args.command == "check":
            status = setup_status()
            print(json.dumps(status, indent=2, sort_keys=True))
            return 0 if status["configured"] else 1
        if args.command == "setup-resend":
            return configure_resend(args)
    except KindleMailError as exc:
        print(f"kindle-mail: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

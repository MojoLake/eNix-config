#!/usr/bin/env python3
"""Safe, GUI-optional command-line access to a local Anki collection."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pickle
import re
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import anki.lang
from anki import notes_pb2
from anki.collection import AddNoteRequest, Collection
from anki.notes import NoteId
from anki.sync import SyncAuth
from anki.utils import field_checksum


API_VERSION = 6
DEFAULT_CONNECT_URL = "http://127.0.0.1:8765"
MAX_INPUT_BYTES = 10 * 1024 * 1024
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")

# Some legacy helpers used by Anki's duplicate detection expect the GUI to have
# initialized this global. Command-line users need to do so themselves.
anki.lang.set_lang("en_US")


class AnkiCardError(Exception):
    """An expected error that should be reported without a traceback."""


class AddedButUnsyncedError(AnkiCardError):
    """The mutation succeeded, but its requested post-add sync failed."""

    def __init__(self, result: dict[str, Any], reason: str) -> None:
        super().__init__(reason)
        self.result = result


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def emit(value: Any, *, stream: Any = sys.stdout) -> None:
    json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
    stream.write("\n")


def state_directory() -> Path:
    root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    path = root / "anki-card"
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


@contextmanager
def exclusive_lock() -> Iterator[None]:
    path = state_directory() / "lock"
    with path.open("a+", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield


class ReceiptLog:
    def __init__(self) -> None:
        self.path = state_directory() / "events.jsonl"

    def events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        with self.path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AnkiCardError(
                        f"receipt log is corrupt at line {line_number}: {exc}"
                    ) from exc
                if not isinstance(event, dict):
                    raise AnkiCardError(
                        f"receipt log is corrupt at line {line_number}: expected an object"
                    )
                events.append(event)
        return events

    def append(self, event: dict[str, Any]) -> None:
        encoded = json.dumps(
            event, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        )
        fd = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def request_state(self, request_id: str) -> dict[str, Any] | None:
        state: dict[str, Any] | None = None
        for event in self.events():
            if event.get("requestId") != request_id:
                continue
            if event.get("event") == "add":
                state = dict(event)
                state["undone"] = False
            elif event.get("event") == "undo" and state is not None:
                state["undone"] = True
                state["undoEvent"] = event
        return state


class AnkiConnect:
    def __init__(self, url: str, timeout: float, key: str | None = None) -> None:
        self.url = url
        self.timeout = timeout
        self.key = key

    def invoke(
        self,
        action: str,
        params: dict[str, Any] | None = None,
        *,
        request_timeout: float | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "action": action,
            "version": API_VERSION,
            "params": params or {},
        }
        if self.key:
            payload["key"] = self.key
        request = Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=request_timeout or self.timeout) as response:
                body = response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise AnkiCardError(f"AnkiConnect request failed: {exc}") from exc
        try:
            decoded = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AnkiCardError("AnkiConnect returned invalid JSON") from exc
        if (
            not isinstance(decoded, dict)
            or "error" not in decoded
            or "result" not in decoded
        ):
            raise AnkiCardError("AnkiConnect returned an invalid response envelope")
        if decoded["error"] is not None:
            raise AnkiCardError(f"AnkiConnect {action} failed: {decoded['error']}")
        return decoded["result"]

    def available(self) -> bool:
        try:
            version = self.invoke("version", request_timeout=min(self.timeout, 0.5))
            return isinstance(version, int) and version >= API_VERSION
        except AnkiCardError:
            return False


def default_anki_base() -> Path:
    if value := os.environ.get("ANKI_BASE"):
        return Path(value).expanduser()
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return data_home / "Anki2"


def available_profiles(base: Path) -> list[str]:
    if not base.is_dir():
        return []
    return sorted(
        child.name
        for child in base.iterdir()
        if child.is_dir() and (child / "collection.anki2").is_file()
    )


def resolve_profile(base: Path, requested: str | None) -> str:
    profiles = available_profiles(base)
    if requested:
        if requested not in profiles:
            raise AnkiCardError(
                f"Anki profile {requested!r} was not found; available profiles: {profiles}"
            )
        return requested
    if len(profiles) == 1:
        return profiles[0]
    if not profiles:
        raise AnkiCardError(f"no Anki profiles were found below {base}")
    raise AnkiCardError(
        f"multiple Anki profiles exist; pass --profile with one of: {profiles}"
    )


def collection_path(base: Path, profile: str) -> Path:
    return base / profile / "collection.anki2"


def processes_using_collection(path: Path) -> list[int]:
    targets = {
        str(path.resolve()),
        str(Path(f"{path}-wal").resolve()),
        str(Path(f"{path}-shm").resolve()),
        str(path.with_name("collection.media.db2").resolve()),
    }
    users: list[int] = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            descriptors = (proc / "fd").iterdir()
            for descriptor in descriptors:
                try:
                    target = os.readlink(descriptor)
                except OSError:
                    continue
                if target.removesuffix(" (deleted)") in targets:
                    users.append(int(proc.name))
                    break
        except (OSError, PermissionError):
            continue
    return sorted(set(users))


def active_profile(connect: AnkiConnect) -> str:
    profile = connect.invoke("getActiveProfile")
    if not isinstance(profile, str) or not profile:
        raise AnkiCardError("AnkiConnect is running, but no Anki profile is active")
    return profile


def select_route(
    connect: AnkiConnect,
    base: Path,
    requested_profile: str | None,
    *,
    startup_wait: float = 5.0,
) -> tuple[str, str]:
    if connect.available():
        profile = active_profile(connect)
        if requested_profile and requested_profile != profile:
            raise AnkiCardError(
                f"Anki has profile {profile!r} open, not requested profile {requested_profile!r}"
            )
        return "ankiconnect", profile

    profile = resolve_profile(base, requested_profile)
    path = collection_path(base, profile)
    users = processes_using_collection(path)
    if users:
        deadline = time.monotonic() + startup_wait
        while time.monotonic() < deadline:
            time.sleep(0.25)
            if connect.available():
                active = active_profile(connect)
                if active != profile:
                    raise AnkiCardError(
                        f"Anki has profile {active!r} open, not requested profile {profile!r}"
                    )
                return "ankiconnect", active
        raise AnkiCardError(
            "the Anki collection is open in another process, but AnkiConnect is not "
            f"available (process IDs: {users}); wait for Anki to finish starting, "
            "enable AnkiConnect, or close Anki"
        )
    return "backend", profile


@contextmanager
def open_collection(base: Path, profile: str) -> Iterator[Collection]:
    path = collection_path(base, profile)
    try:
        col = Collection(str(path))
    except Exception as exc:
        raise AnkiCardError(f"could not open Anki collection {path}: {exc}") from exc
    try:
        yield col
    finally:
        col.close()


def ensure_backup(col: Collection, base: Path, profile: str) -> bool:
    backup_folder = base / profile / "backups"
    backup_folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        return col.create_backup(
            backup_folder=str(backup_folder),
            force=True,
            wait_for_completion=True,
        )
    except Exception as exc:
        raise AnkiCardError(
            f"could not create a pre-change Anki backup: {exc}"
        ) from exc


def load_profile_preferences(base: Path, profile: str) -> dict[str, Any]:
    path = base / "prefs21.db"
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as database:
            row = database.execute(
                "select data from profiles where name = ? collate nocase", (profile,)
            ).fetchone()
    except sqlite3.Error as exc:
        raise AnkiCardError(f"could not read Anki sync preferences: {exc}") from exc
    if not row:
        raise AnkiCardError(f"Anki preferences do not contain profile {profile!r}")
    try:
        preferences = pickle.loads(row[0])
    except Exception as exc:
        raise AnkiCardError(f"could not decode Anki sync preferences: {exc}") from exc
    if not isinstance(preferences, dict):
        raise AnkiCardError("Anki profile preferences have an unexpected format")
    return preferences


def backend_sync(col: Collection, base: Path, profile: str) -> dict[str, Any]:
    preferences = load_profile_preferences(base, profile)
    hkey = preferences.get("syncKey")
    if not isinstance(hkey, str) or not hkey:
        raise AnkiCardError("AnkiWeb sync is not configured for this profile")
    endpoint = preferences.get("currentSyncUrl") or preferences.get("customSyncUrl")
    auth_args: dict[str, Any] = {
        "hkey": hkey,
        "io_timeout_secs": preferences.get("networkTimeout") or 60,
    }
    if endpoint:
        auth_args["endpoint"] = endpoint
    auth = SyncAuth(**auth_args)
    try:
        result = col.sync_collection(auth, sync_media=False)
    except Exception as exc:
        raise AnkiCardError(f"AnkiWeb sync failed: {exc}") from exc
    status = result.ChangesRequired.Name(result.required)
    if status not in {"NO_CHANGES", "NORMAL_SYNC"}:
        raise AnkiCardError(
            f"AnkiWeb requires {status}; open Anki and choose the sync direction manually"
        )
    return {
        "status": status,
        "serverMessage": result.server_message or None,
        "newEndpoint": bool(result.new_endpoint),
    }


def perform_sync(
    route: str,
    connect: AnkiConnect,
    base: Path,
    profile: str,
    col: Collection | None = None,
) -> dict[str, Any]:
    if route == "ankiconnect":
        connect.invoke("sync")
        return {"status": "complete"}
    if col is None:
        raise AssertionError("backend sync requires an open collection")
    return backend_sync(col, base, profile)


def read_add_payload() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise AnkiCardError(f"input exceeds {MAX_INPUT_BYTES} bytes")
    if not raw.strip():
        raise AnkiCardError("add expects a JSON object on standard input")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnkiCardError(f"invalid JSON input: {exc}") from exc
    if not isinstance(payload, dict):
        raise AnkiCardError("input must be a JSON object")
    unknown = set(payload) - {"notes", "profile", "request_id", "sync"}
    if unknown:
        raise AnkiCardError(f"unknown top-level input keys: {sorted(unknown)}")
    notes = payload.get("notes")
    if not isinstance(notes, list) or not notes:
        raise AnkiCardError("notes must be a non-empty array")
    if len(notes) > 1000:
        raise AnkiCardError("a single request may contain at most 1000 notes")
    if "sync" in payload and not isinstance(payload["sync"], bool):
        raise AnkiCardError("sync must be true or false")
    if "profile" in payload and (
        not isinstance(payload["profile"], str) or not payload["profile"]
    ):
        raise AnkiCardError("profile must be a non-empty string")
    request_id = payload.get("request_id")
    if request_id is not None and (
        not isinstance(request_id, str) or not REQUEST_ID_RE.fullmatch(request_id)
    ):
        raise AnkiCardError(
            "request_id must be 1-128 characters using letters, numbers, '.', '_', ':' or '-'"
        )
    for index, note in enumerate(notes):
        validate_note_shape(note, index)
    return payload


def validate_note_shape(note: Any, index: int) -> None:
    label = f"notes[{index}]"
    if not isinstance(note, dict):
        raise AnkiCardError(f"{label} must be an object")
    unknown = set(note) - {"deck", "fields", "note_type", "tags"}
    if unknown:
        raise AnkiCardError(f"{label} has unknown keys: {sorted(unknown)}")
    for key in ("deck", "note_type"):
        if not isinstance(note.get(key), str) or not note[key]:
            raise AnkiCardError(f"{label}.{key} must be a non-empty string")
    fields = note.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise AnkiCardError(f"{label}.fields must be a non-empty object")
    if not all(isinstance(key, str) and key for key in fields):
        raise AnkiCardError(f"{label}.fields keys must be non-empty strings")
    if not all(isinstance(value, str) for value in fields.values()):
        raise AnkiCardError(f"{label}.fields values must be strings")
    tags = note.get("tags", [])
    if not isinstance(tags, list) or not all(
        isinstance(tag, str) and tag.strip() for tag in tags
    ):
        raise AnkiCardError(f"{label}.tags must be an array of non-empty strings")


def canonical_hash(profile: str, notes: list[dict[str, Any]]) -> str:
    encoded = json.dumps(
        {"profile": profile, "notes": notes},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def request_identity(payload: dict[str, Any], profile: str) -> tuple[str, str]:
    payload_hash = canonical_hash(profile, payload["notes"])
    request_id = payload.get("request_id") or f"sha256:{payload_hash}"
    return request_id, payload_hash


def normalise_fields(
    supplied: dict[str, str], expected: list[str], label: str
) -> dict[str, str]:
    expected_by_casefold = {name.casefold(): name for name in expected}
    normalised: dict[str, str] = {}
    for name, value in supplied.items():
        canonical = expected_by_casefold.get(name.casefold())
        if canonical is None:
            raise AnkiCardError(
                f"{label} has unknown field {name!r}; expected fields: {expected}"
            )
        if canonical in normalised:
            raise AnkiCardError(f"{label} supplies field {canonical!r} more than once")
        normalised[canonical] = value
    return {name: normalised.get(name, "") for name in expected}


def prepare_connect_notes(
    connect: AnkiConnect, notes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    decks = set(connect.invoke("deckNames"))
    models = set(connect.invoke("modelNames"))
    fields_by_model: dict[str, list[str]] = {}
    prepared: list[dict[str, Any]] = []
    for index, note in enumerate(notes):
        deck = note["deck"]
        model = note["note_type"]
        if deck not in decks:
            raise AnkiCardError(f"notes[{index}] references unknown deck {deck!r}")
        if model not in models:
            raise AnkiCardError(
                f"notes[{index}] references unknown note type {model!r}"
            )
        if model not in fields_by_model:
            fields = connect.invoke("modelFieldNames", {"modelName": model})
            if not isinstance(fields, list) or not all(
                isinstance(field, str) for field in fields
            ):
                raise AnkiCardError(
                    f"AnkiConnect returned invalid fields for note type {model!r}"
                )
            fields_by_model[model] = fields
        fields = normalise_fields(
            note["fields"], fields_by_model[model], f"notes[{index}]"
        )
        prepared.append(
            {
                "deckName": deck,
                "modelName": model,
                "fields": fields,
                "tags": list(note.get("tags", [])),
                "options": {"allowDuplicate": False},
            }
        )
    checks = connect.invoke("canAddNotesWithErrorDetail", {"notes": prepared})
    if not isinstance(checks, list) or len(checks) != len(prepared):
        raise AnkiCardError("AnkiConnect returned invalid note validation results")
    failures = [
        {"index": index, "error": check.get("error", "note was rejected")}
        for index, check in enumerate(checks)
        if not isinstance(check, dict) or not check.get("canAdd")
    ]
    if failures:
        raise AnkiCardError(f"note validation failed: {json.dumps(failures)}")
    return prepared


FIELD_CHECK_ERRORS = {
    notes_pb2.NoteFieldsCheckResponse.EMPTY: "the first field is empty",
    notes_pb2.NoteFieldsCheckResponse.DUPLICATE: "the note is a duplicate",
    notes_pb2.NoteFieldsCheckResponse.MISSING_CLOZE: "the cloze note has no cloze deletion",
    notes_pb2.NoteFieldsCheckResponse.NOTETYPE_NOT_CLOZE: "the note type is not a cloze type",
    notes_pb2.NoteFieldsCheckResponse.FIELD_NOT_CLOZE: "the cloze field is invalid",
}


def prepare_backend_notes(
    col: Collection, notes: list[dict[str, Any]]
) -> tuple[list[AddNoteRequest], list[Any], list[dict[str, Any]]]:
    requests: list[AddNoteRequest] = []
    created_notes: list[Any] = []
    canonical_notes: list[dict[str, Any]] = []
    batch_first_fields: set[tuple[int, int]] = set()
    for index, spec in enumerate(notes):
        deck = col.decks.by_name(spec["deck"])
        if deck is None:
            raise AnkiCardError(
                f"notes[{index}] references unknown deck {spec['deck']!r}"
            )
        model = col.models.by_name(spec["note_type"])
        if model is None:
            raise AnkiCardError(
                f"notes[{index}] references unknown note type {spec['note_type']!r}"
            )
        field_names = [field["name"] for field in model["flds"]]
        fields = normalise_fields(spec["fields"], field_names, f"notes[{index}]")
        note = col.new_note(model)
        for name, value in fields.items():
            note[name] = value
        note.tags = list(spec.get("tags", []))
        check = note.fields_check()
        if check != notes_pb2.NoteFieldsCheckResponse.NORMAL:
            reason = FIELD_CHECK_ERRORS.get(
                check, f"field check returned state {check}"
            )
            raise AnkiCardError(f"notes[{index}] cannot be added: {reason}")
        batch_key = (int(note.mid), field_checksum(note.fields[0]))
        if batch_key in batch_first_fields:
            raise AnkiCardError(
                f"notes[{index}] duplicates an earlier note in this request"
            )
        batch_first_fields.add(batch_key)
        requests.append(AddNoteRequest(note=note, deck_id=deck["id"]))
        created_notes.append(note)
        canonical_notes.append(
            {
                "deck": spec["deck"],
                "note_type": spec["note_type"],
                "fields": fields,
                "tags": list(spec.get("tags", [])),
            }
        )
    return requests, created_notes, canonical_notes


def add_receipt(
    *,
    request_id: str,
    payload_hash: str,
    route: str,
    profile: str,
    note_ids: list[int],
    notes: list[dict[str, Any]],
    backup_created: bool | None,
) -> dict[str, Any]:
    return {
        "event": "add",
        "version": 1,
        "createdAt": utc_now(),
        "requestId": request_id,
        "payloadHash": payload_hash,
        "route": route,
        "profile": profile,
        "noteIds": note_ids,
        "notes": notes,
        "backupCreated": backup_created,
    }


def result_from_receipt(
    receipt: dict[str, Any], *, already_applied: bool
) -> dict[str, Any]:
    return {
        "ok": True,
        "operation": "add",
        "alreadyApplied": already_applied,
        "requestId": receipt["requestId"],
        "route": receipt["route"],
        "profile": receipt["profile"],
        "noteIds": receipt["noteIds"],
        "added": 0 if already_applied else len(receipt["noteIds"]),
        "backupCreated": receipt.get("backupCreated"),
    }


def command_add(
    args: argparse.Namespace, connect: AnkiConnect, base: Path
) -> dict[str, Any]:
    payload = read_add_payload()
    input_profile = payload.get("profile")
    if args.profile and input_profile and args.profile != input_profile:
        raise AnkiCardError("--profile conflicts with the profile in the JSON input")
    route, profile = select_route(connect, base, args.profile or input_profile)
    request_id, payload_hash = request_identity(payload, profile)
    log = ReceiptLog()
    previous = log.request_state(request_id)
    if previous:
        if previous.get("payloadHash") != payload_hash:
            raise AnkiCardError("request_id was already used with a different payload")
        if previous.get("undone"):
            raise AnkiCardError(
                "this request was previously undone; use a new request_id to add it again"
            )
        result = result_from_receipt(previous, already_applied=True)
        if payload.get("sync", False):
            if route == "ankiconnect":
                result["sync"] = perform_sync(route, connect, base, profile)
            else:
                with open_collection(base, profile) as col:
                    result["sync"] = perform_sync(route, connect, base, profile, col)
        return result

    sync_requested = payload.get("sync", False)
    if route == "ankiconnect":
        if sync_requested:
            perform_sync(route, connect, base, profile)
        prepared = prepare_connect_notes(connect, payload["notes"])
        note_ids = connect.invoke("addNotes", {"notes": prepared})
        if (
            not isinstance(note_ids, list)
            or len(note_ids) != len(prepared)
            or not all(isinstance(note_id, int) and note_id > 0 for note_id in note_ids)
        ):
            raise AnkiCardError(f"AnkiConnect returned invalid note IDs: {note_ids}")
        canonical_notes = [
            {
                "deck": note["deckName"],
                "note_type": note["modelName"],
                "fields": note["fields"],
                "tags": note["tags"],
            }
            for note in prepared
        ]
        receipt = add_receipt(
            request_id=request_id,
            payload_hash=payload_hash,
            route=route,
            profile=profile,
            note_ids=note_ids,
            notes=canonical_notes,
            backup_created=None,
        )
        log.append(receipt)
        result = result_from_receipt(receipt, already_applied=False)
        if sync_requested:
            try:
                result["sync"] = perform_sync(route, connect, base, profile)
            except AnkiCardError as exc:
                result["ok"] = False
                result["sync"] = {"status": "failed", "error": str(exc)}
                raise AddedButUnsyncedError(result, str(exc)) from exc
        return result

    with open_collection(base, profile) as col:
        if sync_requested:
            perform_sync(route, connect, base, profile, col)
        requests, created_notes, canonical_notes = prepare_backend_notes(
            col, payload["notes"]
        )
        backup_created = ensure_backup(col, base, profile)
        try:
            col.add_notes(requests)
        except Exception as exc:
            raise AnkiCardError(f"Anki rejected the note batch: {exc}") from exc
        note_ids = [int(note.id) for note in created_notes]
        if not all(note_id > 0 for note_id in note_ids):
            raise AnkiCardError(f"Anki returned invalid note IDs: {note_ids}")
        receipt = add_receipt(
            request_id=request_id,
            payload_hash=payload_hash,
            route=route,
            profile=profile,
            note_ids=note_ids,
            notes=canonical_notes,
            backup_created=backup_created,
        )
        log.append(receipt)
        result = result_from_receipt(receipt, already_applied=False)
        if sync_requested:
            try:
                result["sync"] = perform_sync(route, connect, base, profile, col)
            except AnkiCardError as exc:
                result["ok"] = False
                result["sync"] = {"status": "failed", "error": str(exc)}
                raise AddedButUnsyncedError(result, str(exc)) from exc
        return result


def validate_deck_name(name: str) -> None:
    if not name.strip():
        raise AnkiCardError("deck name must not be empty")
    if name != name.strip():
        raise AnkiCardError("deck name must not start or end with whitespace")
    if any(not component.strip() for component in name.split("::")):
        raise AnkiCardError(
            "deck name must contain non-empty components separated by '::'"
        )


def command_create_deck(
    args: argparse.Namespace, connect: AnkiConnect, base: Path
) -> dict[str, Any]:
    name = args.deck_name
    validate_deck_name(name)
    route, profile = select_route(connect, base, args.profile)
    backup_created: bool | None = None

    if route == "ankiconnect":
        deck_names = connect.invoke("deckNames")
        if not isinstance(deck_names, list) or not all(
            isinstance(deck_name, str) for deck_name in deck_names
        ):
            raise AnkiCardError("AnkiConnect returned invalid deck names")
        existing = next(
            (
                deck_name
                for deck_name in deck_names
                if deck_name.casefold() == name.casefold()
            ),
            None,
        )
        deck_name = existing or name
        # createDeck is idempotent and is also the only AnkiConnect API that
        # exposes the deck ID for an existing deck.
        deck_id = connect.invoke("createDeck", {"deck": deck_name})
        created = existing is None
    else:
        with open_collection(base, profile) as col:
            existing = col.decks.by_name(name)
            if existing is not None:
                deck_name = existing["name"]
                deck_id = int(existing["id"])
                created = False
            else:
                backup_created = ensure_backup(col, base, profile)
                result = col.decks.add_normal_deck_with_name(name)
                deck_name = name
                deck_id = int(result.id)
                created = True

    if not isinstance(deck_id, int) or isinstance(deck_id, bool) or deck_id <= 0:
        raise AnkiCardError(f"Anki returned an invalid deck ID: {deck_id!r}")
    return {
        "ok": True,
        "operation": "create-deck",
        "route": route,
        "profile": profile,
        "deck": deck_name,
        "deckId": deck_id,
        "created": created,
        "backupCreated": backup_created,
    }


def connect_schema(connect: AnkiConnect) -> tuple[list[str], list[dict[str, Any]]]:
    decks = sorted(connect.invoke("deckNames"), key=str.casefold)
    models = sorted(connect.invoke("modelNames"), key=str.casefold)
    note_types = [
        {
            "name": model,
            "fields": connect.invoke("modelFieldNames", {"modelName": model}),
        }
        for model in models
    ]
    return decks, note_types


def backend_schema(col: Collection) -> tuple[list[str], list[dict[str, Any]]]:
    decks = sorted(
        (entry.name for entry in col.decks.all_names_and_ids()), key=str.casefold
    )
    note_types = [
        {
            "name": model["name"],
            "fields": [field["name"] for field in model["flds"]],
        }
        for model in sorted(col.models.all(), key=lambda item: item["name"].casefold())
    ]
    return decks, note_types


def command_schema(
    args: argparse.Namespace, connect: AnkiConnect, base: Path
) -> dict[str, Any]:
    route, profile = select_route(connect, base, args.profile)
    if route == "ankiconnect":
        decks, note_types = connect_schema(connect)
    else:
        with open_collection(base, profile) as col:
            decks, note_types = backend_schema(col)
    return {
        "ok": True,
        "operation": "schema",
        "route": route,
        "profile": profile,
        "decks": decks,
        "noteTypes": note_types,
    }


def backend_note_info(col: Collection, note_id: int) -> dict[str, Any]:
    try:
        note = col.get_note(NoteId(note_id))
    except Exception as exc:
        raise AnkiCardError(f"note {note_id} was not found: {exc}") from exc
    model = note.note_type()
    if model is None:
        raise AnkiCardError(f"note {note_id} references a missing note type")
    card_ids = [int(card_id) for card_id in col.card_ids_of_note(note.id)]
    return {
        "noteId": int(note.id),
        "guid": note.guid,
        "noteType": model["name"],
        "fields": {name: note[name] for name in note.keys()},
        "tags": list(note.tags),
        "cardIds": card_ids,
    }


def command_get(
    args: argparse.Namespace, connect: AnkiConnect, base: Path
) -> dict[str, Any]:
    route, profile = select_route(connect, base, args.profile)
    if route == "ankiconnect":
        notes = connect.invoke("notesInfo", {"notes": args.note_ids})
    else:
        with open_collection(base, profile) as col:
            notes = [backend_note_info(col, note_id) for note_id in args.note_ids]
    return {
        "ok": True,
        "operation": "get",
        "route": route,
        "profile": profile,
        "notes": notes,
    }


def command_sync(
    args: argparse.Namespace, connect: AnkiConnect, base: Path
) -> dict[str, Any]:
    route, profile = select_route(connect, base, args.profile)
    if route == "ankiconnect":
        result = perform_sync(route, connect, base, profile)
    else:
        with open_collection(base, profile) as col:
            result = perform_sync(route, connect, base, profile, col)
    return {
        "ok": True,
        "operation": "sync",
        "route": route,
        "profile": profile,
        "sync": result,
    }


def note_matches_receipt(note: dict[str, Any], expected: dict[str, Any]) -> bool:
    model = note.get("modelName", note.get("noteType"))
    fields = note.get("fields", {})
    connect_fields = {
        name: value.get("value") if isinstance(value, dict) else value
        for name, value in fields.items()
    }
    return model == expected["note_type"] and connect_fields == expected["fields"]


def command_undo(
    args: argparse.Namespace, connect: AnkiConnect, base: Path
) -> dict[str, Any]:
    log = ReceiptLog()
    receipt = log.request_state(args.request_id)
    if not receipt:
        raise AnkiCardError(
            f"no successful request named {args.request_id!r} was found"
        )
    if receipt.get("undone"):
        return {
            "ok": True,
            "operation": "undo",
            "alreadyUndone": True,
            "requestId": args.request_id,
            "deleted": 0,
        }
    requested_profile = args.profile or receipt.get("profile")
    route, profile = select_route(connect, base, requested_profile)
    note_ids = [int(note_id) for note_id in receipt["noteIds"]]
    expected_by_id = dict(zip(note_ids, receipt["notes"], strict=True))
    existing_ids: list[int] = []
    changed_ids: list[int] = []
    backup_created: bool | None = None
    if route == "ankiconnect":
        infos = connect.invoke("notesInfo", {"notes": note_ids})
        info_by_id = {int(info["noteId"]): info for info in infos}
        existing_ids = sorted(info_by_id)
        changed_ids = [
            note_id
            for note_id in existing_ids
            if not note_matches_receipt(info_by_id[note_id], expected_by_id[note_id])
        ]
        if changed_ids and not args.force:
            raise AnkiCardError(
                f"notes were edited after creation and will not be deleted without --force: {changed_ids}"
            )
        if existing_ids:
            connect.invoke("deleteNotes", {"notes": existing_ids})
    else:
        with open_collection(base, profile) as col:
            info_by_id: dict[int, dict[str, Any]] = {}
            for note_id in note_ids:
                try:
                    info_by_id[note_id] = backend_note_info(col, note_id)
                except AnkiCardError:
                    continue
            existing_ids = sorted(info_by_id)
            changed_ids = [
                note_id
                for note_id in existing_ids
                if not note_matches_receipt(
                    info_by_id[note_id], expected_by_id[note_id]
                )
            ]
            if changed_ids and not args.force:
                raise AnkiCardError(
                    f"notes were edited after creation and will not be deleted without --force: {changed_ids}"
                )
            if existing_ids:
                backup_created = ensure_backup(col, base, profile)
                col.remove_notes([NoteId(note_id) for note_id in existing_ids])
            if args.sync:
                perform_sync(route, connect, base, profile, col)
    if route == "ankiconnect" and args.sync:
        perform_sync(route, connect, base, profile)
    event = {
        "event": "undo",
        "version": 1,
        "createdAt": utc_now(),
        "requestId": args.request_id,
        "profile": profile,
        "route": route,
        "deletedNoteIds": existing_ids,
        "alreadyMissingNoteIds": sorted(set(note_ids) - set(existing_ids)),
        "backupCreated": backup_created,
    }
    log.append(event)
    return {
        "ok": True,
        "operation": "undo",
        "alreadyUndone": False,
        "requestId": args.request_id,
        "route": route,
        "profile": profile,
        "deleted": len(existing_ids),
        "deletedNoteIds": existing_ids,
        "alreadyMissingNoteIds": event["alreadyMissingNoteIds"],
        "backupCreated": backup_created,
        "synced": args.sync,
    }


def command_history(args: argparse.Namespace) -> dict[str, Any]:
    events = ReceiptLog().events()
    return {
        "ok": True,
        "operation": "history",
        "events": events[-args.limit :],
    }


def command_status(
    args: argparse.Namespace, connect: AnkiConnect, base: Path
) -> dict[str, Any]:
    profiles = available_profiles(base)
    if connect.available():
        return {
            "ok": True,
            "operation": "status",
            "route": "ankiconnect",
            "profile": active_profile(connect),
            "profiles": profiles,
            "ankiConnect": True,
        }
    busy = {
        profile: processes_using_collection(collection_path(base, profile))
        for profile in profiles
    }
    return {
        "ok": True,
        "operation": "status",
        "route": "backend",
        "profile": resolve_profile(base, args.profile),
        "profiles": profiles,
        "ankiConnect": False,
        "busyProfiles": {name: pids for name, pids in busy.items() if pids},
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="anki-card",
        description=(
            "Safely inspect and modify Anki. Uses AnkiConnect when the GUI is "
            "already open and Anki's backend directly otherwise."
        ),
    )
    result.add_argument(
        "--profile", help="Anki profile name (auto-detected by default)"
    )
    result.add_argument(
        "--anki-base",
        type=Path,
        default=default_anki_base(),
        help="Anki data directory (default: $ANKI_BASE or the platform default)",
    )
    result.add_argument(
        "--connect-url",
        default=os.environ.get("ANKI_CONNECT_URL", DEFAULT_CONNECT_URL),
        help="AnkiConnect endpoint",
    )
    result.add_argument(
        "--connect-timeout",
        type=float,
        default=60.0,
        help="AnkiConnect request timeout in seconds",
    )
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("status", help="show the selected access route and profile")
    subcommands.add_parser("schema", help="list decks, note types, and fields as JSON")
    create_deck = subcommands.add_parser(
        "create-deck", help="create a deck or nested deck if it does not exist"
    )
    create_deck.add_argument("deck_name")
    add = subcommands.add_parser(
        "add", help="add a JSON batch read from standard input"
    )
    add.epilog = (
        'Example: echo \'{"notes":[{"deck":"Default","note_type":"Basic",'
        '"fields":{"Front":"Q","Back":"A"}}]}\' | anki-card add'
    )
    get = subcommands.add_parser("get", help="return notes by numeric note ID")
    get.add_argument("note_ids", nargs="+", type=int)
    subcommands.add_parser("sync", help="perform a normal AnkiWeb sync")
    undo = subcommands.add_parser(
        "undo", help="delete all notes from a recorded request"
    )
    undo.add_argument("request_id")
    undo.add_argument(
        "--force",
        action="store_true",
        help="also delete notes whose fields were edited after creation",
    )
    undo.add_argument(
        "--sync", action="store_true", help="sync after deleting the notes"
    )
    history = subcommands.add_parser("history", help="show recent local receipt events")
    history.add_argument("--limit", type=int, default=20)
    return result


def main() -> int:
    args = parser().parse_args()
    if args.connect_timeout <= 0:
        emit(
            {"ok": False, "error": "--connect-timeout must be positive"},
            stream=sys.stderr,
        )
        return 2
    if getattr(args, "limit", 1) <= 0:
        emit({"ok": False, "error": "--limit must be positive"}, stream=sys.stderr)
        return 2
    connect = AnkiConnect(
        args.connect_url,
        args.connect_timeout,
        os.environ.get("ANKI_CONNECT_KEY"),
    )
    try:
        with exclusive_lock():
            if args.command == "add":
                output = command_add(args, connect, args.anki_base)
            elif args.command == "create-deck":
                output = command_create_deck(args, connect, args.anki_base)
            elif args.command == "schema":
                output = command_schema(args, connect, args.anki_base)
            elif args.command == "get":
                output = command_get(args, connect, args.anki_base)
            elif args.command == "sync":
                output = command_sync(args, connect, args.anki_base)
            elif args.command == "undo":
                output = command_undo(args, connect, args.anki_base)
            elif args.command == "history":
                output = command_history(args)
            elif args.command == "status":
                output = command_status(args, connect, args.anki_base)
            else:
                raise AssertionError(f"unhandled command: {args.command}")
        emit(output)
        return 0
    except AddedButUnsyncedError as exc:
        emit(exc.result, stream=sys.stderr)
        return 3
    except AnkiCardError as exc:
        emit({"ok": False, "error": str(exc)}, stream=sys.stderr)
        return 1
    except KeyboardInterrupt:
        emit({"ok": False, "error": "interrupted"}, stream=sys.stderr)
        return 130
    except Exception as exc:
        emit(
            {
                "ok": False,
                "error": f"internal error: {type(exc).__name__}: {exc}",
            },
            stream=sys.stderr,
        )
        return 70


if __name__ == "__main__":
    raise SystemExit(main())

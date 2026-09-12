---
name: anki-cards
description: Safely create decks, add and inspect cards, sync, and undo cards in Elias's local Anki collection with the anki-card command. Use when asked to create an Anki deck, add Anki cards, list decks or note types, verify locally created cards, explicitly sync Anki, or undo an agent-created card batch.
---

# Anki Cards

Use the `anki-card` command. It automatically uses AnkiConnect when the Anki GUI
is already open and Anki's official backend when it is closed. Never start or
stop Anki for this skill.

## Inspect the collection

- Run `anki-card schema` when the deck, note type, or field names are not already
  known. Its JSON response includes every deck and note type with its fields.
- Run `anki-card get NOTE_ID...` to verify notes by ID.
- Run `anki-card status` only when diagnosing route or profile selection.

## Create decks

- Create a deck only when Elias explicitly requests it; do not create one merely
  because no existing deck is a perfect match.
- Run `anki-card create-deck 'General::CS::History'` to create a deck or nested
  deck. Anki uses `::` to separate levels.
- The command is idempotent: `created` is false when the deck already exists.
- Report the deck name, deck ID, route, profile, and whether it was created. A
  headless creation makes a pre-change backup; AnkiConnect creation reports
  `backupCreated` as null because Anki owns the open collection.

## Add cards

- Treat an explicit request to add cards as authorization to create exactly
  those cards; do not ask for a second confirmation.
- Pass one JSON object to `anki-card add` on standard input. Use this shape:

  ```json
  {
    "request_id": "stable-id-for-safe-retries",
    "sync": false,
    "notes": [
      {
        "deck": "General",
        "note_type": "Basic",
        "fields": {"Front": "Question", "Back": "Answer"},
        "tags": []
      }
    ]
  }
  ```

- Construct JSON with `jq` or another JSON encoder so text is escaped correctly.
- Use the same stable `request_id` when retrying an uncertain request. If it is
  omitted, `anki-card` derives one from the complete batch.
- Omit `tags` unless Elias requested tags. Do not request duplicates; the
  command rejects them.
- Preserve card wording supplied by Elias. Generate or rewrite card content
  only when he asks for that editorial work.
- Set `sync` to true, or run `anki-card sync`, only when Elias explicitly asks
  to synchronize.
- Check `ok`, `added`, `alreadyApplied`, `noteIds`, `route`, and `profile` in the
  response. Exit code 3 means the notes were added locally but the requested
  post-add sync failed; do not repeat the request under a new ID.
- Report the destination deck, number of notes created, note IDs, route, and any
  rejected or duplicate notes.

## Undo a recorded batch

- Run `anki-card undo REQUEST_ID` only when Elias explicitly asks to remove that
  batch. The command refuses to delete notes edited since creation unless
  `--force` is supplied; never add `--force` without explicit authorization.
- Add `--sync` only if Elias explicitly requests synchronization.

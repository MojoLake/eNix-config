---
name: anki-cards
description: Formulate and safely manage simple Anki cards in Elias's local collection with the anki-card command. Use when asked to propose or create cards, create a deck, inspect cards or schemas, explicitly sync Anki, or undo an agent-created card batch.
---

# Anki Cards

Use the `anki-card` command. It automatically uses AnkiConnect when the Anki GUI
is already open and Anki's official backend when it is closed. Never start or
stop Anki for this skill.

## Formulate cards for Elias

Elias uses Anki mainly to awaken a small, useful brain signal, not to recite an
explanation. When proposing or writing cards:

- Do not formulate cards for material he has not understood. Prefer fundamental,
  durable knowledge that helps reconstruct a useful mental model; omit a fact
  merely mentioned in conversation.
- Apply the minimum-information principle: test one fact, term, distinction, or
  causal link per generated card. Treat `and`, semicolons, multiple requested
  outputs, or multiple independent verbs in an answer as warnings that the note
  should be split. Do not combine an acronym expansion with how the thing works.
- Judge the cue from a cold start. The visible front must naturally evoke one
  intended piece of knowledge without requiring the learner to remember the
  card's wording. If several materially different answers fit, rewrite it.
- Give cards a recognizable structure. Use `TERM?` for an acronym expansion or
  short explanation, for example `SIMT?` → `single instruction, multiple
  threads`. Here `?` means “expand or explain this term,” but each note should
  choose only one of those retrieval targets rather than answering both.
- Use parenthetical direction labels to specify the expected answer language.
  For example, `el sol (fi.)` → `aurinko`, while `aurinko (esp.)` → `el sol`.
  The label names the language to answer in, not the language shown.
- Use a cloze only when the remaining sentence semantically constrains the exact
  missing item. A grammatical blank with many plausible completions is a bad
  cue: `A flip-flop stores {{...}}` could elicit many valid answers.
- Hide the smallest useful unit in a cloze—normally one word, symbol, number, or
  short established term. Keep qualifiers, relationships, and explanatory text
  visible. If the hidden text is a sentence fragment or substantial explanation,
  use a Basic card instead.
- There is no one-cloze-per-note rule. A note may contain two or more deletions:
  use different cloze numbers when each should generate its own retrieval card,
  such as `{{c1::causal}} {{c2::masking}}`; use the same number for multiple
  tightly linked fragments that should be recalled together. Judge the simplicity
  and uniqueness of each generated card, not the number of deletions in the note.
- Prefer a compact, self-contained relational sentence with several small clozes
  over a terse Basic prompt when each visible context strongly constrains its
  deletion. For example: `If layer weights are too large to fit on-chip
  {{c2::SRAM}}, they are processed in {{c1::tiles}}.` Do not default to Basic
  merely because the underlying idea is explanatory.
- Use Basic when the answer is naturally a short explanation and equivalent
  wording should count as correct. Use `Basic (and reversed)` only when both
  directions are useful and each direction independently has one clear answer.
- Add domain context or an expected-answer cue when needed to prevent interference.
  Do not introduce unfamiliar terminology solely to make a card.
- Several atomic cards may approach an important idea from different directions;
  this useful redundancy is preferable to one comprehensive card.
- Preserve user-supplied wording and note types unless incorrect. Put optional
  explanations, sources, and dates outside the recalled text when fields permit;
  date-stamp volatile knowledge.
- Before proposing or adding cards, inspect every card that will actually be
  generated—including each cloze and both directions of reversed notes—for an
  ambiguous cue, oversized hidden text, low-value fact, or accidental set.

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

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

- Do not formulate cards for material he has not yet understood. Teach or clarify
  it first.
- Apply the minimum-information principle aggressively: test one fact, term,
  distinction, or causal link per card.
- Prefer a short cue and an even shorter answer, often a word or phrase. If an
  answer needs several clauses or a list, split or omit the card.
- Require the intended answer to be unique at the cue's stated level of
  specificity. If a broader category, narrower term, synonym, or alternative
  answer would also be correct, tighten the cue or explicitly accept the
  equivalents. Never rely on the learner guessing which answer was intended.
- Prefer basics, fundamentals, and durable high-value knowledge over comprehensive
  coverage or incidental detail. Do not make a card merely because a fact was
  discussed; keep it only if recalling it helps reconstruct the useful mental
  model.
- Preserve the user's requested wording and note type when supplied; these take
  precedence over the defaults below unless they would make the card incorrect.
- Use a `Basic (and reversed)` note for a foundational mapping when recall in
  both directions is useful. Evaluate each generated direction as its own card:
  both fronts must independently cue a unique answer. For example, “a hardware
  description language” is not a safe reverse cue for “Verilog” because VHDL is
  also correct; add distinguishing context.
- Otherwise prefer a cloze for a compact declarative relationship, using Anki
  syntax such as `Raw score before softmax is called a {{c1::logit}}`; use a
  direct basic question when a cloze would be unnatural. Do not make clozes by
  merely deleting arbitrary words from verbose prose.
- Avoid broad prompts such as “explain,” compound comparison questions, sets, and
  enumerations. Include the domain in the cue, such as “In LLM inference,” when
  the prompt would otherwise be ambiguous or invite answers from other domains.
- Several atomic cards may approach an important idea from different directions;
  this useful redundancy is preferable to one comprehensive card.
- Put optional explanation, source, or date outside the text that must be recalled
  when the note type has suitable fields. Date-stamp volatile knowledge.
- When proposing cards, identify the intended note type and perform a final pass
  over every card that will actually be generated—including both directions of
  reversed notes—for ambiguous cues, low-value facts, compound answers, and
  accidental sets.

For example, “HBM is a form of ...” is ambiguous because both “memory” and “DRAM”
are correct. Prefer the precise cloze `HBM uses {{c1::DRAM}} memory cells.` Also
replace “What is the difference between an attention head, multi-head attention,
and a transformer block?” with separate atomic cues.

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

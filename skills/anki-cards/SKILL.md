---
name: anki-cards
description: Suggest or add Anki cards for Elias; inspect collections, create requested decks, explicitly sync, or undo agent batches using anki-card.
---

# Anki Cards

## Formulation

Prefer contextual clozes with short, unambiguous answers. Test one idea per
generated card, allowing multiple clozes per note. Use Basic for causal questions,
commands, and vocabulary; reverse only useful, unambiguous pairs. Avoid yes/no
questions, essays, padding, and unfamiliar material. Unselected cards aren't
necessarily rejected. Preserve supplied wording/types unless incorrect; put
qualifications in Back Extra. Review each generated card for ambiguity and value.
Show cloze syntax or front/back pairs. Language labels indicate answer language.

## Formulation examples

These examples come from Elias's existing collection and reflect card shapes he
has approved. Use them as patterns, not as a catalog of facts that must be added
to Anki or wording that must be copied literally.

### Accepted from the electronics discussion

- `Implementing a communication protocol by directly controlling pins in software is called {{c1::bit-banging}}.`
- `“Asynchronous” in UART means there is no shared {{c1::clock signal}} between the devices.`
- `To sample bits at the right intervals, UART sender and receiver must agree on the {{c1::bit rate}} beforehand.`
- `A UART receiver uses the {{c1::start bit}} as the timing reference for receiving a character.`
- Basic: `Why does a UART receiver sample near the middle of each bit?` →
  `To leave a timing margin from the transitions between bits.`
- `UART {{c1::Universal asynchronous receiver-transmitter}} was one of the {{c2::earliest}} computer {{c3::communication}} devices.`
  Back Extra qualifies “earliest”: Bell dates his design to 1961–62;
  computer communication interfaces existed before UART.
- `SPI's ({{c1::Serial Peripheral Interface}}) original specification was from {{c2::Motorola}} in the early {{c3::1980's}}.`

### Technical

- `A Git branch is a {{c1::pointer}} to a {{c2::commit}}.`
- `Deleting a branch deletes {{c1::the pointer}}, not {{c2::the commits}}.`
- `A {{c1::process}} owns resources such as the address space, while a
  {{c2::thread}} is an execution stream.`
- `The OS scheduler usually schedules {{c1::threads}}, not
  {{c1::processes}}.` Use the same cloze number when the contrasted fragments
  should be recalled together.
- `A CPU gets the address of its next instruction from the {{c1::program
  counter (PC)}}.`
- `DHCP automatically assigns {{c1::IP addresses}} and network configuration to
  devices joining a network.`
- Basic: `Create the symlink a.md → b.md (command)` → `ln -s b.md a.md`.

### Revising weak conceptual prompts

These are illustrative revisions, not previously approved cards. Preserve the
useful relationship in the visible text and make the missing concept small.

- Weak: `Does one CPU instruction always take one clock cycle?` → `No ...`
  tests recognition. If pipelining was understood, a useful target is:
  `CPU {{c1::pipelining}} overlaps the processing of multiple instructions.`
- Weak: `Does the clock supply the energy that powers a register?` → `No ...`
  becomes: `In a digital circuit, the power supply provides energy; the clock
  controls the {{c1::timing}} of register updates.`
- Weak: `How does SPI differ from UART regarding timing?` can become:
  `{{c1::SPI}} carries a separate clock signal; {{c2::UART}} uses a pre-agreed
  bit rate without a separate clock signal.` Each deletion tests one protocol
  against its timing mechanism.
- A direct causal question can remain Basic: `Why can an excessively fast CPU
  clock cause incorrect results?` → `Registers may capture results before the
  logic settles.` Do not force this into an ambiguous one-word blank.

### Mathematics

- `The {{c1::characteristic polynomial}} of A is {{c2::det(xI − A)}}.`
- `The normal derivative {{c1::∂u/∂n}} equals {{c2::∇u · n}}.` Put `It is
  the component of the gradient in the normal direction.` in Back Extra.
- `In Lᵖ spaces, functions differing only on a set of {{c1::measure zero}} are
  considered {{c2::the same function}}, because the {{c3::Lebesgue integral
  ignores such sets}}.`
- `A {{c1::Banach space}} is a {{c2::complete normed vector space}}.`
- `A {{c1::normal operator}} satisfies {{c2::VV* = V*V}}.` Put `Equivalently,
  it commutes with its adjoint.` in Back Extra.
- `In Lu = f, f is the {{c1::source term}}; when f = 0, the equation is
  {{c2::homogeneous}}.`

### Languages

- Basic: `vakiintua (esp.)` → `consolidarse`.
- Basic: `harhaanjohtava (eng.)` → `misleading`.
- Basic: `intentional (synonym)` → `deliberate`.
- Basic: `latent (etym., meaning)` → `latere — “to lie hidden”`.
- Basic: `latent (etym., language)` → `Latin`.
- Basic: `välittömästi (esp.; not inmediatamente)` → `enseguida`.
- Basic: `Te agradezco que me pagues la mitad.` → `Kiitän sinua siitä,
  että maksat minulle puolet.`

### Behaviour and personal cues

- `If something is scary, {{c1::do it}}.`

### General knowledge and causal understanding

- `{{c1::Great Britain}} consists of England, Scotland, and Wales; the
  {{c2::United Kingdom}} also includes Northern Ireland.`
- Basic: `A.D.?` → `anno Domini`.
- Basic: `Why was muscle power the main source of mechanical power before
  electricity?` → `The body was the only widely available general-purpose
  energy converter.`

## Collection operations

Use `anki-card`; it selects AnkiConnect or the closed-GUI backend automatically.
Never start/stop Anki. Run `schema` for unknown decks/types/fields, `get NOTE_ID...`
to verify, and `status` for route/profile diagnosis.

Add explicitly requested cards without reconfirmation. Pass encoded JSON on stdin
to `anki-card add`:

```json
{"request_id":"stable-batch-id","sync":false,"notes":[{"deck":"General","note_type":"Basic","fields":{"Front":"Question","Back":"Answer"}}]}
```

Keep request IDs stable on retries. Omit tags unless requested; don't request
duplicates. Sync only when explicitly requested (`sync:true` or `anki-card sync`).
Check `ok`, `added`, `alreadyApplied`, `noteIds`, `route`, and `profile`.
Exit 3 means added locally but sync failed: don't re-add under another ID.
Report deck, count, note IDs, route/profile, and rejections.

Only on explicit request: `anki-card create-deck 'General::CS::History'`
(idempotent; report name/ID, created, route/profile), or
`anki-card undo REQUEST_ID`. Undo needs separate explicit authorization for
`--force`; add `--sync` only when requested.

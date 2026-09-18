---
name: paper-to-kindle
description: Find, obtain, validate, and deliver papers or books to Elias's Kindle. Use when asked for reading recommendations, to locate a specific paper or book, or to send a local PDF or EPUB to Kindle.
---

# Paper to Kindle

Use the `kindle_mail` MCP tools for delivery. They send only to Elias's fixed
Send-to-Kindle address and accept only validated PDF and EPUB files.

## Find the document

- When Elias names a specific work, identify the exact title, authors, and
  version before downloading it. Prefer the author's site, arXiv, an
  institutional repository, or an openly accessible publisher copy.
- When he asks for an interesting paper without choosing one, use his stated
  topic and current interests to present a small set of candidates with a brief
  reason for each. Do not send one until he chooses, unless he explicitly asks
  you to select and deliver it autonomously.
- Do not bypass paywalls, authentication, DRM, or access controls. A
  user-provided local file is acceptable even when its original source is not
  available to the agent.
- Verify that the downloaded file is the intended complete document rather than
  an HTML error page, abstract-only page, supplement, or unrelated version.
- Prefer a temporary download directory unless Elias asks to keep the local
  copy. Preserve a user-provided file.

## Prepare and preview

- Preserve the work's recognizable title in the filename and delivery title.
- Use `check_kindle_mail_setup` when configuration state is unknown. If it is
  incomplete, stop before downloading large files. Report its `problem` field;
  a missing or rotated Resend key is repaired with `kindle-mail setup-resend`.
- Call `preview_kindle_delivery` before every send. Report the title, source,
  file type, size, and masked Kindle destination. Resolve validation errors
  before attempting delivery.
- Do not convert formats unless Elias asks. The current delivery tool accepts
  PDF and EPUB only.

## Deliver

- Treat an explicit request to send or deliver the document as authorization
  to call `send_to_kindle` after the preview; do not ask for an extra
  conversational confirmation. The MCP write approval remains the final
  confirmation.
- If the request was only to find, compare, summarize, or download a document,
  do not send it.
- Use a stable `request_id` derived from the document identity or SHA-256, such
  as `kindle:sha256:<first-24-hex>`, and reuse it for any retry. Never invent a
  new ID after an uncertain result.
- Check `alreadySent`, `sentAt`, `filename`, and `sha256` in the result. Report
  delivery as successful only when the tool does.
- Remove only temporary files created for this request, and only after a
  confirmed send or when they are no longer needed.

## Record confirmed deliveries

- The sender's authoritative machine-readable receipts are stored in
  `~/.local/state/kindle-mail/sent.jsonl`; do not edit them by hand.
- After a confirmed send, add the work to
  `/home/mojolake/eVault/AI Playground/Kindle Delivery Log.md`. Record the
  delivery date, title, authors and source when known, format, size, SHA-256,
  and provider message ID.
- Do not log failed or uncertain sends. When `alreadySent` is true, backfill a
  missing human-readable entry if useful, but do not duplicate an existing one.

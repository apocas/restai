"""Outbound + inbound messaging channels.

Groups the per-channel integrations that were previously loose top-level
modules:

- `whatsapp` — WhatsApp Cloud API: signature verification + send.
- `telegram` — Telegram Bot API: long-poll updates + send.
- `webhooks` — generic per-project outbound event webhooks (HMAC-signed).

Each is a leaf module (stdlib + `requests`/`httpx` + the SSRF guard for
webhooks); none import each other, so this package is purely organizational.
"""

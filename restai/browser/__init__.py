"""Agentic browser — Playwright-backed per-chat Chromium container.

`manager.py` runs on the host (spawns containers, discovers ports, posts
JSON to the micro-server). `micro_server.py` runs INSIDE each container
(wraps Playwright's sync API over stdlib `http.server`).
"""

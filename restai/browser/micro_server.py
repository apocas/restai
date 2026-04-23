"""Browser micro-server — runs INSIDE the Playwright container.

Wraps `playwright.sync_api` over stdlib `http.server`. Zero third-party
deps beyond Playwright itself (which is pre-installed in
`mcr.microsoft.com/playwright/python`). One module-level BrowserContext
per container keeps cookies + navigation state alive across tool calls.

Endpoints:
- POST /health      — liveness probe, returns `{ok: true}`.
- POST /goto        — {url} → {final_url, title}
- POST /content     — {selector?, format?} → {content, length}
- POST /click       — {selector} → {url_after, nearby_text}
- POST /fill        — {selector, value} → {ok}
- POST /select      — {selector, option} → {ok}
- POST /screenshot  — {selector?} → {png_b64, width, height}
- POST /wait        — {selector, timeout?} → {found}
- POST /download    — {selector, timeout?} → {path, size, mime}
- POST /eval        — {js} → {result}
- POST /storage/load — {state: {...}}
- POST /storage/dump — {} → {state: {...}}
- POST /close       — shuts the context (page stays disposable); used by host on cleanup.

JSON-in, JSON-out. Errors surface as {"error": "..."} with HTTP 500.

This file is copied into the container at `/opt/restai_browser/micro_server.py`
by the host-side `BrowserManager` at container startup (via `put_archive`).
It is **not** imported by the host-side RESTai process — it lives in the
container's Python runtime only, so it can import `playwright.sync_api`
without demanding Playwright as a host dep.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import sys
import threading
import time
# Single-threaded HTTPServer on purpose: Playwright's sync_api requires
# that every call comes from the thread that started `sync_playwright()`.
# ThreadingHTTPServer would spawn a new thread per request and break that
# invariant with a confusing "cannot switch to a different thread" error.
# Tool calls per chat are sequential anyway (the LLM calls one at a time),
# so single-threaded is fine.
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
_log = logging.getLogger("restai.browser.micro")

_DOWNLOAD_DIR = "/home/user/downloads"
os.makedirs(_DOWNLOAD_DIR, exist_ok=True)


# ─── Playwright lifecycle ────────────────────────────────────────────

_lock = threading.Lock()
_pw = None
_browser = None
_context = None
_page = None  # current active page


def _ensure_context():
    """Lazy-start Playwright + a persistent BrowserContext on first use."""
    global _pw, _browser, _context, _page
    with _lock:
        if _context is not None:
            return
        from playwright.sync_api import sync_playwright

        _pw = sync_playwright().start()
        _browser = _pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )
        _context = _browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        _page = _context.new_page()
        _log.info("Playwright context initialized.")


def _page_or_new():
    """Return the live page, making a new one if the previous closed."""
    global _page
    _ensure_context()
    if _page is None or _page.is_closed():
        _page = _context.new_page()
    return _page


# ─── HTML sanitation before returning content to the agent ───────────

_SCRIPT_RE = re.compile(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style\b[^<]*(?:(?!</style>)<[^<]*)*</style>", re.IGNORECASE | re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_MAX_CONTENT_BYTES = 500_000


def _sanitize_html(html: str) -> str:
    if not html:
        return ""
    html = _SCRIPT_RE.sub("", html)
    html = _STYLE_RE.sub("", html)
    html = _COMMENT_RE.sub("", html)
    if len(html) > _MAX_CONTENT_BYTES:
        html = html[:_MAX_CONTENT_BYTES] + "\n<!-- truncated -->"
    return html


def _to_markdown(html: str) -> str:
    """Quick HTML → markdown-ish rendering. Not perfect but cheap."""
    # Very lightweight: strip tags, collapse whitespace. The LLM is smart
    # enough to work with this for most purposes.
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|section|article|li|tr|h[1-6])>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<(p|div|section|article|li|tr|h[1-6])[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)  # strip remaining tags
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ─── Handlers ────────────────────────────────────────────────────────


def _handle_goto(payload: dict) -> dict:
    url = payload.get("url", "")
    if not url:
        raise ValueError("url is required")
    page = _page_or_new()
    page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    return {"final_url": page.url, "title": page.title()}


def _handle_content(payload: dict) -> dict:
    selector = payload.get("selector")
    fmt = (payload.get("format") or "markdown").lower()
    page = _page_or_new()
    if selector:
        el = page.query_selector(selector)
        if el is None:
            raise ValueError(f"selector not found: {selector}")
        html = el.inner_html()
    else:
        html = page.content()
    html = _sanitize_html(html)
    if fmt == "html":
        out = html
    elif fmt == "text":
        out = _to_markdown(html)
    else:  # markdown (= cleaned text for now)
        out = _to_markdown(html)
    if len(out) > _MAX_CONTENT_BYTES:
        out = out[:_MAX_CONTENT_BYTES] + "\n… (truncated)"
    return {"content": out, "length": len(out)}


def _handle_click(payload: dict) -> dict:
    selector = payload.get("selector", "")
    if not selector:
        raise ValueError("selector is required")
    page = _page_or_new()
    page.click(selector, timeout=15_000)
    try:
        page.wait_for_load_state("domcontentloaded", timeout=5_000)
    except Exception:
        pass
    nearby = ""
    try:
        nearby = _to_markdown(page.content())[:500]
    except Exception:
        pass
    return {"url_after": page.url, "nearby_text": nearby}


def _handle_fill(payload: dict) -> dict:
    selector = payload.get("selector", "")
    value = payload.get("value", "")
    if not selector:
        raise ValueError("selector is required")
    page = _page_or_new()
    page.fill(selector, value, timeout=15_000)
    return {"ok": True}


def _handle_select(payload: dict) -> dict:
    selector = payload.get("selector", "")
    option = payload.get("option")
    if not selector or option is None:
        raise ValueError("selector + option required")
    page = _page_or_new()
    page.select_option(selector, option, timeout=15_000)
    return {"ok": True}


def _handle_screenshot(payload: dict) -> dict:
    selector = payload.get("selector")
    page = _page_or_new()
    if selector:
        el = page.query_selector(selector)
        if el is None:
            raise ValueError(f"selector not found: {selector}")
        png = el.screenshot(type="png")
    else:
        png = page.screenshot(type="png", full_page=False)
    if len(png) > 2_000_000:
        raise ValueError(f"screenshot too large ({len(png)} bytes) — narrow it with a selector")
    return {"png_b64": base64.b64encode(png).decode("ascii"), "size": len(png)}


def _handle_wait(payload: dict) -> dict:
    selector = payload.get("selector", "")
    timeout = int(payload.get("timeout") or 10) * 1000
    if not selector:
        raise ValueError("selector is required")
    page = _page_or_new()
    try:
        page.wait_for_selector(selector, timeout=timeout, state="visible")
        return {"found": True}
    except Exception:
        return {"found": False}


def _handle_download(payload: dict) -> dict:
    selector = payload.get("selector", "")
    timeout = int(payload.get("timeout") or 30) * 1000
    if not selector:
        raise ValueError("selector is required")
    page = _page_or_new()
    with page.expect_download(timeout=timeout) as dl_info:
        page.click(selector)
    dl = dl_info.value
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", dl.suggested_filename or "download.bin")
    path = os.path.join(_DOWNLOAD_DIR, safe_name)
    dl.save_as(path)
    size = os.path.getsize(path)
    mime = "application/octet-stream"
    try:
        import mimetypes
        mime = mimetypes.guess_type(path)[0] or mime
    except Exception:
        pass
    return {"path": path, "size": size, "mime": mime, "filename": safe_name}


def _handle_eval(payload: dict) -> dict:
    js = payload.get("js", "")
    if not js:
        raise ValueError("js is required")
    page = _page_or_new()
    result = page.evaluate(js)
    # JSON-safe coercion — Playwright returns dicts/lists/primitives.
    try:
        json.dumps(result)
    except Exception:
        result = str(result)
    return {"result": result}


def _handle_storage_load(payload: dict) -> dict:
    """Re-apply a saved storage_state (cookies + localStorage)."""
    global _context, _page
    state = payload.get("state")
    if not isinstance(state, dict):
        raise ValueError("state dict required")
    _ensure_context()
    with _lock:
        # Close the old context + page, open a new one with the state.
        try:
            if _page and not _page.is_closed():
                _page.close()
        except Exception:
            pass
        try:
            _context.close()
        except Exception:
            pass
        _context = _browser.new_context(
            accept_downloads=True,
            viewport={"width": 1280, "height": 800},
            storage_state=state,
        )
        _page = _context.new_page()
    return {"ok": True}


def _handle_storage_dump(_payload: dict) -> dict:
    _ensure_context()
    return {"state": _context.storage_state()}


def _handle_close(_payload: dict) -> dict:
    global _context, _browser, _pw, _page
    with _lock:
        for closer in (_page, _context, _browser, _pw):
            if closer is None:
                continue
            try:
                if hasattr(closer, "close"):
                    closer.close()
                elif hasattr(closer, "stop"):
                    closer.stop()
            except Exception:
                pass
        _page = _context = _browser = _pw = None
    return {"ok": True}


_ROUTES = {
    "/health":         lambda p: {"ok": True},
    "/goto":           _handle_goto,
    "/content":        _handle_content,
    "/click":          _handle_click,
    "/fill":           _handle_fill,
    "/select":         _handle_select,
    "/screenshot":     _handle_screenshot,
    "/wait":           _handle_wait,
    "/download":       _handle_download,
    "/eval":           _handle_eval,
    "/storage/load":   _handle_storage_load,
    "/storage/dump":   _handle_storage_dump,
    "/close":          _handle_close,
}


# ─── HTTP plumbing ───────────────────────────────────────────────────


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        _log.info("%s %s", self.path, args)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        handler = _ROUTES.get(path)
        if handler is None:
            self._respond(404, {"error": f"unknown path {path}"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception as e:
            self._respond(400, {"error": f"bad json: {e}"})
            return
        try:
            result = handler(payload)
            self._respond(200, result)
        except Exception as e:
            _log.exception("%s failed: %s", path, e)
            self._respond(500, {"error": f"{type(e).__name__}: {e}"})

    def do_GET(self):
        # Convenience: /health as GET too for docker HEALTHCHECK.
        if self.path.split("?", 1)[0] == "/health":
            self._respond(200, {"ok": True})
            return
        self._respond(405, {"error": "POST required"})

    def _respond(self, status: int, body: dict):
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    port = int(os.environ.get("BROWSER_SERVER_PORT", "7000"))
    _log.info("RESTai browser micro-server listening on :%d", port)
    server = HTTPServer(("0.0.0.0", port), _Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

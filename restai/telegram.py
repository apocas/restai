import asyncio
import json
import logging
import threading
import requests

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}"

# Global registry of active polling threads: project_id -> TelegramPoller
_pollers: dict[int, "TelegramPoller"] = {}
_pollers_lock = threading.Lock()


def validate_token(token: str) -> dict:
    resp = requests.get(f"{TELEGRAM_API_BASE.format(token=token)}/getMe", timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise ValueError(f"Telegram token validation failed: {data}")
    return data["result"]


def send_message(token: str, chat_id: int, text: str):
    max_len = 4096
    chunks = [text[i : i + max_len] for i in range(0, len(text), max_len)]
    for chunk in chunks:
        resp = requests.post(
            f"{TELEGRAM_API_BASE.format(token=token)}/sendMessage",
            json={"chat_id": chat_id, "text": chunk},
            timeout=30,
        )
        resp.raise_for_status()


def send_typing_action(token: str, chat_id: int):
    try:
        requests.post(
            f"{TELEGRAM_API_BASE.format(token=token)}/sendChatAction",
            json={"chat_id": chat_id, "action": "typing"},
            timeout=5,
        )
    except Exception:
        pass


def get_updates(token: str, offset: int = 0, timeout: int = 30):
    """Returns ``(updates, error)``.

    - ``(list, None)`` on success (list may be empty for a long-poll timeout)
    - ``(None, "<reason>")`` on failure — caller can log/surface the reason
      instead of just "API error".
    """
    try:
        resp = requests.get(
            f"{TELEGRAM_API_BASE.format(token=token)}/getUpdates",
            params={"offset": offset, "timeout": timeout, "allowed_updates": '["message"]'},
            timeout=timeout + 10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("ok"):
            return data.get("result", []), None
        # Telegram returned 200 but ok=false — surface the description it
        # gave us (e.g. "Conflict: terminated by other getUpdates request",
        # "Unauthorized" for a bad token).
        desc = data.get("description") or "unknown error"
        code = data.get("error_code")
        return None, f"Telegram API rejected getUpdates ({code}): {desc}"
    except requests.exceptions.Timeout:
        return [], None  # long-poll timeout is normal — treat as no-updates
    except requests.exceptions.HTTPError as e:
        # Try to extract Telegram's JSON description from the error response.
        detail = ""
        try:
            payload = e.response.json()
            if isinstance(payload, dict):
                detail = payload.get("description") or ""
        except Exception:
            pass
        return None, f"HTTP {getattr(e.response, 'status_code', '?')}: {detail or str(e)}"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


class TelegramPoller:
    """Background thread that polls Telegram for updates and forwards them to a project's chat."""

    def __init__(self, project_id: int, token: str, app):
        self.project_id = project_id
        self.token = token
        self.app = app
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(
            target=self._poll_loop,
            name=f"telegram-poller-{self.project_id}",
            daemon=True,
        )
        self._thread.start()
        logging.info(f"Telegram poller started for project {self.project_id}")

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logging.info(f"Telegram poller stopped for project {self.project_id}")

    def _poll_loop(self):
        offset = 0
        consecutive_errors = 0
        backoff = 1
        while not self._stop_event.is_set():
            updates, err = get_updates(self.token, offset=offset, timeout=30)
            if err is not None:
                consecutive_errors += 1
                logging.warning(f"Telegram poller for project {self.project_id}: {err}")
                if consecutive_errors >= 10:
                    logging.error(f"Telegram poller for project {self.project_id}: too many consecutive errors, stopping")
                    break
                backoff = min(backoff * 2, 300)  # max 5 min
                self._stop_event.wait(backoff)
                continue
            consecutive_errors = 0
            backoff = 1
            for update in updates:
                offset = update["update_id"] + 1
                self._handle_update(update)

    def _handle_update(self, update: dict):
        message = update.get("message")
        if not message:
            return

        text = message.get("text")
        chat_id = message.get("chat", {}).get("id")
        if not text or not chat_id:
            return

        send_typing_action(self.token, chat_id)

        try:
            # Run the async chat_main in a new event loop on this thread
            answer = asyncio.run(self._process_message(text, chat_id))
            if answer:
                send_message(self.token, chat_id, answer)
        except Exception as e:
            logging.exception(f"Telegram message processing error for project {self.project_id}: {e}")
            try:
                send_message(self.token, chat_id, "Sorry, an error occurred processing your message.")
            except Exception:
                pass

    async def _process_message(self, text: str, chat_id: int) -> str | None:
        from restai.database import get_db_wrapper
        from restai.helper import chat_main
        from restai.models.models import ChatModel, User
        from fastapi import BackgroundTasks, Request

        db_wrapper = get_db_wrapper()
        brain = self.app.state.brain

        project = brain.find_project(self.project_id, db_wrapper)
        if project is None:
            return None

        chat_input = ChatModel(question=text, id=f"telegram_{chat_id}", stream=False)
        user = User(id=0, username=f"telegram_{chat_id}", is_admin=False, is_private=False)

        background_tasks = BackgroundTasks()

        # Create a minimal ASGI scope for the Request object
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "app": self.app,
        }
        request = Request(scope)

        response = await chat_main(
            request,
            brain,
            project,
            chat_input,
            user,
            db_wrapper,
            background_tasks,
        )

        # Run any background tasks (logging etc.)
        await background_tasks()

        if isinstance(response, dict):
            return response.get("answer")
        elif hasattr(response, "body"):
            resp_body = json.loads(response.body.decode())
            return resp_body.get("answer")

        return None


def start_poller(project_id: int, token: str, app):
    with _pollers_lock:
        # Stop existing poller for this project if any
        existing = _pollers.get(project_id)
        if existing:
            existing.stop()

        poller = TelegramPoller(project_id, token, app)
        _pollers[project_id] = poller
        poller.start()


def stop_poller(project_id: int):
    with _pollers_lock:
        poller = _pollers.pop(project_id, None)
        if poller:
            poller.stop()


def stop_all_pollers():
    with _pollers_lock:
        for poller in _pollers.values():
            poller.stop()
        _pollers.clear()

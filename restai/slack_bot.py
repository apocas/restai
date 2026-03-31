"""Slack bot integration — connects RestAI projects to Slack channels via Socket Mode."""

import asyncio
import json
import logging
import threading

# Global registry of active Slack bots: project_id -> SlackBot
_bots: dict[int, "SlackBot"] = {}
_bots_lock = threading.Lock()


class SlackBot:
    def __init__(self, project_id: int, bot_token: str, app_token: str, app):
        self.project_id = project_id
        self.bot_token = bot_token
        self.app_token = app_token
        self.app = app
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logging.info("Slack bot started for project %d", self.project_id)

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logging.info("Slack bot stopped for project %d", self.project_id)

    def _run(self):
        try:
            from slack_bolt import App
            from slack_bolt.adapter.socket_mode import SocketModeHandler

            bolt_app = App(token=self.bot_token)

            @bolt_app.event("message")
            def handle_message(event, say):
                # Ignore bot messages to avoid loops
                if event.get("subtype") == "bot_message" or event.get("bot_id"):
                    return

                text = event.get("text", "")
                channel = event.get("channel", "")
                if not text or not channel:
                    return

                try:
                    answer = asyncio.run(self._process_message(text, channel))
                    if answer:
                        say(answer)
                except Exception as e:
                    logging.exception("Slack message processing error for project %d: %s", self.project_id, e)
                    try:
                        say("Sorry, an error occurred processing your message.")
                    except Exception:
                        pass

            handler = SocketModeHandler(bolt_app, self.app_token)
            handler.start()

            # Block until stop is requested
            self._stop_event.wait()

            try:
                handler.close()
            except Exception:
                pass

        except Exception as e:
            logging.exception("Slack bot failed for project %d: %s", self.project_id, e)

    async def _process_message(self, text: str, channel_id: str) -> str | None:
        from restai.database import get_db_wrapper
        from restai.helper import chat_main
        from restai.models.models import ChatModel, User
        from fastapi import BackgroundTasks, Request

        db_wrapper = get_db_wrapper()
        brain = self.app.state.brain

        project = brain.find_project(self.project_id, db_wrapper)
        if project is None:
            return None

        chat_input = ChatModel(question=text, id=f"slack_{channel_id}", stream=False)
        user = User(id=0, username=f"slack_{channel_id}", is_admin=False, is_private=False)

        background_tasks = BackgroundTasks()

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

        await background_tasks()

        if isinstance(response, dict):
            return response.get("answer")
        elif hasattr(response, "body"):
            resp_body = json.loads(response.body.decode())
            return resp_body.get("answer")

        return None


def start_slack_bot(project_id: int, bot_token: str, app_token: str, app):
    with _bots_lock:
        existing = _bots.get(project_id)
        if existing:
            existing.stop()

        bot = SlackBot(project_id, bot_token, app_token, app)
        _bots[project_id] = bot
        bot.start()


def stop_slack_bot(project_id: int):
    with _bots_lock:
        bot = _bots.pop(project_id, None)
        if bot:
            bot.stop()


def stop_all_slack_bots():
    with _bots_lock:
        for bot in _bots.values():
            bot.stop()
        _bots.clear()

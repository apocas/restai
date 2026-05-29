"""A tiny, dependency-light RESTai client (just `requests`).

It is intentionally small and readable — the point is to show how the current
RESTai REST API is shaped, not to be a full SDK. The other Python examples
import from here.

Key things this demonstrates about the *current* API (vs. the old examples):
  - Projects are addressed by integer **id**, never by name, e.g.
    POST /projects/{id}/chat
  - Chatting goes through /chat (the old /question is deprecated). The request
    field is `question`; the reply is {"answer", "sources", "type", "id"}.
  - Creating a project requires a `team_id`, and the team must have been
    granted access to the LLM (and embeddings, for RAG).
  - Nothing is pre-seeded: you discover LLMs/embeddings via GET /llms and
    GET /embeddings.

Auth: pass an `api_key` (sent as `Authorization: Bearer ...`) or fall back to
HTTP Basic with `user`/`password`.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterator, Optional

import requests


class RestaiError(RuntimeError):
    """Raised when the server returns a non-2xx response."""

    def __init__(self, status: int, detail: Any):
        self.status = status
        self.detail = detail
        super().__init__(f"HTTP {status}: {detail}")


class RestaiClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        verify: bool = True,
        timeout: int = 120,
    ):
        self.base_url = (base_url or os.getenv("RESTAI_URL", "http://localhost:9000")).rstrip("/")
        self.api_key = api_key or os.getenv("RESTAI_API_KEY")
        self.user = user or os.getenv("RESTAI_USER", "admin")
        self.password = password or os.getenv("RESTAI_PASSWORD", "admin")
        self.verify = verify
        self.timeout = timeout

        self._session = requests.Session()
        if self.api_key:
            self._session.headers["Authorization"] = f"Bearer {self.api_key}"
        else:
            self._session.auth = (self.user, self.password)

    # -- low level ---------------------------------------------------------

    def request(self, method: str, path: str, **kwargs) -> Any:
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("verify", self.verify)
        resp = self._session.request(method, f"{self.base_url}{path}", **kwargs)
        if not resp.ok:
            try:
                detail = resp.json().get("detail", resp.text)
            except ValueError:
                detail = resp.text
            raise RestaiError(resp.status_code, detail)
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.text

    def get(self, path, **kw):
        return self.request("GET", path, **kw)

    def post(self, path, **kw):
        return self.request("POST", path, **kw)

    def patch(self, path, **kw):
        return self.request("PATCH", path, **kw)

    def delete(self, path, **kw):
        return self.request("DELETE", path, **kw)

    # -- discovery ---------------------------------------------------------

    def list_llms(self) -> list[dict]:
        return self.get("/llms")

    def list_embeddings(self) -> list[dict]:
        return self.get("/embeddings")

    def list_teams(self) -> list[dict]:
        return self.get("/teams").get("teams", [])

    def pick_llm(self, prefer: Optional[str] = None, vision: bool = False) -> str:
        """Return an LLM name to use. Honors `prefer`/env, else auto-discovers.

        For `vision=True`, prefers models that look multimodal (class name or
        model name hints). It's a heuristic — set RESTAI_VISION_LLM to be sure.
        """
        prefer = prefer or os.getenv("RESTAI_VISION_LLM" if vision else "RESTAI_LLM")
        llms = self.list_llms()
        if not llms:
            raise RestaiError(404, "No LLMs configured. Add one in /admin → Settings → LLMs.")
        names = [l["name"] for l in llms]
        if prefer:
            if prefer not in names:
                raise RestaiError(404, f"LLM '{prefer}' not found. Available: {names}")
            return prefer
        if vision:
            hints = ("multimodal", "vision", "gpt-4o", "gpt-4.1", "gemini", "claude", "llava", "pixtral")
            for l in llms:
                hay = f"{l['name']} {l.get('class_name', '')}".lower()
                if any(h in hay for h in hints):
                    return l["name"]
        return names[0]

    def pick_embeddings(self, prefer: Optional[str] = None) -> str:
        prefer = prefer or os.getenv("RESTAI_EMBEDDINGS")
        embs = self.list_embeddings()
        if not embs:
            raise RestaiError(404, "No embeddings configured. Add one in /admin → Settings → Embeddings.")
        names = [e["name"] for e in embs]
        if prefer:
            if prefer not in names:
                raise RestaiError(404, f"Embeddings '{prefer}' not found. Available: {names}")
            return prefer
        return names[0]

    # -- teams -------------------------------------------------------------

    def ensure_team(self, name: str, llms: list[str], embeddings: Optional[list[str]] = None) -> int:
        """Find a team by name (or create it) and make sure it can use the
        given models. Returns the team id.

        Creating a team with `llms`/`embeddings` name lists grants access in
        one shot. If the team already exists, missing grants are added via the
        per-resource attach endpoints (which take ids, so we resolve them).
        """
        embeddings = embeddings or []
        for team in self.list_teams():
            if team["name"] == name:
                self._grant_missing(team, llms, embeddings)
                return team["id"]

        team = self.post(
            "/teams",
            json={"name": name, "description": "RESTai examples", "llms": llms, "embeddings": embeddings},
        )
        return team["id"]

    def _grant_missing(self, team: dict, llms: list[str], embeddings: list[str]) -> None:
        team_id = team["id"]
        have_llms = {l["name"] for l in team.get("llms", [])}
        have_embs = {e["name"] for e in team.get("embeddings", [])}

        if set(llms) - have_llms:
            by_name = {l["name"]: l["id"] for l in self.list_llms()}
            for name in set(llms) - have_llms:
                if name in by_name:
                    self.post(f"/teams/{team_id}/llms/{by_name[name]}")
        if set(embeddings) - have_embs:
            by_name = {e["name"]: e["id"] for e in self.list_embeddings()}
            for name in set(embeddings) - have_embs:
                if name in by_name:
                    self.post(f"/teams/{team_id}/embeddings/{by_name[name]}")

    # -- projects ----------------------------------------------------------

    def create_project(
        self,
        name: str,
        ptype: str,
        team_id: int,
        llm: Optional[str] = None,
        embeddings: Optional[str] = None,
        vectorstore: Optional[str] = None,
        human_name: Optional[str] = None,
        human_description: Optional[str] = None,
    ) -> int:
        """Create a project and return its integer id."""
        body = {
            "name": name,
            "type": ptype,
            "team_id": team_id,
            "llm": llm,
            "embeddings": embeddings,
            "vectorstore": vectorstore,
            "human_name": human_name,
            "human_description": human_description,
        }
        body = {k: v for k, v in body.items() if v is not None}
        return self.post("/projects", json=body)["project"]

    def find_project(self, name: str) -> Optional[dict]:
        """Return the first project matching `name`, or None."""
        page = self.get("/projects", params={"start": 0, "end": 1000})
        for p in page.get("projects", []):
            if p["name"] == name:
                return p
        return None

    def get_or_create_project(self, name: str, ptype: str, team_id: int, **kw) -> int:
        existing = self.find_project(name)
        if existing:
            return existing["id"]
        return self.create_project(name, ptype, team_id, **kw)

    def edit_project(self, project_id: int, **patch) -> Any:
        return self.patch(f"/projects/{project_id}", json=patch)

    def delete_project(self, project_id: int) -> Any:
        return self.delete(f"/projects/{project_id}")

    # -- knowledge (RAG) ---------------------------------------------------

    def ingest_text(self, project_id: int, text: str, source: str, **opts) -> dict:
        return self.post(f"/projects/{project_id}/embeddings/ingest/text",
                         json={"text": text, "source": source, **opts})

    def ingest_url(self, project_id: int, url: str, **opts) -> dict:
        return self.post(f"/projects/{project_id}/embeddings/ingest/url",
                         json={"url": url, **opts})

    def search(self, project_id: int, text: str, k: int = 4, score: float = 0.0) -> list[dict]:
        out = self.post(f"/projects/{project_id}/embeddings/search",
                        json={"text": text, "k": k, "score": score})
        return out.get("embeddings", [])

    # -- chat --------------------------------------------------------------

    def chat(self, project_id: int, question: str, chat_id: Optional[str] = None,
             image: Optional[str] = None, system: Optional[str] = None, **opts) -> dict:
        """One non-streaming chat turn. Returns {"answer", "sources", "type", "id"}.

        Pass the returned "id" back as `chat_id` to continue the conversation.
        `image` is a base64 string or an http(s) URL (vision models only).
        """
        body: dict[str, Any] = {"question": question, **opts}
        if chat_id:
            body["id"] = chat_id
        if image:
            body["image"] = image
        if system:
            body["system"] = system
        return self.post(f"/projects/{project_id}/chat", json=body)

    def chat_stream(self, project_id: int, question: str, chat_id: Optional[str] = None,
                    **opts) -> Iterator[dict]:
        """Stream a chat turn over Server-Sent Events.

        Yields parsed JSON objects as they arrive. RESTai emits:
          - {"text": "..."}        incremental answer tokens (concatenate them)
          - {"plan": [...]}        (agent, auto_plan) the upfront plan
          - {"tool": ..., ...}     (agent) tool-call activity
          - {"answer": ..., ...}   the final, complete object (sent last)

        Omit `chat_id` for a simple one-shot stream. When you DO pass one, the
        server keeps a resumable buffer of the in-flight stream for ~5 minutes
        so a dropped connection can re-attach (send the SSE `Last-Event-ID`) and
        tail the rest without re-running the model. Because of that buffer, a
        second streaming POST with the same id within the window re-attaches to
        the previous turn — for distinct back-to-back streaming turns, use a new
        id each time (or POST /projects/{id}/chat/stop to release it first).
        """
        body: dict[str, Any] = {"question": question, "stream": True, **opts}
        if chat_id:
            body["id"] = chat_id
        with self._session.post(
            f"{self.base_url}/projects/{project_id}/chat",
            json=body, stream=True, timeout=self.timeout, verify=self.verify,
            headers={"Accept": "text/event-stream"},
        ) as resp:
            if not resp.ok:
                raise RestaiError(resp.status_code, resp.text)
            for raw in resp.iter_lines(decode_unicode=True):
                if not raw or not raw.startswith("data:"):
                    continue
                payload = raw[len("data:"):].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    yield json.loads(payload)
                except json.JSONDecodeError:
                    continue

    # -- tools -------------------------------------------------------------

    def classify(self, sequence: str, labels: list[str], model: Optional[str] = None) -> dict:
        """Zero-shot classification. Returns {"sequence", "labels", "scores", "model"}
        with labels ordered by descending confidence."""
        body = {"sequence": sequence, "labels": labels}
        if model:
            body["model"] = model
        return self.post("/tools/classifier", json=body)


def stream_answer(events: Iterator[dict]) -> str:
    """Consume a chat_stream(), print tokens live, return the final answer.

    Handy default behavior for a CLI: prints incremental text as it streams and
    returns the authoritative final answer once the stream closes.
    """
    final = None
    streamed = []
    for ev in events:
        if "text" in ev:
            print(ev["text"], end="", flush=True)
            streamed.append(ev["text"])
        elif "answer" in ev:
            final = ev
    print()
    return (final or {}).get("answer", "".join(streamed))

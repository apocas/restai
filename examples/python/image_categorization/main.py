"""Categorize images by combining a vision model with the zero-shot classifier.

Two RESTai capabilities, chained:
  1. Vision  — ask a vision-capable LLM to describe each image (POST /projects/{id}/chat
     with a base64 `image`).
  2. Classify — feed that description to the built-in zero-shot classifier
     (POST /tools/classifier) against your candidate labels.

Self-contained (`requests` + `pillow`) so the raw API calls are easy to read.

Config via env (see ../README.md):
    RESTAI_URL, RESTAI_API_KEY (or RESTAI_USER/RESTAI_PASSWORD),
    RESTAI_VISION_LLM, RESTAI_PROJECT_ID (reuse an existing project)

    python main.py
"""

import base64
import os
from io import BytesIO

import requests
from PIL import Image

LABELS = ["overcast", "sunny"]

BASE_URL = os.getenv("RESTAI_URL", "http://localhost:9000").rstrip("/")
API_KEY = os.getenv("RESTAI_API_KEY")

session = requests.Session()
if API_KEY:
    session.headers["Authorization"] = f"Bearer {API_KEY}"
else:
    session.auth = (os.getenv("RESTAI_USER", "admin"), os.getenv("RESTAI_PASSWORD", "admin"))


def _api(method: str, path: str, **kw):
    r = session.request(method, f"{BASE_URL}{path}", timeout=300, **kw)
    r.raise_for_status()
    return r.json()


def ensure_vision_project() -> int:
    """Reuse RESTAI_PROJECT_ID if given, else create/find an agent project
    backed by a vision-capable LLM."""
    if os.getenv("RESTAI_PROJECT_ID"):
        return int(os.environ["RESTAI_PROJECT_ID"])

    llms = _api("GET", "/llms")
    if not llms:
        raise SystemExit("No LLMs configured. Add a vision-capable LLM in /admin first.")
    want = os.getenv("RESTAI_VISION_LLM")
    names = [l["name"] for l in llms]
    if want and want not in names:
        raise SystemExit(f"LLM '{want}' not found. Available: {names}")
    if not want:
        hints = ("multimodal", "vision", "gpt-4o", "gpt-4.1", "gemini", "claude", "llava", "pixtral")
        want = next((l["name"] for l in llms
                     if any(h in f"{l['name']} {l.get('class_name','')}".lower() for h in hints)),
                    names[0])
    print(f"→ vision LLM: {want}  (override with RESTAI_VISION_LLM)")

    teams = _api("GET", "/teams").get("teams", [])
    team = next((t for t in teams if t["name"] == "examples"), None)
    if team is None:
        team = _api("POST", "/teams", json={"name": "examples", "llms": [want]})
    elif want not in {l["name"] for l in team.get("llms", [])}:
        by_name = {l["name"]: l["id"] for l in llms}
        _api("POST", f"/teams/{team['id']}/llms/{by_name[want]}")

    for p in _api("GET", "/projects", params={"start": 0, "end": 1000}).get("projects", []):
        if p["name"] == "examples_vision":
            return p["id"]
    return _api("POST", "/projects", json={
        "name": "examples_vision", "type": "agent", "team_id": team["id"], "llm": want,
        "human_name": "Vision", "human_description": "Vision example project",
    })["project"]


def image_to_base64(path: str) -> str:
    with Image.open(path) as img:
        with BytesIO() as buf:
            img.convert("RGB").save(buf, "JPEG")
            return base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    print(f"→ RESTai at {BASE_URL}")
    project_id = ensure_vision_project()

    images_dir = os.path.join(os.path.dirname(__file__), "images")
    for name in sorted(os.listdir(images_dir)):
        if name.startswith("."):
            continue
        img_b64 = image_to_base64(os.path.join(images_dir, name))

        # 1. Describe the image with the vision model.
        description = _api("POST", f"/projects/{project_id}/chat",
                           json={"question": "Describe this image in detail.", "image": img_b64})["answer"]

        # 2. Classify the description into one of LABELS.
        result = _api("POST", "/tools/classifier", json={"sequence": description, "labels": LABELS})

        print("─" * 40)
        print(name)
        for label, score in zip(result["labels"], result["scores"]):
            print(f"  {label:<10} {score:.3f}")


if __name__ == "__main__":
    main()

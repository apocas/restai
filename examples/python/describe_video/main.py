"""Describe a video (local mp4 or YouTube) with RESTai vision.

Samples frames from the video, asks a vision-capable LLM to describe each one,
then merges those descriptions into a single narrative. Both steps go through the
same `agent` project's /chat endpoint — multimodal models describe images and also
write the final summary.

Self-contained (only `requests` + `opencv-python`, plus `cap-from-youtube` for the
YouTube path) so you can read the raw API calls. The vision request is just a normal
chat with a base64 image in the `image` field:

    POST /projects/{id}/chat   {"question": "...", "image": "<base64>"}

Config via env (see ../README.md):
    RESTAI_URL, RESTAI_API_KEY (or RESTAI_USER/RESTAI_PASSWORD),
    RESTAI_VISION_LLM (a vision-capable model name), RESTAI_PROJECT_ID (reuse one)

    python main.py
"""

import base64
import os

import cv2
import requests

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


def describe_frame(project_id: int, frame) -> str:
    _, buffer = cv2.imencode(".jpg", frame)
    image_b64 = base64.b64encode(buffer).decode("utf-8")
    out = _api("POST", f"/projects/{project_id}/chat",
               json={"question": "Describe this image in detail.", "image": image_b64})
    return out["answer"]


def fetch_frames(cap, interval=10):
    if not cap.isOpened():
        raise SystemExit("Could not open the video.")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_skip = int(fps * interval)
    frames, idx = [], 0
    while cap.isOpened():
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
        idx += frame_skip
    cap.release()
    return frames


def summarize(project_id: int, descriptions: list[str]) -> str:
    prompt = (
        "These are descriptions of frames sampled from a video, in order. Write a single "
        "cohesive description of the video. Don't mention frames, scenes, or images.\n\n"
        + "\n".join(f"- {d}" for d in descriptions)
    )
    return _api("POST", f"/projects/{project_id}/chat", json={"question": prompt})["answer"]


def describe_video(cap, interval=10) -> str:
    project_id = ensure_vision_project()
    frames = fetch_frames(cap, interval)
    print(f"→ sampled {len(frames)} frame(s)")
    descriptions = [describe_frame(project_id, f) for f in frames]
    return summarize(project_id, descriptions)


if __name__ == "__main__":
    print(f"→ RESTai at {BASE_URL}")
    print(describe_video(cv2.VideoCapture("sample.mp4"), interval=10))

    # YouTube variant (needs `pip install cap-from-youtube`):
    # from cap_from_youtube import cap_from_youtube
    # print(describe_video(cap_from_youtube("https://youtu.be/LXb3EKWsInQ", "480p"), interval=30))

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from restai.image.providers import minimax
from restai.models.models import ImageGeneratorModelCreate, User
from restai.routers import image


@pytest.fixture
def generate(monkeypatch):
    """Exercise the named generator route with an in-memory row and a mocked upstream."""
    app = FastAPI()
    app.include_router(image.router)
    app.state.brain = None
    db = Mock()
    app.dependency_overrides[image.get_current_username] = lambda: User(id=1, username="admin", is_admin=True)
    app.dependency_overrides[image.get_db_wrapper] = lambda: db
    monkeypatch.setattr(image, "log_direct_usage", Mock())

    def run(upstream_status, upstream_body, **options):
        generator = ImageGeneratorModelCreate(name="h3", class_name="minimax", options=options)
        db.get_image_generator_by_name.return_value = SimpleNamespace(
            class_name=generator.class_name, enabled=True, options=json.dumps(options),
        )
        upstream = requests.Response()
        upstream.status_code = upstream_status
        upstream._content = json.dumps(upstream_body).encode()
        post = Mock(return_value=upstream)
        monkeypatch.setattr(minimax.requests, "post", post)
        with TestClient(app) as client:
            response = client.post("/image/h3/generate", json={"prompt": "a red fox"})
        db.get_image_generator_by_name.assert_called_once_with("h3")
        post.assert_called_once()
        return response, post.call_args

    return run


@pytest.mark.parametrize(("options", "host", "model", "response_metadata"), [
    ({}, "api.minimax.io", "MiniMax-H3-Image", {"output_format": "png"}),
    ({"base_url": "https://api.minimax.cn/v1/", "model": "MiniMax-H3-Image-Highspeed"},
     "api.minimax.cn", "MiniMax-H3-Image-Highspeed", {}),
])
def test_generate_png(generate, options, host, model, response_metadata):
    response, call = generate(
        200, {"data": [{"b64_json": "aW1hZ2U="}], **response_metadata}, api_key="test", **options,
    )
    assert response.status_code == 200
    assert response.json() == {"image": "aW1hZ2U="}
    assert call.args == (f"https://{host}/v1/images/generations",)
    assert call.kwargs == {
        "headers": {"Authorization": "Bearer test"},
        "json": {"model": model, "prompt": "a red fox", "response_format": "b64_json", "output_format": "png"},
        "timeout": 600, "allow_redirects": False,
    }


@pytest.mark.parametrize(("upstream_status", "body", "status", "detail"), [
    (429, {"error": {"message": "rate limit exceeded"}}, 429, "rate limit exceeded"),
    (200, {"data": [{"error": {"message": "image failed safety check"}}]}, 502, "image failed safety check"),
    (200, {"data": [{"b64_json": "invalid!"}], "output_format": "png"}, 502, "invalid base64"),
    (200, {"data": [{"b64_json": "aW1hZ2U="}], "output_format": "jpeg"}, 502, "no PNG image"),
    (200, {"data": []}, 502, "unexpected image list"),
])
def test_generate_errors(generate, upstream_status, body, status, detail):
    response, _ = generate(upstream_status, body, api_key="test")
    assert response.status_code == status
    assert detail in response.json()["detail"]

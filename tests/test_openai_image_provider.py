from __future__ import annotations

import base64
import json

import httpx
import pytest
from openai import OpenAI

from restai.image.providers import openai
from restai.models.models import ImageModel


@pytest.fixture
def sdk_requests(monkeypatch):
    requests = []
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aXioAAAAASUVORK5CYII="
    )

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"created": 1, "data": [{"b64_json": base64.b64encode(png).decode()}]},
        )

    clients = []

    def make_client(**kwargs):
        client = OpenAI(
            **kwargs,
            http_client=httpx.Client(transport=httpx.MockTransport(respond)),
            max_retries=0,
        )
        clients.append(client)
        return client

    monkeypatch.setattr(openai, "OpenAI", make_client)
    yield requests, png
    for client in clients:
        client.close()


@pytest.mark.parametrize("model", ["gpt-image-2.6-sunburst", "gpt-image-2.6-flare"])
@pytest.mark.parametrize("extra", [{}, {"size": "1536x1024", "quality": "high"}])
def test_gpt_image_request_and_png_response(sdk_requests, model, extra):
    requests, png = sdk_requests
    options = {"api_key": "sk-test", "model": model, **extra}

    result = openai.generate(options, ImageModel(prompt="draw a blue square"))

    assert result == (png, "image/png")
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://api.openai.com/v1/images/generations"
    assert request.headers["Authorization"] == "Bearer sk-test"
    assert json.loads(request.content) == {"model": model, "prompt": "draw a blue square", "n": 1, **extra}
    assert options == {"api_key": "sk-test", "model": model, **extra}


def test_custom_endpoint_keeps_explicit_model(sdk_requests):
    requests, png = sdk_requests

    result = openai.generate(
        {"api_key": "sk-test", "model": "custom-image-model", "base_url": "https://images.example/v1"},
        ImageModel(prompt="draw a blue square"),
    )

    assert result == (png, "image/png")
    assert len(requests) == 1
    assert str(requests[0].url) == "https://images.example/v1/images/generations"
    assert json.loads(requests[0].content)["model"] == "custom-image-model"

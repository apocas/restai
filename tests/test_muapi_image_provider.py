from __future__ import annotations

import pytest

from restai.image import dispatch as image_dispatch
from restai.image.dispatch import ImageProviderError
from restai.image.providers import muapi
from restai.models.models import ImageGeneratorModelCreate, ImageModel


class FakeResponse:
    def __init__(self, status_code=200, body=None, content=b"", headers=None):
        self.status_code = status_code
        self._body = body
        self.content = content
        self.headers = headers or {}

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._body


def test_generate_uses_catalog_endpoint_polls_and_does_not_forward_key(monkeypatch):
    post_calls = []
    get_calls = []

    def fake_post(url, **kwargs):
        post_calls.append((url, kwargs))
        return FakeResponse(body={"request_id": "request-123", "status": "queued"})

    responses = [
        FakeResponse(body={"status": "processing"}),
        FakeResponse(body={"status": "completed", "outputs": ["https://cdn.example/image.png"]}),
        FakeResponse(content=b"png-bytes", headers={"Content-Type": "image/png"}),
    ]

    def fake_get(url, **kwargs):
        get_calls.append((url, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(muapi.requests, "post", fake_post)
    monkeypatch.setattr(muapi.requests, "get", fake_get)
    monkeypatch.setattr(muapi.time, "sleep", lambda _seconds: None)

    result = muapi.generate(
        {
            "api_key": "muapi-test-key",
            "endpoint": "/api/v1/flux-dev",
            "base_url": "https://api.muapi.ai",
            "poll_interval": 0.1,
        },
        ImageModel(prompt="draw a blue square"),
    )

    assert result == (b"png-bytes", "image/png")
    assert post_calls[0][0] == "https://api.muapi.ai/api/v1/flux-dev"
    assert post_calls[0][1]["headers"]["x-api-key"] == "muapi-test-key"
    assert post_calls[0][1]["json"] == {"prompt": "draw a blue square"}
    assert get_calls[0][0] == "https://api.muapi.ai/api/v1/predictions/request-123/result"
    assert "headers" in get_calls[0][1]
    assert "headers" not in get_calls[-1][1]


def test_model_name_is_normalized_to_one_versioned_endpoint(monkeypatch):
    calls = []
    monkeypatch.setattr(
        muapi.requests,
        "post",
        lambda url, **kwargs: calls.append((url, kwargs))
        or FakeResponse(body={"request_id": "request-123"}),
    )
    monkeypatch.setattr(
        muapi.requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(
            body={"status": "completed", "outputs": ["https://cdn.example/image.png"]}
        ),
    )
    monkeypatch.setattr(muapi.time, "sleep", lambda _seconds: None)

    muapi.generate(
        {"api_key": "muapi-test-key", "model": "flux-dev", "poll_interval": 0.1},
        ImageModel(prompt="test"),
    )

    assert calls[0][0] == "https://api.muapi.ai/api/v1/flux-dev"


def test_generate_maps_upstream_rate_limit(monkeypatch):
    monkeypatch.setattr(
        muapi.requests,
        "post",
        lambda *_args, **_kwargs: FakeResponse(status_code=429, body={"message": "slow down"}),
    )

    with pytest.raises(ImageProviderError) as error:
        muapi.generate({"api_key": "muapi-test-key", "model": "flux-dev"}, ImageModel(prompt="test"))

    assert error.value.status_code == 429
    assert error.value.message == "MuAPI image API: slow down"


def test_generate_rejects_non_https_output(monkeypatch):
    monkeypatch.setattr(
        muapi.requests,
        "post",
        lambda *_args, **_kwargs: FakeResponse(body={"request_id": "request-123"}),
    )
    monkeypatch.setattr(
        muapi.requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(
            body={"status": "completed", "outputs": ["http://cdn.example/image.png"]}
        ),
    )
    monkeypatch.setattr(muapi.time, "sleep", lambda _seconds: None)

    with pytest.raises(RuntimeError, match="non-HTTPS output URL"):
        muapi.generate({"api_key": "muapi-test-key", "model": "flux-dev"}, ImageModel(prompt="test"))


def test_muapi_is_a_valid_image_generator_class():
    model = ImageGeneratorModelCreate(
        name="muapi-flux",
        class_name="muapi",
        options={"api_key": "muapi-test-key", "model": "flux-dev"},
    )
    assert model.class_name == "muapi"


def test_dispatch_routes_muapi_provider(monkeypatch):
    class FakeDatabase:
        @staticmethod
        def get_image_generator_by_name(name):
            assert name == "muapi-flux"
            return type("ImageGenerator", (), {"class_name": "muapi", "enabled": True})()

    options = {"api_key": "muapi-test-key", "model": "flux-dev"}
    calls = []
    monkeypatch.setattr(image_dispatch, "_load_options", lambda _row: options)
    monkeypatch.setattr(
        muapi,
        "generate",
        lambda provider_options, image_model: calls.append((provider_options, image_model))
        or (b"png-bytes", "image/png"),
    )

    image_model = ImageModel(prompt="draw a blue square")
    result = image_dispatch.generate_image("muapi-flux", image_model, brain=None, db_wrapper=FakeDatabase())

    assert result == (b"png-bytes", "image/png")
    assert calls == [(options, image_model)]

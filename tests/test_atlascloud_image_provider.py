from __future__ import annotations

import pytest

from restai.image import dispatch as image_dispatch
from restai.image.dispatch import ImageProviderError
from restai.image.providers import atlascloud
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


def test_generate_submits_polls_and_downloads_without_forwarding_key(monkeypatch):
    post_calls = []
    get_calls = []

    def fake_post(url, **kwargs):
        post_calls.append((url, kwargs))
        return FakeResponse(
            body={
                "code": 200,
                "data": {
                    "id": "prediction-123",
                    "status": "created",
                    "urls": {"get": "/api/v1/model/prediction/prediction-123"},
                },
            }
        )

    responses = [
        FakeResponse(body={"code": 200, "data": {"id": "prediction-123", "status": "processing"}}),
        FakeResponse(
            body={
                "code": 200,
                "data": {
                    "id": "prediction-123",
                    "status": "completed",
                    "outputs": ["https://cdn.example/image.png"],
                },
            }
        ),
        FakeResponse(content=b"png-bytes", headers={"Content-Type": "image/png"}),
    ]

    def fake_get(url, **kwargs):
        get_calls.append((url, kwargs))
        return responses.pop(0)

    monkeypatch.setattr(atlascloud.requests, "post", fake_post)
    monkeypatch.setattr(atlascloud.requests, "get", fake_get)
    monkeypatch.setattr(atlascloud.time, "sleep", lambda _seconds: None)

    result = atlascloud.generate(
        {
            "api_key": "atlas-test-key",
            "model": "qwen-image-3.0/text-to-image",
            "base_url": "https://api.atlascloud.ai",
            "size": "1024x1024",
            "poll_interval": 0.1,
        },
        ImageModel(prompt="draw a blue square"),
    )

    assert result == (b"png-bytes", "image/png")
    assert post_calls[0][0] == "https://api.atlascloud.ai/api/v1/model/generateImage"
    assert post_calls[0][1]["json"] == {
        "model": "qwen-image-3.0/text-to-image",
        "prompt": "draw a blue square",
        "n": 1,
        "size": "1024*1024",
    }
    assert get_calls[0][0] == "https://api.atlascloud.ai/api/v1/model/prediction/prediction-123"
    assert "headers" not in get_calls[-1][1]


def test_generate_maps_upstream_rate_limit(monkeypatch):
    monkeypatch.setattr(
        atlascloud.requests,
        "post",
        lambda *_args, **_kwargs: FakeResponse(
            status_code=429,
            body={"message": "slow down"},
        ),
    )

    with pytest.raises(ImageProviderError) as error:
        atlascloud.generate(
            {"api_key": "atlas-test-key", "model": "qwen-image-3.0/text-to-image"},
            ImageModel(prompt="test"),
        )

    assert error.value.status_code == 429
    assert error.value.message == "Atlas Cloud image API: slow down"


def test_generate_rejects_cross_origin_polling_url(monkeypatch):
    monkeypatch.setattr(
        atlascloud.requests,
        "post",
        lambda *_args, **_kwargs: FakeResponse(
            body={
                "id": "prediction-123",
                "status": "created",
                "urls": {"get": "https://untrusted.example/prediction-123"},
            },
        ),
    )

    with pytest.raises(RuntimeError, match="cross-origin polling URL"):
        atlascloud.generate(
            {"api_key": "atlas-test-key", "model": "qwen-image-3.0/text-to-image"},
            ImageModel(prompt="test"),
        )


def test_atlascloud_is_a_valid_image_generator_class():
    model = ImageGeneratorModelCreate(
        name="atlas-qwen-image",
        class_name="atlascloud",
        options={"api_key": "atlas-test-key", "model": "qwen-image-3.0/text-to-image"},
    )
    assert model.class_name == "atlascloud"


def test_dispatch_routes_atlascloud_provider(monkeypatch):
    class FakeDatabase:
        @staticmethod
        def get_image_generator_by_name(name):
            assert name == "atlas-qwen-image"
            return type(
                "ImageGenerator", (), {"class_name": "atlascloud", "enabled": True}
            )()

    options = {"api_key": "atlas-test-key", "model": "qwen-image-3.0/text-to-image"}
    calls = []
    monkeypatch.setattr(image_dispatch, "_load_options", lambda _row: options)
    monkeypatch.setattr(
        atlascloud,
        "generate",
        lambda provider_options, image_model: calls.append((provider_options, image_model))
        or (b"png-bytes", "image/png"),
    )

    image_model = ImageModel(prompt="draw a blue square")
    result = image_dispatch.generate_image(
        "atlas-qwen-image", image_model, brain=None, db_wrapper=FakeDatabase()
    )

    assert result == (b"png-bytes", "image/png")
    assert calls == [(options, image_model)]

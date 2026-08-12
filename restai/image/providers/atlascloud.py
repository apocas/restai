"""Atlas Cloud asynchronous image generation provider."""

from __future__ import annotations

import logging
import time
from urllib.parse import quote, urljoin, urlsplit

import requests

from restai.image.dispatch import ImageProviderError
from restai.models.models import ImageModel

logger = logging.getLogger(__name__)

_SUCCESS_STATUSES = {"completed", "succeeded", "success", "done"}
_FAILURE_STATUSES = {"failed", "failure", "error", "cancelled", "canceled"}


def _message(response: requests.Response, fallback: str) -> str:
    try:
        body = response.json()
    except ValueError:
        return fallback
    if isinstance(body, dict):
        detail = body.get("message") or body.get("detail") or body.get("error")
        if isinstance(detail, dict):
            detail = detail.get("message")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    return fallback


def _raise_http_error(response: requests.Response) -> None:
    upstream = response.status_code
    status = upstream if 400 <= upstream < 500 else 502
    message = _message(response, f"upstream returned HTTP {upstream}")
    logger.warning("Atlas Cloud image generation failed (%s): %s", upstream, message)
    raise ImageProviderError(status, f"Atlas Cloud image API: {message}")


def _prediction(response: requests.Response) -> dict:
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("Atlas Cloud image API returned invalid JSON.") from exc
    if not isinstance(body, dict):
        raise RuntimeError("Atlas Cloud image API returned an invalid response.")
    if "code" in body and str(body.get("code")) != "200":
        message = body.get("message") or "request was not successful"
        raise RuntimeError(f"Atlas Cloud image API: {message}")
    data = body.get("data")
    return data if isinstance(data, dict) else body


def _outputs(prediction: dict) -> list[str]:
    outputs = prediction.get("outputs")
    if not isinstance(outputs, list):
        output = prediction.get("output")
        outputs = output if isinstance(output, list) else [output] if output else []
    return [str(item).strip() for item in outputs if str(item).strip()]


def _atlas_size(value: object) -> str | None:
    size = str(value or "").strip()
    return size.replace("x", "*") if size else None


def generate(options: dict, image_model: ImageModel) -> tuple[bytes, str]:
    api_key = str(options.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("Atlas Cloud image generator: `api_key` is required in options.")

    model = str(options.get("model") or "").strip()
    if not model:
        raise RuntimeError("Atlas Cloud image generator: `model` is required in options.")

    base_url = str(options.get("base_url") or "https://api.atlascloud.ai").rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "prompt": image_model.prompt, "n": 1}
    size = _atlas_size(options.get("size"))
    if size:
        payload["size"] = size

    response = requests.post(
        f"{base_url}/api/v1/model/generateImage",
        headers=headers,
        json=payload,
        timeout=30,
    )
    if not response.ok:
        _raise_http_error(response)
    prediction = _prediction(response)
    prediction_id = str(prediction.get("id") or prediction.get("request_id") or "").strip()
    outputs = _outputs(prediction)

    if not outputs:
        if not prediction_id:
            raise RuntimeError("Atlas Cloud image API response is missing a prediction id.")
        urls = prediction.get("urls")
        result_path = str(urls.get("get") or "").strip() if isinstance(urls, dict) else ""
        result_url = (
            result_path
            if result_path.startswith(("http://", "https://"))
            else urljoin(
                f"{base_url}/",
                (result_path or f"/api/v1/model/prediction/{quote(prediction_id, safe='')}").lstrip("/"),
            )
        )
        base_origin = urlsplit(base_url)
        result_origin = urlsplit(result_url)
        if (result_origin.scheme, result_origin.netloc) != (
            base_origin.scheme,
            base_origin.netloc,
        ):
            raise RuntimeError("Atlas Cloud image API returned a cross-origin polling URL.")
        poll_interval = max(0.1, float(options.get("poll_interval") or 3))
        timeout = max(poll_interval, float(options.get("timeout") or 300))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(poll_interval)
            response = requests.get(result_url, headers=headers, timeout=30)
            if not response.ok:
                _raise_http_error(response)
            prediction = _prediction(response)
            status = str(prediction.get("status") or "").strip().lower()
            if status in _FAILURE_STATUSES:
                message = prediction.get("error") or prediction.get("message") or "prediction failed"
                raise RuntimeError(f"Atlas Cloud image API: {message}")
            outputs = _outputs(prediction)
            if outputs or status in _SUCCESS_STATUSES:
                break
        else:
            raise ImageProviderError(504, "Atlas Cloud image API: prediction timed out")

    if not outputs:
        raise RuntimeError("Atlas Cloud image API completed without an output image.")

    # Output URLs may use a separate CDN. Never forward the Atlas API key.
    image_response = requests.get(outputs[0], timeout=30)
    if not image_response.ok:
        _raise_http_error(image_response)
    mime_type = image_response.headers.get("Content-Type", "image/png").split(";", 1)[0]
    return image_response.content, mime_type

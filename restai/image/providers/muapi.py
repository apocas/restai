"""MuAPI asynchronous image generation provider."""

from __future__ import annotations

import logging
import time
from urllib.parse import quote, urlsplit

import requests

from restai.image.dispatch import ImageProviderError
from restai.models.models import ImageModel

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.muapi.ai"
_SUCCESS_STATUSES = {"completed", "succeeded", "success", "done"}
_FAILURE_STATUSES = {"failed", "failure", "error", "timeout", "cancelled", "canceled"}


def _message(response: requests.Response, fallback: str) -> str:
    try:
        body = response.json()
    except ValueError:
        return fallback
    if isinstance(body, dict):
        detail = body.get("message") or body.get("detail") or body.get("error")
        if isinstance(detail, dict):
            detail = detail.get("message") or detail.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    return fallback


def _raise_http_error(response: requests.Response) -> None:
    upstream = response.status_code
    status = upstream if 400 <= upstream < 500 else 502
    message = _message(response, f"upstream returned HTTP {upstream}")
    logger.warning("MuAPI image generation failed (%s): %s", upstream, message)
    raise ImageProviderError(status, f"MuAPI image API: {message}")


def _body(response: requests.Response) -> dict:
    try:
        body = response.json()
    except ValueError as exc:
        raise RuntimeError("MuAPI image API returned invalid JSON.") from exc
    if not isinstance(body, dict):
        raise RuntimeError("MuAPI image API returned an invalid response.")
    return body


def _data(body: dict) -> dict:
    data = body.get("data")
    return data if isinstance(data, dict) else body


def _request_id(body: dict) -> str:
    data = _data(body)
    value = data.get("request_id") or data.get("id") or body.get("request_id") or body.get("id")
    return str(value or "").strip()


def _status(body: dict) -> str:
    data = _data(body)
    return str(data.get("status") or body.get("status") or "").strip().lower()


def _outputs(body: dict) -> list[str]:
    data = _data(body)
    outputs = data.get("outputs") or data.get("output") or body.get("outputs") or body.get("output")
    if isinstance(outputs, str):
        outputs = [outputs]
    if not isinstance(outputs, list):
        return []
    return [str(item).strip() for item in outputs if str(item).strip()]


def _base_url(options: dict) -> str:
    base_url = str(options.get("base_url") or DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("MuAPI image generator: `base_url` must be an HTTP(S) URL.")
    if parsed.path.rstrip("/").endswith("/api/v1"):
        base_url = base_url[: -len(parsed.path.rstrip("/"))]
    return base_url.rstrip("/")


def _endpoint(options: dict) -> str:
    value = str(options.get("endpoint") or options.get("model") or "").strip()
    if not value:
        raise RuntimeError("MuAPI image generator: `model` or `endpoint` is required in options.")
    if "://" in value:
        raise ValueError("MuAPI image generator: endpoint must be a catalog path or model name.")
    value = value.lstrip("/")
    if value.startswith("api/v1/"):
        return "/" + value
    return "/api/v1/" + value


def generate(options: dict, image_model: ImageModel) -> tuple[bytes, str]:
    """Submit one MuAPI image job, poll its result, and download the image."""
    api_key = str(options.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError("MuAPI image generator: `api_key` is required in options.")

    base_url = _base_url(options)
    endpoint = _endpoint(options)
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {"prompt": image_model.prompt}
    parameters = options.get("parameters")
    if parameters is not None:
        if not isinstance(parameters, dict):
            raise ValueError("MuAPI image generator: `parameters` must be an object when provided.")
        payload.update(parameters)
        payload["prompt"] = image_model.prompt

    response = requests.post(
        f"{base_url}{endpoint}",
        headers=headers,
        json=payload,
        timeout=30,
    )
    if not response.ok:
        _raise_http_error(response)

    submission = _body(response)
    request_id = _request_id(submission)
    if not request_id:
        raise RuntimeError("MuAPI image API response is missing a request ID.")

    result_url = f"{base_url}/api/v1/predictions/{quote(request_id, safe='')}/result"
    poll_interval = max(0.1, float(options.get("poll_interval") or 3))
    timeout = max(poll_interval, float(options.get("timeout") or 300))
    deadline = time.monotonic() + timeout
    outputs: list[str] = []
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        response = requests.get(result_url, headers=headers, timeout=30)
        if not response.ok:
            _raise_http_error(response)
        result = _body(response)
        status = _status(result)
        outputs = _outputs(result)
        if outputs or status in _SUCCESS_STATUSES:
            break
        if status in _FAILURE_STATUSES:
            detail = _data(result).get("error") or _data(result).get("message") or status
            raise RuntimeError(f"MuAPI image API: prediction failed: {detail}")
    else:
        raise ImageProviderError(504, "MuAPI image API: prediction timed out")

    if not outputs:
        raise RuntimeError("MuAPI image API completed without an output image.")

    output_url = outputs[0]
    if not output_url.startswith("https://"):
        raise RuntimeError("MuAPI image API returned a non-HTTPS output URL.")

    # Output URLs may use a separate CDN. Never forward the MuAPI API key.
    image_response = requests.get(output_url, timeout=30)
    if not image_response.ok:
        _raise_http_error(image_response)
    mime_type = image_response.headers.get("Content-Type", "image/png").split(";", 1)[0]
    return image_response.content, mime_type

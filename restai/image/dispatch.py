"""Image-generator dispatch — look up a generator by name and hand off to its provider."""
from __future__ import annotations

import json
import logging

from restai.models.databasemodels import ImageGeneratorDatabase
from restai.models.models import ImageModel

logger = logging.getLogger(__name__)


class UnknownGeneratorError(Exception):
    """Raised when no enabled generator matches the requested name."""


class GeneratorDisabledError(Exception):
    """Raised when a matching generator exists but `enabled=False`."""


class ImageProviderError(Exception):
    """Raised when a provider's upstream API returns a non-2xx response.

    Carries the upstream HTTP status so the router can forward it cleanly.
    """

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _load_options(row: ImageGeneratorDatabase) -> dict:
    """Parse + decrypt the row's options blob."""
    from restai.utils.crypto import decrypt_sensitive_options, LLM_SENSITIVE_KEYS

    try:
        raw = json.loads(row.options) if row.options else {}
    except Exception:
        raw = {}
    if isinstance(raw, dict):
        try:
            raw = decrypt_sensitive_options(raw, LLM_SENSITIVE_KEYS)
        except Exception:
            pass
    return raw if isinstance(raw, dict) else {}


def list_available_generators(db_wrapper) -> list[str]:
    """Names of all enabled generators."""
    rows = db_wrapper.get_image_generators()
    return [r.name for r in rows if r.enabled]


def generate_image(name: str, image_model: ImageModel, brain, db_wrapper) -> tuple[bytes, str]:
    """Resolve `name` to a generator row and run it. Returns ``(raw_bytes, mime_type)``."""
    row = db_wrapper.get_image_generator_by_name(name)
    if row is None:
        raise UnknownGeneratorError(name)
    if not row.enabled:
        raise GeneratorDisabledError(name)

    options = _load_options(row)

    if row.class_name == "openai":
        from restai.image.providers.openai import generate as _gen
        return _gen(options, image_model)

    if row.class_name == "google":
        from restai.image.providers.google import generate as _gen
        return _gen(options, image_model)

    if row.class_name == "local":
        # Local workers live in `restai/image/workers/*.py`. `name` matches
        # the module basename. Lightweight `Brain` (cron) never loads
        # generators, so `get_generators` returns empty there and we bail
        # before touching the multiprocessing manager.
        generators = brain.get_generators([name]) if hasattr(brain, "get_generators") else []
        if not generators:
            raise UnknownGeneratorError(name)
        from restai.multiprocessing import get_manager
        from restai.image.runner import generate as _runner
        b64 = _runner(get_manager(), generators[0], image_model)
        import base64 as _b64
        return _b64.b64decode(b64), "image/png"

    raise UnknownGeneratorError(name)

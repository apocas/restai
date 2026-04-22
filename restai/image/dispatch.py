"""Image-generator dispatch — look up a generator by name in the registry
and hand off to its provider.

Callers:
- `restai/routers/image.py` — REST + OpenAI-compat endpoints.
- `restai/llms/tools/draw_image.py` — agent-side `draw_image` builtin.

Both share this single source of truth so admins don't have to maintain
two lists, and so adding a new external provider only means adding a new
module under `restai/image/providers/`.
"""
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


def _load_options(row: ImageGeneratorDatabase) -> dict:
    """Parse + decrypt the row's options blob. Safe to call repeatedly."""
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
    """Names of all enabled generators — for the list endpoint + UI."""
    rows = db_wrapper.get_image_generators()
    return [r.name for r in rows if r.enabled]


def generate_image(name: str, image_model: ImageModel, brain, db_wrapper) -> tuple[bytes, str]:
    """Resolve `name` to a generator row and run it. Returns
    ``(raw_bytes, mime_type)``. Raises `UnknownGeneratorError` when the
    name doesn't match anything, `GeneratorDisabledError` when it matches
    but the admin flipped `enabled=false`."""
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
        # the module basename. The actual runner uses torch multiprocessing
        # and needs the `manager` on `brain.image_manager` — only the
        # main API process (non-lightweight) has it.
        manager = getattr(brain, "image_manager", None)
        generators = brain.get_generators([name]) if hasattr(brain, "get_generators") else []
        if not generators:
            raise UnknownGeneratorError(name)
        if manager is None:
            raise RuntimeError(
                f"Local generator '{name}' needs the torch multiprocessing manager "
                "(GPU mode). Start the API with RESTAI_GPU=true."
            )
        from restai.image.runner import generate as _runner
        b64 = _runner(manager, generators[0], image_model)
        import base64 as _b64
        return _b64.b64decode(b64), "image/png"

    raise UnknownGeneratorError(name)

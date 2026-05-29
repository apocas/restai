"""HTTP endpoints for the App-Builder file IDE.

This package splits the App-Builder router across cohesive modules. Each
sub-module decorates its routes onto the shared ``router`` defined in
``_common``; importing the sub-modules here registers every route on that
single ``APIRouter`` instance, which is then re-exported as the package's
``router`` for ``from restai.routers import app``.
"""

from __future__ import annotations

from ._common import router

# Importing each sub-module registers its routes on the shared `router`.
from . import files  # noqa: E402,F401
from . import db  # noqa: E402,F401
from . import chat  # noqa: E402,F401
from . import generate  # noqa: E402,F401
from . import deploy  # noqa: E402,F401
from . import validate  # noqa: E402,F401

__all__ = ["router"]

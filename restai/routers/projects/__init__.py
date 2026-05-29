from restai.routers.projects._common import router, get_project

# Import every route-group module so their @router decorators execute and
# register onto the shared `router` instance from `_common`. Order is
# irrelevant to the resulting route set.
from restai.routers.projects import (  # noqa: E402,F401
    core,
    prompts,
    analytics,
    comments,
    widgets,
    routines,
    memory,
    tools,
    kg,
    mobile,
)

__all__ = ["router", "get_project"]

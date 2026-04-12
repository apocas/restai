import sys
sys.setrecursionlimit(20000)

# Force full app initialization (all routers, all Pydantic models) under the
# raised recursion limit. Without this, the first TestClient in each test file
# triggers schema resolution which can hit the default 1000-depth limit on CI.
from restai.main import app  # noqa: F401

import sys

# Increase recursion limit to handle repeated TestClient(app) creations
# across the full test suite. Each TestClient startup triggers Pydantic
# schema generation which can exhaust the default limit cumulatively.
sys.setrecursionlimit(5000)

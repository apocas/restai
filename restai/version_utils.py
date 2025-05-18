import tomli
from pathlib import Path

def get_version_from_pyproject():
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    with pyproject_path.open("rb") as f:
        data = tomli.load(f)
    return data["project"]["version"]

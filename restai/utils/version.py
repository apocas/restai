def get_version_from_pyproject():
    try:
        from importlib.metadata import version
        return version("restai-core")
    except Exception:
        pass
    # Fallback: read from pyproject.toml (dev mode)
    try:
        import tomli
        from pathlib import Path
        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        with pyproject_path.open("rb") as f:
            data = tomli.load(f)
        return data["project"]["version"]
    except Exception:
        return "0.0.0"

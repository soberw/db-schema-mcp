"""Package version helpers."""

from importlib.metadata import PackageNotFoundError, version

PACKAGE_NAME = "db-schema-mcp"


def get_version() -> str:
    """Return the installed package version."""
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.0.0"


__version__ = get_version()

__version__ = "0.1.6"
__build__   = 3
__dev__      = False


def version_string() -> str:
    if __dev__:
        return f"v{__version__}+b{__build__}"
    return f"v{__version__}"

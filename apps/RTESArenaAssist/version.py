__version__ = '0.2.31'
__build__ = 3
__dev__ = False

def version_string() -> str:
    if __dev__:
        return f'v{__version__}+b{__build__}'
    return f'v{__version__}'

__version__ = '0.2.29'
__build__ = 24
__dev__ = False

def version_string() -> str:
    if __dev__:
        return f'v{__version__}+b{__build__}'
    return f'v{__version__}'

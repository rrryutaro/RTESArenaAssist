__version__ = '0.1.7'
__build__ = 99
__dev__ = False

def version_string() -> str:
    if __dev__:
        return f'v{__version__}+b{__build__}'
    return f'v{__version__}'

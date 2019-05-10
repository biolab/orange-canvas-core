import warnings
from contextlib import redirect_stderr, redirect_stdout

warnings.warn(
    "'{}' is deprecated use contextlib.redirect_{stderr,stdin}.",
    DeprecationWarning, stacklevel=2
)

import warnings

# Back-compatibility. Should not be imported from here
from AnyQt.QtCore import QSettings  # pylint: disable=unused-import


def toPyObject(variant):
    warnings.warn(
        "toPyObject is deprecated and will be removed.",
        DeprecationWarning, stacklevel=2
    )
    return variant


def qunwrap(variant):
    """Unwrap a `variant` and return it's contents.
    """
    warnings.warn(
        "qunwrap is deprecated and will be removed.",
        DeprecationWarning, stacklevel=2
    )
    return variant


def qwrap(obj):
    warnings.warn(
        "qwrap is deprecated and will be removed.",
        DeprecationWarning, stacklevel=2
    )
    return obj

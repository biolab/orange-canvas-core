import types
from functools import reduce

import typing
from typing import Iterable, Set, Any, Optional, Union, Tuple

from .qtcompat import toPyObject

if typing.TYPE_CHECKING:
    H = typing.TypeVar("H", bound=typing.Hashable)


def dotted_getattr(obj, name):
    # type: (Any, str) -> Any
    """
    `getattr` like function accepting a dotted name for attribute lookup.
    """
    return reduce(getattr, name.split("."), obj)


def qualified_name(obj):
    # type: (Union[types.FunctionType, type]) -> str
    """
    Return a qualified name for `obj` (type or function).
    """
    if obj.__name__ == "builtins":
        return obj.__name__
    else:
        return "%s.%s" % (obj.__module__, obj.__name__)


def name_lookup(qualified_name):
    # type: (str) -> Any
    """
    Return the object referenced by a qualified name (dotted name).
    """
    if "." not in qualified_name:
        qualified_name = "builtins." + qualified_name

    module_name, class_name = qualified_name.rsplit(".", 1)
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)


def type_lookup(qualified_name):
    # type: (str) -> Optional[type]
    T = name_lookup(qualified_name)
    if isinstance(T, type):
        return T
    else:
        return None


def type_lookup_(tspec):
    # type: (Union[str, type]) -> Optional[type]
    if isinstance(tspec, str):
        return type_lookup(tspec)
    else:
        return tspec


def asmodule(module):
    # type: (Union[str, types.ModuleType]) -> types.ModuleType
    """
    Return the :class:`module` instance named by `module`.

    If `module` is already a module instance and not a string, return
    it unchanged.

    """
    if isinstance(module, str):
        return __import__(module, fromlist=[])
    else:
        return module


def check_type(obj, type_or_tuple):
    if not isinstance(obj, type_or_tuple):
        raise TypeError("Expected %r. Got %r" % (type_or_tuple, type(obj)))


def check_subclass(cls, class_or_tuple):
    # type: (type, Union[type, Tuple[type, ...]]) -> None
    if not issubclass(cls, class_or_tuple):
        raise TypeError("Expected %r. Got %r" % (class_or_tuple, type(cls)))


def check_arg(pred, value):
    # type: (bool, str) -> None
    if not pred:
        raise ValueError(value)


def unique(iterable):
    # type: (Iterable[H]) -> Iterable[H]
    """
    Return unique elements of `iterable` while preserving their order.

    Parameters
    ----------
    iterable : Iterable[Hashable]

    Returns
    -------
    unique : Iterable
        Unique elements from `iterable`.
    """
    seen = set()  # type: Set[H]

    def observed(el):  # type: (H) -> bool
        observed = el in seen
        seen.add(el)
        return observed
    return (el for el in iterable if not observed(el))

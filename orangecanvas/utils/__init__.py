import enum
import operator
import types
from functools import reduce

import typing
from typing import (
    Iterable, Set, Any, Optional, Union, Tuple, Callable, Mapping, List, Dict,
    SupportsInt, cast, overload
)

from AnyQt.QtCore import Qt
from AnyQt.QtGui import QMouseEvent, QWheelEvent
from AnyQt.QtWidgets import QSizePolicy

from .qtcompat import toPyObject

__all__ = [
    "dotted_getattr",
    "qualified_name",
    "name_lookup",
    "type_lookup",
    "type_lookup_",
    "asmodule",
    "check_type",
    "check_arg",
    "check_subclass",
    "unique",
    "assocv",
    "assocf",
    "group_by_all",
    "mapping_get",
    "findf",
    "set_flag",
    "is_flag_set",
    "qsizepolicy_is_expanding",
    "qsizepolicy_is_shrinking",
    "is_event_source_mouse",
    "UNUSED",
]

if typing.TYPE_CHECKING:
    H = typing.TypeVar("H", bound=typing.Hashable)
    A = typing.TypeVar("A")
    B = typing.TypeVar("B")
    C = typing.TypeVar("C")
    K = typing.TypeVar("K")
    V = typing.TypeVar("V")
    KV = Tuple[K, V]
    F = typing.TypeVar("F", bound=int)


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


def type_str(type_name):
    # type: (Union[str, Tuple[str, ...]]) -> str
    if isinstance(type_name, tuple):
        if len(type_name) == 1:
            return type_str(type_name[0])
        else:
            return "Union[" + ", ".join(type_str(t) for t in type_name) + "]"
    elif type_name.startswith("builtin."):
        return type_name[len("builtin."):]
    else:
        return type_name


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
    # type: (str) -> type
    """
    Return the type referenced by a qualified name.

    Parameters
    ----------
    qualified_name : str

    Returns
    -------
    type: type

    Raises
    ------
    TypeError:
        If the object referenced by `qualified_name` is not a type
    """
    rval = name_lookup(qualified_name)
    if not isinstance(rval, type):
        raise TypeError(
            "'{}' is a {!r} not a type".format(qualified_name, type(rval))
        )
    return rval


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


@overload
def unique(iterable: Iterable['H']) -> Iterable['H']: ...


@overload
def unique(iterable: Iterable['A'], key: Callable[['A'], 'H']) -> Iterable['A']: ...


def unique(iterable, key=None):
    # type: (Iterable[A], Optional[Callable[[A], H]]) -> Iterable[A]
    """
    Return unique elements of `iterable` while preserving their order.

    If `key` is supplied it is used as a substitute for determining
    'uniqueness' of elements.

    Parameters
    ----------
    iterable : Iterable[A]
    key : Callable[[A], Hashable]

    Returns
    -------
    unique : Iterable[A]
        Unique elements from `iterable`.
    """
    seen = set()  # type: Set[Union[H, A]]
    if key is None:
        key = cast('Callable[[A], H]', lambda t: t)
    for el in iterable:
        el_key = key(el)
        if el_key not in seen:
            seen.add(el_key)
            yield el


def assocv(seq, key, eq=operator.eq):
    # type: (Iterable[KV], C, Callable[[K, C], bool]) -> Optional[KV]
    """
    Find and return the first pair `p` in `seq` where `eq(p[0], key) is True`

    Return None if not found.

    Parameters
    ----------
    seq: Iterable[Tuple[K, V]]
    key: C
    eq: Callable[[K, C], bool]

    Returns
    -------
    pair: Optional[Tuple[K, V]]
    """
    for k, v in seq:
        if eq(k, key):
            return k, v
    return None


def assocf(seq, predicate):
    # type: (Iterable[KV], Callable[[K], bool]) -> Optional[KV]
    """
    Find and return the first pair `p` in `seq` where `predicate(p[0]) is True`

    Return None if not found.

    Parameters
    ----------
    seq: Iterable[Tuple[K, V]]
    predicate: Callable[[K], bool]

    Returns
    -------
    pair: Optional[Tuple[K, V]]
    """
    for k, v in seq:
        if predicate(k):
            return k, v
    return None


def group_by_all(sequence, key=None):
    # type: (Iterable[V], Callable[[V], K]) -> List[Tuple[K, List[V]]]
    order_seen = []
    groups = {}  # type: Dict[K, List[V]]

    for item in sequence:
        if key is not None:
            item_key = key(item)
        else:
            item_key = item  # type: ignore
        if item_key in groups:
            groups[item_key].append(item)
        else:
            groups[item_key] = [item]
            order_seen.append(item_key)

    return [(key, groups[key]) for key in order_seen]


def mapping_get(
    mapping,  # type: Mapping[K, V]
    key,      # type: K
    type,     # type: Callable[[V], A]
    default,  # type: B
):  # type: (...) -> Union[A, B]
    try:
        val = mapping[key]
    except KeyError:
        return default
    try:
        return type(val)
    except (TypeError, ValueError):
        return default


def findf(iterable, predicate, default=None):
    # type: (Iterable[A], Callable[[A], bool], B) -> Union[A, B]
    """
    Find and return the first element in iterable where `predicate(el)` is True.

    Return default if no such element is found.
    """
    for item in iterable:
        if predicate(item):
            return item
    return typing.cast('Union[A, B]', default)


def set_flag(flags, mask, on=True):
    # type: (F, Union[SupportsInt, enum.Flag], bool) -> F
    if not isinstance(mask, enum.Flag):
        mask = int(mask)
    if on:
        return type(flags)(flags | mask)
    else:
        return type(flags)(flags & ~mask)


def enum_as_int(value: Union[int, enum.Enum]) -> int:
    """
    Return a `enum.Enum` value as an `int.

    This is function intended for extracting underlying Qt5/6 enum
    values specifically with PyQt6 where most Qt enums are represented
    with `enum.Enum` and lose their numerical value.

    >>> from PyQt6.QtCore import Qt
    >>> enum_as_int(Qt.Alignment.AlignLeft)
    1
    """
    if isinstance(value, enum.Enum):
        return int(value.value)
    else:
        return int(value)


def is_flag_set(flags, mask):
    flags_i = enum_as_int(flags)
    mask_i = enum_as_int(mask)
    return bool(flags_i & mask_i)


def qsizepolicy_is_expanding(policy: QSizePolicy.Policy) -> bool:
    return is_flag_set(policy, QSizePolicy.ExpandFlag)


def qsizepolicy_is_shrinking(policy: QSizePolicy.Policy) -> bool:
    return is_flag_set(policy, QSizePolicy.ShrinkFlag)


def is_event_source_mouse(event: Union[QWheelEvent, QMouseEvent]) -> bool:
    """
    Does th event originate from a mouse type device or from another source
    (touchpad/screen).
    """
    try:
        return event.source() != Qt.MouseEventNotSynthesized
    except AttributeError:  # PyQt6
        from AnyQt.QtGui import QInputDevice
        return event.device().type() == QInputDevice.DeviceType.Mouse


def UNUSED(*_unused_args) -> None:
    """
    *Mark* the function arguments as unused for a code checker

    Examples
    --------
    >>> def foo(bar, baz):
    ...     UNUSED(bar, baz)
    ...     return True
    """

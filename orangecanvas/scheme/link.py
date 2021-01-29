"""
===========
Scheme Link
===========

"""
import enum
import warnings
import typing
from traceback import format_exception_only
from typing import List, Tuple, Union, Optional, Iterable

from AnyQt.QtCore import QObject, QCoreApplication
from AnyQt.QtCore import pyqtSignal as Signal, pyqtProperty as Property

from ..registry.description import normalize_type_simple
from ..utils import type_lookup
from .errors import IncompatibleChannelTypeError
from .events import LinkEvent

if typing.TYPE_CHECKING:
    from ..registry import OutputSignal as Output, InputSignal as Input
    from . import SchemeNode as Node


def resolve_types(types):
    # type: (Iterable[str]) -> Tuple[Optional[type], ...]
    """
    Resolve the fully qualified names to python types.

    If a name fails to resolve to a type then the corresponding entry in output
    is replaced with a None.

    Parameters
    ----------
    types: Iterable[str]
        Names of types to resolve

    Returns
    -------
    type: Tuple[Optional[type], ...]
        The `type` instances in the same order as input `types` with `None`
        replacing any type that cannot be resolved.

    """
    rt = []  # type: List[Optional[type]]
    for t in types:
        try:
            rt.append(type_lookup(t))
        except (TypeError, ImportError, AttributeError) as err:
            warnings.warn(
                "Failed to resolve name {!r} to a type: {!s}"
                    .format(t, "\n".join(format_exception_only(type(err), err))),
                RuntimeWarning, stacklevel=2
            )
            rt.append(None)
    return tuple(rt)


def resolved_valid_types(types):
    # type: (Iterable[str]) -> Tuple[type, ...]
    """
    Resolve fully qualified names to python types, omiting all types that
    fail to resolve.

    Parameters
    ----------
    types: Iterable[str]

    Returns
    -------
    type: Tuple[type, ...]
    """
    return tuple(filter(None, resolve_types(types)))


def compatible_channels(source_channel, sink_channel):
    # type: (Output, Input) -> bool
    """
    Do the source and sink channels have compatible types, i.e. can they be
    connected based on their specified types.
    """
    strict, dynamic = _classify_connection(source_channel, sink_channel)
    return strict or dynamic


def _classify_connection(source, sink):
    # type: (Output, Input) -> Tuple[bool, bool]
    """
    Classify the source -> sink connection type check.

    Returns
    -------
    rval : Tuple[bool, bool]
        A `(strict, dynamic)` tuple where `strict` is True if connection
        passes a strict type check, and `dynamic` is True if the
        `source.dynamic` is True and at least one of the sink types is
        a subtype of the source types.
    """
    source_types = resolved_valid_types(source.types)
    sink_types = resolved_valid_types(sink.types)
    if not source_types or not sink_types:
        return False, False
    # Are all possible source types subtypes of the sink_types.
    strict = all(issubclass(source_t, sink_types) for source_t in source_types)
    if source.dynamic:
        # Is at least one of the possible sink types a subtype of
        # the source_types.
        dynamic = any(issubclass(sink_t, source_types) for sink_t in sink_types)
    else:
        dynamic = False
    return strict, dynamic


def can_connect(source_node, sink_node):
    # type: (Node, Node) -> bool
    """
    Return True if any output from `source_node` can be connected to
    any input of `sink_node`.
    """
    return bool(possible_links(source_node, sink_node))


def possible_links(source_node, sink_node):
    # type: (Node, Node) -> List[Tuple[Output, Input]]
    """
    Return a list of (OutputSignal, InputSignal) tuples, that
    can connect the two nodes.
    """
    possible = []
    for source in source_node.output_channels():
        for sink in sink_node.input_channels():
            if compatible_channels(source, sink):
                possible.append((source, sink))
    return possible


def _get_first_type(arg, newname):
    # type: (Union[str, type, Tuple[Union[str, type], ...]], str) -> type
    if isinstance(arg, tuple):
        if len(arg) > 1:
            warnings.warn(
                "Multiple types specified, but using only the first. "
                "Use `{newname}` instead.".format(newname=newname),
                RuntimeWarning, stacklevel=3
            )
        if arg:
            arg0 = normalize_type_simple(arg[0])
            return type_lookup(arg0)
        else:
            raise ValueError("no type spec")
    if isinstance(arg, type):
        return arg
    rv = type_lookup(arg)
    if rv is not None:
        return rv
    else:
        raise TypeError("{!r} does not resolve to a type")


class SchemeLink(QObject):
    """
    A instantiation of a link between two :class:`.SchemeNode` instances
    in a :class:`.Scheme`.

    Parameters
    ----------
    source_node : :class:`.SchemeNode`
        Source node.
    source_channel : :class:`OutputSignal`
        The source widget's signal.
    sink_node : :class:`.SchemeNode`
        The sink node.
    sink_channel : :class:`InputSignal`
        The sink widget's input signal.
    properties : `dict`
        Additional link properties.

    """

    #: The link enabled state has changed
    enabled_changed = Signal(bool)

    #: The link dynamic enabled state has changed.
    dynamic_enabled_changed = Signal(bool)

    #: Runtime link state has changed
    state_changed = Signal(int)

    class State(enum.IntEnum):
        """
        Flags indicating the runtime state of a link
        """
        #: The link has no associated state (e.g. is not associated with any
        #: execution contex)
        NoState = 0
        #: A link is empty when it has no value on it.
        Empty = 1
        #: A link is active when the source node provides a value on output.
        Active = 2
        #: A link is pending when it's sink node has not yet been notified
        #: of a change (note that Empty|Pending is a valid state)
        Pending = 4
        #: The link's source node has invalidated the source channel.
        #: The execution manager should not propagate this links source value
        #: until this flag is cleared.
        #:
        #: .. versionadded:: 0.1.8
        Invalidated = 8

    NoState = State.NoState
    Empty = State.Empty
    Active = State.Active
    Pending = State.Pending
    Invalidated = State.Invalidated

    def __init__(self, source_node, source_channel,
                 sink_node, sink_channel,
                 enabled=True, properties=None, parent=None):
        # type: (Node, Output, Node, Input, bool, dict, QObject) -> None
        super().__init__(parent)
        self.source_node = source_node

        if isinstance(source_channel, str):
            source_channel = source_node.output_channel(source_channel)
        elif source_channel not in source_node.output_channels():
            raise ValueError("%r not in in nodes output channels." \
                             % source_channel)

        self.source_channel = source_channel

        self.sink_node = sink_node

        if isinstance(sink_channel, str):
            sink_channel = sink_node.input_channel(sink_channel)
        elif sink_channel not in sink_node.input_channels():
            raise ValueError("%r not in in nodes input channels." \
                             % source_channel)

        self.sink_channel = sink_channel

        if not compatible_channels(source_channel, sink_channel):
            raise IncompatibleChannelTypeError(
                "Cannot connect %r to %r"
                % (source_channel.type, sink_channel.type)
            )

        self.__enabled = enabled
        self.__dynamic_enabled = False
        self.__state = SchemeLink.NoState  # type: Union[SchemeLink.State, int]
        self.__tool_tip = ""
        self.properties = properties or {}

    def source_type(self):
        # type: () -> type
        """
        Return the type of the source channel.

        .. deprecated:: 0.1.5
            Use :func:`source_types` instead.
        """
        warnings.warn(
            "`source_type()` is deprecated. Use `source_types()`.",
            DeprecationWarning, stacklevel=2
        )
        return _get_first_type(self.source_channel.type, "source_types")

    def source_types(self):
        # type: () -> Tuple[type, ...]
        """
        Return the type(s) of the source channel.
        """
        return resolved_valid_types(self.source_channel.types)

    def sink_type(self):
        # type: () -> type
        """
        Return the type of the sink channel.

        .. deprecated:: 0.1.5
            Use :func:`sink_types` instead.
        """
        warnings.warn(
            "`sink_type()` is deprecated. Use `sink_types()`.",
            DeprecationWarning, stacklevel=2
        )
        return _get_first_type(self.sink_channel.types, "sink_types")

    def sink_types(self):
        # type: () -> Tuple[type, ...]
        """
        Return the type(s) of the sink channel.
        """
        return resolved_valid_types(self.sink_channel.types)

    def is_dynamic(self):
        # type: () -> bool
        """
        Is this link dynamic.
        """
        sink_types = self.sink_types()
        source_types = self.source_types()
        if self.source_channel.dynamic:
            strict, dynamic = _classify_connection(
                self.source_channel, self.sink_channel)
            # If the connection type checks (strict) then supress the dynamic
            # state.
            return not strict and dynamic
        else:
            return False

    def set_enabled(self, enabled):
        # type: (bool) -> None
        """
        Enable/disable the link.
        """
        if self.__enabled != enabled:
            self.__enabled = enabled
            self.enabled_changed.emit(enabled)

    def is_enabled(self):
        # type: () -> bool
        """
        Is this link enabled.
        """
        return self.__enabled

    enabled: bool
    enabled = Property(bool, is_enabled, set_enabled)  # type: ignore

    def set_dynamic_enabled(self, enabled):
        # type: (bool) -> None
        """
        Enable/disable the dynamic link. Has no effect if the link
        is not dynamic.
        """
        if self.is_dynamic() and self.__dynamic_enabled != enabled:
            self.__dynamic_enabled = enabled
            self.dynamic_enabled_changed.emit(enabled)

    def is_dynamic_enabled(self):
        # type: () -> bool
        """
        Is this a dynamic link and is `dynamic_enabled` set to `True`
        """
        return self.is_dynamic() and self.__dynamic_enabled

    dynamic_enabled: bool
    dynamic_enabled = Property(  # type: ignore
        bool, is_dynamic_enabled, set_dynamic_enabled)

    def set_runtime_state(self, state):
        # type: (Union[State, int]) -> None
        """
        Set the link's runtime state.

        Parameters
        ----------
        state : SchemeLink.State
        """
        if self.__state != state:
            self.__state = state
            ev = LinkEvent(LinkEvent.InputLinkStateChange, self)
            QCoreApplication.sendEvent(self.sink_node, ev)
            ev = LinkEvent(LinkEvent.OutputLinkStateChange, self)
            QCoreApplication.sendEvent(self.source_node, ev)
            self.state_changed.emit(state)

    def runtime_state(self):
        # type: () -> Union[State, int]
        """
        Returns
        -------
        state : SchemeLink.State
        """
        return self.__state

    def set_runtime_state_flag(self, flag, on):
        # type: (State, bool) -> None
        """
        Set/unset runtime state flag.

        Parameters
        ----------
        flag: SchemeLink.State
        on: bool
        """
        if on:
            state = self.__state | flag
        else:
            state = self.__state & ~flag
        self.set_runtime_state(state)

    def test_runtime_state(self, flag):
        # type: (State) -> bool
        """
        Test if runtime state flag is on/off

        Parameters
        ----------
        flag: SchemeLink.State
            State flag to test

        Returns
        -------
        on: bool
            True if `flag` is set; False otherwise.

        """
        return bool(self.__state & flag)

    def set_tool_tip(self, tool_tip):
        # type: (str) -> None
        """
        Set the link tool tip.
        """
        if self.__tool_tip != tool_tip:
            self.__tool_tip = tool_tip

    def _tool_tip(self):
        # type: () -> str
        """
        Link tool tip.
        """
        return self.__tool_tip

    tool_tip: str
    tool_tip = Property(str, _tool_tip, set_tool_tip)  # type: ignore

    def __str__(self):
        return "{0}(({1}, {2}) -> ({3}, {4}))".format(
            type(self).__name__,
            self.source_node.title, self.source_channel.name,
            self.sink_node.title, self.sink_channel.name
        )

    def __getstate__(self):
        return self.source_node, \
               self.source_channel.name, \
               self.sink_node, \
               self.sink_channel.name, \
               self.__enabled, \
               self.properties, \
               self.parent()

    def __setstate__(self, state):
        mutable_state = list(state)
        # correct source channel
        mutable_state[1] = state[0].output_channel(state[1])
        # correct sink channel
        mutable_state[3] = state[2].input_channel(state[3])
        self.__init__(*mutable_state)

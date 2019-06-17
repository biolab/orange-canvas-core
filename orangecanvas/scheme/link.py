"""
===========
Scheme Link
===========

"""
import enum
import typing
from typing import List, Tuple, Union

from AnyQt.QtCore import QObject
from AnyQt.QtCore import pyqtSignal as Signal, pyqtProperty as Property

from ..utils import type_lookup, type_lookup_
from .errors import IncompatibleChannelTypeError

if typing.TYPE_CHECKING:
    from ..registry import OutputSignal as Output, InputSignal as Input
    from . import SchemeNode as Node


def compatible_channels(source_channel, sink_channel):
    # type: (Output, Input) -> bool
    """
    Do the channels in link have compatible types, i.e. can they be
    connected based on their type.
    """
    source_type = type_lookup_(source_channel.type)
    sink_type = type_lookup_(sink_channel.type)
    if source_type is None or sink_type is None:
        return False
    ret = issubclass(source_type, sink_type)
    if source_channel.dynamic:
        ret = ret or issubclass(sink_type, source_type)
    return ret


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


def _get_type(arg):
    # type: (Union[str, type]) -> type
    """get a type instance qualified name"""
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
        #: The link has no associated state.
        NoState = 0
        #: A link is empty when it has no value on it
        Empty = 1
        #: A link is active when the source node provides a value on output
        Active = 2
        #: A link is pending when it's sink node has not yet been notified
        #: of a change (note that Empty|Pending is a valid state)
        Pending = 4

    NoState = State.NoState
    Empty = State.Empty
    Active = State.Active
    Pending = State.Pending

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
        self.__state = SchemeLink.NoState
        self.__tool_tip = ""
        self.properties = properties or {}

    def source_type(self):
        # type: () -> type
        """
        Return the type of the source channel.
        """
        return _get_type(self.source_channel.type)

    def sink_type(self):
        # type: () -> type
        """
        Return the type of the sink channel.
        """
        return _get_type(self.sink_channel.type)

    def is_dynamic(self):
        # type: () -> bool
        """
        Is this link dynamic.
        """
        return self.source_channel.dynamic and \
               issubclass(self.sink_type(), self.source_type()) and \
               not (self.sink_type() is self.source_type())

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

    enabled = Property(bool, fget=is_enabled, fset=set_enabled)

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

    dynamic_enabled = Property(bool, fget=is_dynamic_enabled,
                               fset=set_dynamic_enabled)

    def set_runtime_state(self, state):
        # type: (State) -> None
        """
        Set the link's runtime state.

        Parameters
        ----------
        state : SchemeLink.State
        """
        if self.__state != state:
            self.__state = state
            self.state_changed.emit(state)

    def runtime_state(self):
        # type: () -> State
        """
        Returns
        -------
        state : SchemeLink.State
        """
        return self.__state

    def set_tool_tip(self, tool_tip):
        # type: (str) -> None
        """
        Set the link tool tip.
        """
        if self.__tool_tip != tool_tip:
            self.__tool_tip = tool_tip

    def tool_tip(self):
        # type: () -> str
        """
        Link tool tip.
        """
        return self.__tool_tip

    tool_tip = Property(str, fget=tool_tip,  # type: ignore
                        fset=set_tool_tip)

    def __str__(self):
        return "{0}(({1}, {2}) -> ({3}, {4}))".format(
            type(self).__name__,
            self.source_node.title, self.source_channel.name,
            self.sink_node.title, self.sink_channel.name
        )

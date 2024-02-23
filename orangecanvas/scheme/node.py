"""
===========
Scheme Node
===========

"""
import enum
import warnings
from typing import Optional, Dict, Any, List, Tuple, Iterable, Union

from AnyQt.QtCore import QObject, QCoreApplication
from AnyQt.QtCore import pyqtSignal as Signal, pyqtProperty as Property
from AnyQt.QtGui import QIcon

from ..registry import WidgetDescription, InputSignal, OutputSignal
from .events import NodeEvent, NodeInputChannelEvent, NodeOutputChannelEvent
from .element import Element
from ..resources import icon_loader

Pos = Tuple[float, float]


class UserMessage(object):
    """
    A user message that should be displayed in a scheme view.

    Parameters
    ----------
    contents : str
        Message text.
    severity : int
        Message severity.
    message_id : str
        Message id.
    data : dict
        A dictionary with optional extra data.
    """
    #: Severity flags
    Info, Warning, Error = 1, 2, 3

    def __init__(self, contents, severity=Info, message_id="", data={}):
        # type: (str, int, str, Dict[str, Any]) -> None
        self.contents = contents
        self.severity = severity
        self.message_id = message_id
        self.data = dict(data)


class Node(Element):
    """
    Common base class of all other workflow graph nodes.

    This class should not be instantiated directly use one of
    :class:`SchemeNode`, :class:`MetaNode`, :class:`InputNode` and
    :class:`OutputNode`.
    """
    class State(enum.IntEnum):
        """
        A workflow node's runtime state flags
        """
        #: The node has no state.
        NoState = 0

        #: The node is running (i.e. executing a task).
        Running = 1

        #: The node has invalidated inputs. This flag is set when:
        #:
        #: * An input link is added or removed
        #: * An input link is marked as pending
        #:
        #: It is set/cleared by the execution manager when the inputs are
        #: propagated to the node.
        Pending = 2

        #: The node has invalidated outputs. Execution manager should not
        #: propagate this node's existing outputs to dependent nodes until
        #: this flag is cleared.
        Invalidated = 4

        #: The node is in a state where it does not accept new signals.
        #: The execution manager should not propagate inputs to this node
        #: until this flag is cleared.
        NotReady = 8

    NoState = State.NoState
    Running = State.Running
    Pending = State.Pending
    Invalidated = State.Invalidated
    NotReady = State.NotReady

    def __init__(
            self, title: str = "", position: Pos = (0, 0),
            properties: Optional[dict] = None, parent: Optional[QObject] = None,
            **kwargs
    ):
        super().__init__(parent, **kwargs)
        self.__parent_node = None
        self.__title = title
        self.__position = position
        self.__properties = properties or {}
        self.__title = title
        self.__position = position
        self.__progress = -1
        self.__processing_state = 0
        self.__tool_tip = ""
        self.__status_message = ""
        self.__state_messages = {}  # type: Dict[str, UserMessage]
        self.__state = Node.NoState  # type: Union[Node.State, int]
        # I/O channels added at runtime/config
        self.__inputs = []  # type: List[InputSignal]
        self.__outputs = []  # type: List[OutputSignal]
        self.properties = properties or {}

    #: Signal emitted when an input channel is inserted
    input_channel_inserted = Signal(int, InputSignal)
    #: Signal emitted when an input channel is removed
    input_channel_removed = Signal(int, InputSignal)

    def add_input_channel(self, signal: InputSignal):
        """Add `signal` input channel."""
        self.insert_input_channel(len(self.input_channels()), signal)

    def insert_input_channel(self, index, signal: InputSignal):
        """Insert the `signal` input channel at `index`"""
        self.__inputs.insert(index, signal)
        ev = NodeInputChannelEvent(NodeEvent.InputChannelAdded, self, signal, index)
        QCoreApplication.sendEvent(self, ev)
        w = self.workflow()
        if w is not None:
            QCoreApplication.sendEvent(self, ev)
        self.input_channel_inserted.emit(index, signal)

    def remove_input_channel(self, index) -> InputSignal:
        """Remove the input channel at `index`"""
        r = self.__inputs.pop(index)
        ev = NodeInputChannelEvent(NodeEvent.InputChannelRemoved, self, r, index)
        QCoreApplication.sendEvent(self, ev)
        w = self.workflow()
        if w is not None:
            QCoreApplication.sendEvent(w, ev)
        self.input_channel_removed.emit(index, r)
        return r

    def input_channels(self):
        # type: () -> List[InputSignal]
        """
        Return a list of input channels (:class:`InputSignal`) for the node.
        """
        return list(self.__inputs)

    #: Signal emitted when an output channel is inserted.
    output_channel_inserted = Signal(int, OutputSignal)
    #: Signal emitted when an output channel is removed.
    output_channel_removed = Signal(int, OutputSignal)

    def add_output_channel(self, signal: OutputSignal):
        """Add `signal` output channel."""
        self.insert_output_channel(len(self.output_channels()), signal)

    def insert_output_channel(self, index, signal: OutputSignal):
        """Insert the `signal` output channel at `index`"""
        self.__outputs.insert(index, signal)
        ev = NodeOutputChannelEvent(NodeEvent.OutputChannelAdded, self, signal, index)
        QCoreApplication.sendEvent(self, ev)
        w = self.workflow()
        if w is not None:
            QCoreApplication.sendEvent(w, ev)
        self.output_channel_inserted.emit(index, signal)

    def remove_output_channel(self, index) -> OutputSignal:
        """Remove the output channel at `index`"""
        r = self.__outputs.pop(index)
        ev = NodeOutputChannelEvent(NodeEvent.OutputChannelRemoved, self, r, index)
        QCoreApplication.sendEvent(self, ev)
        w = self.workflow()
        if w is not None:
            QCoreApplication.sendEvent(w, ev)
        self.output_channel_removed.emit(index, r)
        return r

    def output_channels(self):
        # type: () -> List[OutputSignal]
        """
        Return a list of output channels (:class:`OutputSignal`) for the node.
        """
        return list(self.__outputs)

    def input_channel(self, name):
        # type: (str) -> InputSignal
        """
        Return the input channel matching `name`. Raise a `ValueError`
        if not found.
        """
        for channel in self.input_channels():
            if channel.id == name:
                return channel
        # Fallback to channel names for backward compatibility
        for channel in self.input_channels():
            if channel.name == name:
                return channel
        raise ValueError("%r is not a valid input channel for %r." %
                         (name, self.title))

    def output_channel(self, name):
        # type: (str) -> OutputSignal
        """
        Return the output channel matching `name`. Raise an `ValueError`
        if not found.
        """
        for channel in self.output_channels():
            if channel.id == name:
                return channel
        # Fallback to channel names for backward compatibility
        for channel in self.output_channels():
            if channel.name == name:
                return channel
        raise ValueError("%r is not a valid output channel for %r." %
                         (name, self.title))

    #: The title of the node has changed
    title_changed = Signal(str)

    def set_title(self, title):
        """
        Set the node title.
        """
        if self.__title != title:
            self.__title = title
            self.title_changed.emit(self.__title)

    def _title(self):
        """
        The node title.
        """
        return self.__title

    title: str
    title = Property(str, _title, set_title)  # type: ignore

    def icon(self) -> QIcon:
        return QIcon()

    #: Position of the node in the scheme has changed
    position_changed = Signal(tuple)

    def set_position(self, pos):
        """
        Set the position (``(x, y)`` tuple) of the node.
        """
        if self.__position != pos:
            self.__position = pos
            self.position_changed.emit(pos)

    def _get_position(self):
        """
        ``(x, y)`` tuple containing the position of the node in the scheme.
        """
        return self.__position

    position: Tuple[float, float]
    position = Property(tuple, _get_position, set_position)  # type: ignore

    #: Node's progress value has changed.
    progress_changed = Signal(float)

    def set_progress(self, value):
        """
        Set the progress value.
        """
        if self.__progress != value:
            self.__progress = value
            self.progress_changed.emit(value)

    def _progress(self):
        """
        The current progress value. -1 if progress is not set.
        """
        return self.__progress

    progress: float
    progress = Property(float, _progress, set_progress)  # type: ignore

    #: Node's processing state has changed.
    processing_state_changed = Signal(int)

    def set_processing_state(self, state):
        """
        Set the node processing state.
        """
        self.set_state_flags(Node.Running, bool(state))

    def _processing_state(self):
        """
        The node processing state, 0 for not processing, 1 the node is busy.
        """
        return int(bool(self.state() & Node.Running))

    processing_state: int
    processing_state = Property(  # type: ignore
        int, _processing_state, set_processing_state)

    def set_tool_tip(self, tool_tip):
        if self.__tool_tip != tool_tip:
            self.__tool_tip = tool_tip

    def _tool_tip(self):
        return self.__tool_tip

    tool_tip: str
    tool_tip = Property(str, _tool_tip, set_tool_tip)  # type: ignore

    #: The node's status tip has changes
    status_message_changed = Signal(str)

    def set_status_message(self, text):
        # type: (str) -> None
        """Set a short status message."""
        if self.__status_message != text:
            self.__status_message = text
            self.status_message_changed.emit(text)

    def status_message(self):
        # type: () -> str
        """A short status message summarizing the current node state."""
        return self.__status_message

    #: The node's state message has changed
    state_message_changed = Signal(UserMessage)

    def set_state_message(self, message):
        # type: (UserMessage) -> None
        """
        Set a message to be displayed by a scheme view for this node.
        """
        if message.message_id is not None:
            self.__state_messages[message.message_id] = message
            self.state_message_changed.emit(message)
        else:
            warnings.warn(
                "'message' with no id was ignored. "
                "This will raise an error in the future.",
                FutureWarning, stacklevel=2
            )

    def clear_state_message(self, message_id):
        # type: (str) -> None
        """
        Clear (remove) a message with `message_id`.

        :attr:`state_message_changed` signal will be emitted with a empty
        message for the `message_id`.
        """
        if message_id in self.__state_messages:
            # emit an empty message
            m = self.__state_messages[message_id]
            m = UserMessage("", m.severity, m.message_id)
            self.__state_messages[message_id] = m
            self.state_message_changed.emit(m)
            del self.__state_messages[message_id]

    def state_message(self, message_id):
        # type: (str) -> Optional[UserMessage]
        """
        Return a message with `message_id` or None if a message with that
        id does not exist.
        """
        return self.__state_messages.get(message_id, None)

    def state_messages(self):
        # type: () -> Iterable[UserMessage]
        """
        Return a list of all state messages.
        """
        return self.__state_messages.values()

    state_changed = Signal(int)

    def set_state(self, state):
        # type: (Union[State, int]) -> None
        """
        Set the node runtime state flags

        Parameters
        ----------
        state: Node.State
        """
        if self.__state != state:
            curr = self.__state
            self.__state = state
            QCoreApplication.sendEvent(
                self, NodeEvent(NodeEvent.NodeStateChange, self)
            )
            self.state_changed.emit(state)
            if curr & Node.Running != state & Node.Running:
                self.processing_state_changed.emit(
                    int(bool(state & Node.Running))
                )

    def state(self):
        # type: () -> Union[State, int]
        """
        Return the node runtime state flags.
        """
        return self.__state

    def set_state_flags(self, flags, on):
        # type: (Union[State, int], bool) -> None
        """
        Set the specified state flags on/off.

        Parameters
        ----------
        flags: Node.State
            Flag to modify
        on: bool
            Turn the flag on or off
        """
        if on:
            state = self.__state | flags
        else:
            state = self.__state & ~flags
        self.set_state(state)

    def test_state_flags(self, flag):
        # type: (State) -> bool
        """
        Return True/False if the runtime state flag is set.

        Parameters
        ----------
        flag: Node.State

        Returns
        -------
        val: bool
        """
        return bool(self.__state & flag)


class SchemeNode(Node):
    """
    A node in a :class:`.Scheme`.

    Parameters
    ----------
    description : :class:`WidgetDescription`
        Node description instance.
    title : str, optional
        Node title string (if None `description.name` is used).
    position : tuple
        (x, y) tuple of floats for node position in a visual display.
    properties : dict
        Additional extra instance properties (settings, widget geometry, ...)
    parent : :class:`QObject`
        Parent object.
    """
    def __init__(self, description, title=None, position=(0, 0),
                 properties=None, parent=None):
        # type: (WidgetDescription, str, Pos, dict, QObject) -> None
        if title is None:
            title = description.name

        super().__init__(title, position, properties or {}, parent=parent)
        self.description = description
        # I/O channels added at runtime/config
        self.__inputs = []  # type: List[InputSignal]
        self.__outputs = []  # type: List[OutputSignal]

    def input_channels(self):
        # type: () -> List[InputSignal]
        """
        Return a list of input channels (:class:`InputSignal`) for the node.
        """
        return list(self.description.inputs) + self.__inputs

    input_channel_inserted = Signal(int, InputSignal)
    input_channel_removed = Signal(int, InputSignal)

    def add_input_channel(self, signal: InputSignal):
        self.insert_input_channel(len(self.input_channels()), signal)

    def insert_input_channel(self, index, signal: InputSignal):
        inputs = self.description.inputs
        if 0 <= index < len(inputs):
            raise IndexError("Cannot insert into predefined inputs")
        self.__inputs.insert(index - len(inputs), signal)
        QCoreApplication.sendEvent(
            self, NodeInputChannelEvent(NodeEvent.InputChannelAdded, self, signal, index)
        )
        self.input_channel_inserted.emit(index, signal)

    def remove_input_channel(self, index) -> InputSignal:
        inputs = self.description.inputs
        if 0 <= index < len(inputs):
            raise IndexError("Cannot remove predefined inputs")
        r = self.__inputs.pop(index - len(inputs))
        QCoreApplication.sendEvent(
            self, NodeInputChannelEvent(NodeEvent.InputChannelRemoved, self, r, index)
        )
        self.input_channel_removed.emit(index, r)
        return r

    def output_channels(self):
        # type: () -> List[OutputSignal]
        """
        Return a list of output channels (:class:`OutputSignal`) for the node.
        """
        return list(self.description.outputs) + self.__outputs

    output_channel_inserted = Signal(int, OutputSignal)
    output_channel_removed = Signal(int, OutputSignal)

    def add_output_channel(self, signal: OutputSignal):
        self.insert_output_channel(len(self.output_channels()), signal)

    def insert_output_channel(self, index, signal: OutputSignal):
        outputs = self.description.outputs
        if 0 <= index < len(outputs):
            raise IndexError("Cannot insert into predefined outputs")
        self.__outputs.insert(index - len(outputs), signal)
        QCoreApplication.sendEvent(
            self, NodeOutputChannelEvent(NodeEvent.OutputChannelAdded, self, signal, index)
        )
        self.output_channel_inserted.emit(index, signal)

    def remove_output_channel(self, index) -> OutputSignal:
        outputs = self.description.outputs
        if 0 <= index < len(outputs):
            raise IndexError("Cannot remove predefined output")
        r = self.__outputs.pop(index - len(outputs))
        QCoreApplication.sendEvent(
            self, NodeOutputChannelEvent(NodeEvent.OutputChannelRemoved, self, r, index)
        )
        self.output_channel_removed.emit(index, r)
        return r

    def icon(self) -> QIcon:
        desc = self.description
        return icon_loader.from_description(desc).get(desc.icon)

    def __str__(self):
        return "SchemeNode(description_id=%r, title=%r, ...)" % \
                (str(self.description.id), self.title)

    def __repr__(self):
        return str(self)

    def __getstate__(self):
        return self.description, \
               self.title, \
               self.position, \
               self.properties, \
               self.__inputs, \
               self.__outputs

    def __setstate__(self, state):
        *state, inputs, outputs = state
        self.__init__(*state)
        for ic in self.__inputs:
            self.add_input_channel(ic)
        for oc in self.__outputs:
            self.add_output_channel(oc)

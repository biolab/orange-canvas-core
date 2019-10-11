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

from ..registry import WidgetDescription, InputSignal, OutputSignal
from .events import NodeEvent


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


class SchemeNode(QObject):
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

    def __init__(self, description, title=None, position=None,
                 properties=None, parent=None):
        # type: (WidgetDescription, str, Tuple[float, float], dict, QObject) -> None
        super().__init__(parent)
        self.description = description

        if title is None:
            title = description.name

        self.__title = title
        self.__position = position or (0, 0)
        self.__progress = -1
        self.__processing_state = 0
        self.__status_message = ""
        self.__state_messages = {}  # type: Dict[str, UserMessage]
        self.__state = SchemeNode.NoState  # type: Union[SchemeNode.State, int]
        self.properties = properties or {}

    def input_channels(self):
        # type: () -> List[InputSignal]
        """
        Return a list of input channels (:class:`InputSignal`) for the node.
        """
        return list(self.description.inputs)

    def output_channels(self):
        # type: () -> List[OutputSignal]
        """
        Return a list of output channels (:class:`OutputSignal`) for the node.
        """
        return list(self.description.outputs)

    def input_channel(self, name):
        # type: (str) -> InputSignal
        """
        Return the input channel matching `name`. Raise a `ValueError`
        if not found.
        """
        for channel in self.input_channels():
            if channel.name == name:
                return channel
        raise ValueError("%r is not a valid input channel name for %r." % \
                         (name, self.description.name))

    def output_channel(self, name):
        # type: (str) -> OutputSignal
        """
        Return the output channel matching `name`. Raise an `ValueError`
        if not found.
        """
        for channel in self.output_channels():
            if channel.name == name:
                return channel
        raise ValueError("%r is not a valid output channel name for %r." % \
                         (name, self.description.name))

    #: The title of the node has changed
    title_changed = Signal(str)

    def set_title(self, title):
        """
        Set the node title.
        """
        if self.__title != title:
            self.__title = title
            self.title_changed.emit(self.__title)

    def title(self):
        """
        The node title.
        """
        return self.__title

    title = Property(str, fset=set_title, fget=title)  # type: ignore

    #: Position of the node in the scheme has changed
    position_changed = Signal(tuple)

    def set_position(self, pos):
        """
        Set the position (``(x, y)`` tuple) of the node.
        """
        if self.__position != pos:
            self.__position = pos
            self.position_changed.emit(pos)

    def position(self):
        """
        ``(x, y)`` tuple containing the position of the node in the scheme.
        """
        return self.__position

    position = Property(tuple, fset=set_position, fget=position)  # type: ignore

    #: Node's progress value has changed.
    progress_changed = Signal(float)

    def set_progress(self, value):
        """
        Set the progress value.
        """
        if self.__progress != value:
            self.__progress = value
            self.progress_changed.emit(value)

    def progress(self):
        """
        The current progress value. -1 if progress is not set.
        """
        return self.__progress

    progress = Property(float, fset=set_progress, fget=progress)  # type: ignore

    #: Node's processing state has changed.
    processing_state_changed = Signal(int)

    def set_processing_state(self, state):
        """
        Set the node processing state.
        """
        self.set_state_flags(SchemeNode.Running, bool(state))

    def processing_state(self):
        """
        The node processing state, 0 for not processing, 1 the node is busy.
        """
        return int(bool(self.state() & SchemeNode.Running))

    processing_state = Property(int, fset=set_processing_state,  # type: ignore
                                fget=processing_state)

    def set_tool_tip(self, tool_tip):
        if self.__tool_tip != tool_tip:
            self.__tool_tip = tool_tip

    def tool_tip(self):
        return self.__tool_tip

    tool_tip = Property(str, fset=set_tool_tip,  # type: ignore
                        fget=tool_tip)

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
        state: SchemeNode.State
        """
        if self.__state != state:
            curr = self.__state
            self.__state = state
            QCoreApplication.sendEvent(
                self, NodeEvent(NodeEvent.NodeStateChange, self)
            )
            self.state_changed.emit(state)
            if curr & SchemeNode.Running != state & SchemeNode.Running:
                self.processing_state_changed.emit(
                    int(bool(state & SchemeNode.Running))
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
        flags: SchemeNode.State
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
        flag: SchemeNode.State

        Returns
        -------
        val: bool
        """
        return bool(self.__state & flag)

    def __str__(self):
        return "SchemeNode(description_id=%r, title=%r, ...)" % \
                (str(self.description.id), self.title)

    def __repr__(self):
        return str(self)

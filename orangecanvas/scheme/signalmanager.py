"""
=================================
SignalManager (``signalmanager``)
=================================

A SignalManager instance handles the runtime signal propagation between
widgets in a scheme workflow.

"""
import os
import logging
import warnings
import enum

from collections import defaultdict
from operator import attrgetter
from functools import partial, reduce

import typing
from typing import (
    Any, Optional, List, NamedTuple, Set, Dict,
    Sequence, Union, DefaultDict, Type
)

from AnyQt.QtCore import QObject, QTimer, QSettings, QEvent
from AnyQt.QtCore import pyqtSignal, pyqtSlot as Slot

from . import LinkEvent
from ..utils import unique, mapping_get, group_by_all
from ..registry import OutputSignal, InputSignal
from .scheme import Scheme, SchemeNode, SchemeLink
from ..utils.graph import traverse_bf, strongly_connected_components

if typing.TYPE_CHECKING:
    V = typing.TypeVar("V")
    K = typing.TypeVar("K")

log = logging.getLogger(__name__)


class Signal(
    NamedTuple(
        "Signal", (
            ("link", SchemeLink),
            ("value", Any),
            ("id", Any),
            ("index", int),
        ))
):
    """
    A signal sent via a link between two nodes.

    Attributes
    ----------
    link : SchemeLink
        The link on which the signal is sent
    value : Any
        The signal value
    id : Any
        .. deprecated:: 0.1.19

    index: int
        Position of the link in sink_node's input links at the time the signal
        is enqueued or -1 if not applicable.

    See also
    --------
    InputSignal.flags, OutputSignal.flags
    """
    def __new__(cls, link: SchemeLink, value: Any, id: Any = None,
                index: int = -1):
        return super().__new__(cls, link, value, id, index)

    @property
    def channel(self) -> InputSignal:
        """Alias for `self.link.sink_channel`"""
        return self.link.sink_channel

    New: 'Type[New]'
    Update: 'Type[Update]'
    Close: 'Type[Close]'


class New(Signal): ...
class Update(Signal): ...
class Close(Signal): ...


Signal.New = New
Signal.Update = Update
Signal.Close = Close


is_enabled = attrgetter("enabled")


class _OutputState:
    """Output state for a single node/channel"""
    __slots__ = ('flags', 'outputs')
    #: Flag indicating the output on the channel is invalidated.
    Invalidated = 1

    def __init__(self):
        self.outputs = defaultdict()
        self.flags = 0

    def __repr__(self):
        return "State(flags={}, outputs={!r})".format(
            self.flags, dict(self.outputs)
        )
    __str__ = __repr__


class SignalManager(QObject):
    """
    SignalManager handles the runtime signal propagation for a :class:`.Scheme`
    instance.

    Note
    ----
    If a scheme instance is passed as a parent to the constructor it is also
    set as the workflow model.
    """
    class State(enum.IntEnum):
        """
        SignalManager state flags.

        .. seealso:: :func:`SignalManager.state()`
        """
        #: The manager is running, i.e. it propagates signals
        Running = 0
        #: The manager is stopped. It does not track node output changes,
        #: and does not deliver signals to dependent nodes
        Stopped = 1
        #: The manager is paused. It still tracks node output changes, but
        #: does not deliver new signals to dependent nodes. The pending signals
        #: will be delivered once it enters Running state again
        Paused = 2

    #: The manager is running, i.e. it propagates signals
    Running = State.Running
    #: The manager is stopped. It does not track node ouput changes,
    #: and does not deliver signals to dependent nodes
    Stopped = State.Stopped
    #: The manager is paused. It still tracks node output changes, but
    #: does not deliver new signals to dependent nodes. The pending signals
    #: will be delivered once it enters Running state again
    Paused = State.Paused

    # unused; back-compatibility
    Error = 3

    class RuntimeState(enum.IntEnum):
        """
        SignalManager runtime state.

        See Also
        --------
        SignalManager.runtime_state
        """
        #: Waiting, idle state. The signal queue is empty
        Waiting = 0
        #: ...
        Processing = 1

    Waiting = RuntimeState.Waiting
    Processing = RuntimeState.Processing

    #: Emitted when the state of the signal manager changes.
    stateChanged = pyqtSignal(int)
    #: Emitted when signals are added to the queue.
    updatesPending = pyqtSignal()
    #: Emitted right before a `SchemeNode` instance has its inputs updated.
    processingStarted = pyqtSignal([], [SchemeNode])
    #: Emitted right after a `SchemeNode` instance has had its inputs updated.
    processingFinished = pyqtSignal([], [SchemeNode])
    #: Emitted when `SignalManager`'s runtime state changes.
    runtimeStateChanged = pyqtSignal(int)

    def __init__(self, parent=None, *, max_running=None, **kwargs):
        # type: (Optional[QObject], Optional[int], Any) -> None
        super().__init__(parent, **kwargs)
        self.__workflow = None  # type: Optional[Scheme]
        self.__input_queue = []  # type: List[Signal]

        # mapping a node to its current outputs
        self.__node_outputs = {}  # type: Dict[SchemeNode, DefaultDict[OutputSignal, _OutputState]]

        self.__state = SignalManager.Running
        self.__runtime_state = SignalManager.Waiting

        self.__update_timer = QTimer(self, interval=100, singleShot=True)
        self.__update_timer.timeout.connect(self.__process_next)
        self.__max_running = max_running
        if isinstance(parent, Scheme):
            self.set_workflow(parent)

    def _can_process(self):  # type: () -> bool
        """
        Return a bool indicating if the manger can enter the main
        processing loop.

        """
        return self.__state not in [SignalManager.Error, SignalManager.Stopped]

    def workflow(self):
        # type: () -> Optional[Scheme]
        """
        Return the :class:`Scheme` instance.
        """
        return self.__workflow
    #: Alias
    scheme = workflow

    def set_workflow(self, workflow):
        # type: (Scheme) -> None
        """
        Set the workflow model.

        Parameters
        ----------
        workflow : Scheme
        """
        if workflow is self.__workflow:
            return

        if self.__workflow is not None:
            for node in self.__workflow.nodes:
                node.state_changed.disconnect(self._update)
                node.removeEventFilter(self)
            for link in self.__workflow.links:
                self.__on_link_removed(link)

            self.__workflow.node_added.disconnect(self.__on_node_added)
            self.__workflow.node_removed.disconnect(self.__on_node_removed)
            self.__workflow.link_added.disconnect(self.__on_link_added)
            self.__workflow.link_removed.disconnect(self.__on_link_removed)
            self.__workflow.removeEventFilter(self)
            self.__node_outputs = {}
            self.__input_queue = []

        self.__workflow = workflow

        if workflow is not None:
            workflow.node_added.connect(self.__on_node_added)
            workflow.node_removed.connect(self.__on_node_removed)
            workflow.link_added.connect(self.__on_link_added)
            workflow.link_removed.connect(self.__on_link_removed)
            for node in workflow.nodes:
                self.__node_outputs[node] = defaultdict(_OutputState)
                node.state_changed.connect(self._update)
                node.installEventFilter(self)

            for link in workflow.links:
                self.__on_link_added(link)
            workflow.installEventFilter(self)

    def has_pending(self):  # type: () -> bool
        """
        Does the manager have any signals to deliver?
        """
        return bool(self.__input_queue)

    def start(self):  # type: () -> None
        """
        Start the update loop.

        Note
        ----
        The updates will not happen until the control reaches the Qt event
        loop.
        """
        if self.__state != SignalManager.Running:
            self.__state = SignalManager.Running
            self.stateChanged.emit(SignalManager.Running)
            self._update()

    def stop(self):  # type: () -> None
        """
        Stop the update loop.

        Note
        ----
        If the `SignalManager` is currently in `process_queues` it will
        still update all current pending signals, but will not re-enter
        until `start()` is called again.
        """
        if self.__state != SignalManager.Stopped:
            self.__state = SignalManager.Stopped
            self.stateChanged.emit(SignalManager.Stopped)
            self.__update_timer.stop()

    def pause(self):  # type: () -> None
        """
        Pause the delivery of signals.
        """
        if self.__state != SignalManager.Paused:
            self.__state = SignalManager.Paused
            self.stateChanged.emit(SignalManager.Paused)
            self.__update_timer.stop()

    def resume(self):
        # type: () -> None
        """
        Resume the delivery of signals.
        """
        if self.__state == SignalManager.Paused:
            self.__state = SignalManager.Running
            self.stateChanged.emit(self.__state)
            self._update()

    def step(self):
        # type: () -> None
        """
        Deliver signals to a single node (only applicable while the `state()`
        is `Paused`).
        """
        if self.__state == SignalManager.Paused:
            self.process_queued()

    def state(self):
        # type: () -> State
        """
        Return the current state.

        Return
        ------
        state : SignalManager.State
        """
        return self.__state

    def _set_runtime_state(self, state):
        # type: (Union[RuntimeState, int]) -> None
        """
        Set the runtime state.

        Should only be called by `SignalManager` implementations.
        """
        state = SignalManager.RuntimeState(state)
        if self.__runtime_state != state:
            self.__runtime_state = state
            self.runtimeStateChanged.emit(self.__runtime_state)

    def runtime_state(self):
        # type: () -> RuntimeState
        """
        Return the runtime state. This can be `SignalManager.Waiting`
        or `SignalManager.Processing`.

        """
        return self.__runtime_state

    def __on_node_removed(self, node):
        # type: (SchemeNode) -> None
        # remove all pending input signals for node so we don't get
        # stale references in process_node.
        # NOTE: This does not remove output signals for this node. In
        # particular the final 'None' will be delivered to the sink
        # nodes even after the source node is no longer in the scheme.
        log.info("Removing pending signals for '%s'.", node.title)
        self.remove_pending_signals(node)

        del self.__node_outputs[node]
        node.state_changed.disconnect(self._update)
        node.removeEventFilter(self)

    def __on_node_added(self, node):
        # type: (SchemeNode) -> None
        self.__node_outputs[node] = defaultdict(_OutputState)
        # schedule update pass on state change
        node.state_changed.connect(self._update)
        node.installEventFilter(self)

    def __on_link_added(self, link):
        # type: (SchemeLink) -> None
        # push all current source values to the sink
        link.set_runtime_state(SchemeLink.Empty)
        state = self.__node_outputs[link.source_node][link.source_channel]
        link.set_runtime_state_flag(
            SchemeLink.Invalidated,
            bool(state.flags & _OutputState.Invalidated)
        )
        signals: List[Signal] = [Signal.New(*s)
                                 for s in self.signals_on_link(link)]
        if not link.is_enabled():
            # Send New signals even if disabled. This is changed behaviour
            # from <0.1.19 where signals were only sent when link was enabled.
            # Because we need to maintain input consistency we cannot use the
            # current signal value so replace it with None.
            signals = [s._replace(value=None) for s in signals]
        log.info("Scheduling signal data update for '%s'.", link)
        self._schedule(signals)
        link.enabled_changed.connect(self.__on_link_enabled_changed)

    def __on_link_removed(self, link):
        # type: (SchemeLink) -> None
        link.enabled_changed.disconnect(self.__on_link_enabled_changed)

    def eventFilter(self, recv: QObject, event: QEvent) -> bool:
        etype = event.type()
        if etype == LinkEvent.InputLinkRemoved:
            event = typing.cast(LinkEvent, event)
            link = event.link()
            log.info("Scheduling close signal (%s).", link)
            signals: List[Signal] = [Signal.Close(link, None, id, event.pos())
                                     for id in self.link_contents(link)]
            self._schedule(signals)
        return super().eventFilter(recv, event)

    def __on_link_enabled_changed(self, enabled):
        if enabled:
            link = self.sender()
            log.info("Link %s enabled. Scheduling signal data update.", link)
            self._update_link(link)

    def signals_on_link(self, link):
        # type: (SchemeLink) -> List[Signal]
        """
        Return :class:`Signal` instances representing the current values
        present on the `link`.
        """
        if self.__workflow is None:
            return []
        items = self.link_contents(link)
        links_in = self.__workflow.find_links(sink_node=link.sink_node)
        index = links_in.index(link)
        return [Signal(link, value, key, index=index)
                for key, value in items.items()]

    def link_contents(self, link):
        # type: (SchemeLink) -> Dict[Any, Any]
        """
        Return the contents on the `link`.
        """
        node, channel = link.source_node, link.source_channel

        if node in self.__node_outputs:
            return self.__node_outputs[node][channel].outputs
        else:
            # if the the node was already removed its tracked outputs in
            # __node_outputs are cleared, however the final 'None' signal
            # deliveries for the link are left in the _input_queue.
            pending = [sig for sig in self.__input_queue
                       if sig.link is link]
            return {sig.id: sig.value for sig in pending}

    def send(self, node, channel, value, *args, **kwargs):
        # type: (SchemeNode, OutputSignal, Any, Any, Any) -> None
        """
        Send the `value` on the output `channel` from `node`.

        Schedule the signal delivery to all dependent nodes

        Parameters
        ----------
        node : SchemeNode
            The originating node.
        channel : OutputSignal
            The nodes output on which the value is sent.
        value : Any
            The value to send,
        id : Any
            Signal id.

            .. deprecated:: 0.1.19

        """
        if self.__workflow is None:
            raise RuntimeError("'send' called with no workflow!.")

        # parse deprecated id parameter from *args, **kwargs.
        def _id_(id):
            return id
        try:
            id = _id_(*args, **kwargs)
        except TypeError:
            id = None
        else:
            warnings.warn(
                "`id` parameter is deprecated and will be removed in v0.2",
                FutureWarning, stacklevel=2
            )

        log.debug("%r sending %r (id: %r) on channel %r",
                  node.title, type(value), id, channel.name)

        scheme = self.__workflow

        state = self.__node_outputs[node][channel]

        if state.outputs and id not in state.outputs:
            raise RuntimeError(
                "Sending multiple values on the same output channel via "
                "different ids is no longer supported."
            )

        sigtype: Type[Signal]
        if id in state.outputs:
            sigtype = Signal.Update
        else:
            sigtype = Signal.New

        state.outputs[id] = value
        assert len(state.outputs) == 1
        # clear invalidated flag
        if state.flags & _OutputState.Invalidated:
            log.debug("%r clear invalidated flag on channel %r",
                      node.title, channel.name)
            state.flags &= ~_OutputState.Invalidated

        links = filter(
            is_enabled,
            scheme.find_links(source_node=node, source_channel=channel)
        )
        signals = []
        for link in links:
            links_in = scheme.find_links(sink_node=link.sink_node)
            index = links_in.index(link)
            signals.append(sigtype(link, value, id, index=index))
            link.set_runtime_state_flag(SchemeLink.Invalidated, False)

        self._schedule(signals)

    def invalidate(self, node, channel):
        # type: (SchemeNode, OutputSignal) -> None
        """
        Invalidate the `channel` on `node`.

        The channel is effectively considered changed but unavailable until
        a new value is sent via `send`. While this state is set the dependent
        nodes will not be updated.

        All links originating with this node/channel will be marked with
        `SchemeLink.Invalidated` flag until a new value is sent with `send`.

        Parameters
        ----------
        node: SchemeNode
            The originating node.
        channel: OutputSignal
            The channel to invalidate.


        .. versionadded:: 0.1.8
        """
        log.debug("%r invalidating channel %r", node.title, channel.name)
        self.__node_outputs[node][channel].flags |= _OutputState.Invalidated
        if self.__workflow is None:
            return
        links = self.__workflow.find_links(
            source_node=node, source_channel=channel
        )
        for link in links:
            link.set_runtime_state(link.runtime_state() | link.Invalidated)

    def purge_link(self, link):
        # type: (SchemeLink) -> None
        """
        Purge the link (send None for all ids currently present)

        .. deprecated:: 0.1.19
        """
        warnings.warn(
            "`purge_link` is deprecated.", DeprecationWarning, stacklevel=2
        )
        self._schedule([Signal(link, None, id)
                        for id in self.link_contents(link)])

    def _schedule(self, signals):
        # type: (List[Signal]) -> None
        """
        Schedule a list of :class:`Signal` for delivery.
        """
        self.__input_queue.extend(signals)

        for link in {sig.link for sig in signals}:
            # update the SchemeLink's runtime state flags
            contents = self.link_contents(link)
            if any(value is not None for value in contents.values()):
                state = SchemeLink.Active
            else:
                state = SchemeLink.Empty
            link.set_runtime_state(state | SchemeLink.Pending)

        for node in {sig.link.sink_node for sig in signals}:  # type: SchemeNode
            # update the SchemeNodes's runtime state flags
            node.set_state_flags(SchemeNode.Pending, True)

        if signals:
            self.updatesPending.emit()

        self._update()

    def _update_link(self, link):
        # type: (SchemeLink) -> None
        """
        Schedule update of a single link.
        """
        self._schedule([Signal.Update(*s) for s in self.signals_on_link(link)])

    def process_queued(self, max_nodes=None):
        # type: (Any) -> None
        """
        Process queued signals.

        Take the first eligible node from the pending input queue and deliver
        all scheduled signals.
        """
        if not (max_nodes is None or max_nodes == 1):
            warnings.warn(
                "`max_nodes` is deprecated and will be removed in the future",
                FutureWarning, stacklevel=2)

        if self.__runtime_state == SignalManager.Processing:
            raise RuntimeError("Cannot re-enter 'process_queued'")

        if not self._can_process():
            raise RuntimeError("Can't process in state %i" % self.__state)

        self.process_next()

    def process_next(self):
        # type: () -> bool
        """
        Process queued signals.

        Take the first eligible node from the pending input queue and deliver
        all scheduled signals for it and return `True`.

        If no node is eligible for update do nothing and return `False`.
        """
        return self.__process_next_helper(use_max_active=False)

    def process_node(self, node):
        # type: (SchemeNode) -> None
        """
        Process pending input signals for `node`.
        """
        assert self.__runtime_state != SignalManager.Processing

        signals_in = self.pending_input_signals(node)
        self.remove_pending_signals(node)

        signals_in = self.compress_signals(signals_in)

        log.debug("Processing %r, sending %i signals.",
                  node.title, len(signals_in))
        # Clear the link's pending flag.
        for link in {sig.link for sig in signals_in}:
            link.set_runtime_state(link.runtime_state() & ~SchemeLink.Pending)

        def process_dynamic(signals):
            # type: (List[Signal]) -> List[Signal]
            """
            Process dynamic signals; Update the link's dynamic_enabled flag if
            the value is valid; replace values that do not type check with
            `None`
            """
            res = []
            for sig in signals:
                # Check and update the dynamic link state
                link = sig.link
                if sig.link.is_dynamic():
                    enabled = can_enable_dynamic(link, sig.value)
                    link.set_dynamic_enabled(enabled)
                    if not enabled:
                        # Send None instead (clear the link)
                        sig = sig._replace(value=None)
                res.append(sig)
            return res
        signals_in = process_dynamic(signals_in)
        assert ({sig.link for sig in self.__input_queue}
                .intersection({sig.link for sig in signals_in}) == set([]))

        self._set_runtime_state(SignalManager.Processing)
        self.processingStarted.emit()
        self.processingStarted[SchemeNode].emit(node)
        try:
            self.send_to_node(node, signals_in)
        finally:
            node.set_state_flags(SchemeNode.Pending, False)
            self.processingFinished.emit()
            self.processingFinished[SchemeNode].emit(node)
            self._set_runtime_state(SignalManager.Waiting)

    def compress_signals(self, signals):
        # type: (List[Signal]) -> List[Signal]
        """
        Compress a list of :class:`Signal` instances to be delivered.

        Before the signal values are delivered to the sink node they can be
        optionally `compressed`, i.e. values can be merged or dropped
        depending on the execution semantics.

        The input list is in the order that the signals were enqueued.

        The base implementation returns the list unmodified.

        Parameters
        ----------
        signals : List[Signal]

        Return
        ------
        signals : List[Signal]
        """
        return signals

    def send_to_node(self, node, signals):
        # type: (SchemeNode, List[Signal]) -> None
        """
        Abstract. Reimplement in subclass.

        Send/notify the `node` instance (or whatever object/instance it is a
        representation of) that it has new inputs as represented by the
        `signals` list).

        Parameters
        ----------
        node : SchemeNode
        signals : List[Signal]
        """
        raise NotImplementedError

    def is_pending(self, node):
        # type: (SchemeNode) -> bool
        """
        Is `node` (class:`SchemeNode`) scheduled for processing (i.e.
        it has incoming pending signals).

        Parameters
        ----------
        node : SchemeNode

        Returns
        -------
        pending : bool
        """
        return node in [signal.link.sink_node for signal in self.__input_queue]

    def pending_nodes(self):
        # type: () -> List[SchemeNode]
        """
        Return a list of pending nodes.

        The nodes are returned in the order they were enqueued for
        signal delivery.

        Returns
        -------
        nodes : List[SchemeNode]
        """
        return list(unique(sig.link.sink_node for sig in self.__input_queue))

    def pending_input_signals(self, node):
        # type: (SchemeNode) -> List[Signal]
        """
        Return a list of pending input signals for node.
        """
        return [signal for signal in self.__input_queue
                if node is signal.link.sink_node]

    def remove_pending_signals(self, node):
        # type: (SchemeNode) -> None
        """
        Remove pending signals for `node`.
        """
        for signal in self.pending_input_signals(node):
            try:
                self.__input_queue.remove(signal)
            except ValueError:
                pass

    def __nodes(self):
        # type: () -> Sequence[SchemeNode]
        return self.__workflow.nodes if self.__workflow else []

    def blocking_nodes(self):
        # type: () -> List[SchemeNode]
        """
        Return a list of nodes in a blocking state.
        """
        return [node for node in self.__nodes() if self.is_blocking(node)]

    def invalidated_nodes(self):
        # type: () -> List[SchemeNode]
        """
        Return a list of invalidated nodes.

        .. versionadded:: 0.1.8
        """
        return [node for node in self.__nodes()
                if self.has_invalidated_outputs(node) or
                self.is_invalidated(node)]

    def active_nodes(self):
        # type: () -> List[SchemeNode]
        """
        Return a list of active nodes.

        .. versionadded:: 0.1.8
        """
        return [node for node in self.__nodes() if self.is_active(node)]

    def is_blocking(self, node):
        # type: (SchemeNode) -> bool
        """
        Is the node in `blocking` state.

        Is it currently in a state where will produce new outputs and
        therefore no signals should be delivered to dependent nodes until
        it does so. Also no signals will be delivered to the node until
        it exits this state.

        The default implementation returns False.

        .. deprecated:: 0.1.8
            Use a combination of `is_invalidated` and `is_ready`.
        """
        return False

    def is_ready(self, node: SchemeNode) -> bool:
        """
        Is the node in a state where it can receive inputs.

        Re-implement this method in as subclass to prevent specific nodes from
        being considered for input update (e.g. they are still initializing
        runtime resources, executing a non-interruptable task, ...)

        Note that whenever the implicit state changes the
        `post_update_request` should be called.

        The default implementation returns the state of the node's
        `SchemeNode.NotReady` flag.

        Parameters
        ----------
        node: SchemeNode
        """
        return not node.test_state_flags(SchemeNode.NotReady)

    def is_invalidated(self, node: SchemeNode) -> bool:
        """
        Is the node marked as invalidated.

        Parameters
        ----------
        node : SchemeNode

        Returns
        -------
        state: bool
        """
        return node.test_state_flags(SchemeNode.Invalidated)

    def has_invalidated_outputs(self, node):
        # type: (SchemeNode) -> bool
        """
        Does node have any explicitly invalidated outputs.

        Parameters
        ----------
        node: SchemeNode

        Returns
        -------
        state: bool

        See also
        --------
        invalidate


        .. versionadded:: 0.1.8
        """
        out = self.__node_outputs.get(node)
        if out is not None:
            return any(state.flags & _OutputState.Invalidated
                       for state in out.values())
        else:
            return False

    def has_invalidated_inputs(self, node):
        # type: (SchemeNode) -> bool
        """
        Does the node have any immediate ancestor with invalidated outputs.

        Parameters
        ----------
        node : SchemeNode

        Returns
        -------
        state: bool

        Note
        ----
        The node's ancestors are only computed over enabled links.


        .. versionadded:: 0.1.8
        """
        if self.__workflow is None:
            return False
        workflow = self.__workflow
        return any(self.has_invalidated_outputs(link.source_node)
                   for link in workflow.find_links(sink_node=node)
                   if link.is_enabled())

    def is_active(self, node):
        # type: (SchemeNode) -> bool
        """
        Is the node considered active (executing a task).

        Parameters
        ----------
        node: SchemeNode

        Returns
        -------
        active: bool
        """
        return bool(node.state() & SchemeNode.Running)

    def node_update_front(self):
        # type: () -> Sequence[SchemeNode]
        """
        Return a list of nodes on the update front, i.e. nodes scheduled for
        an update that have no ancestor which is either itself scheduled
        for update or is in a blocking state).

        Note
        ----
        The node's ancestors are only computed over enabled links.
        """
        if self.__workflow is None:
            return []
        workflow = self.__workflow
        expand = partial(expand_node, workflow)

        components = strongly_connected_components(workflow.nodes, expand)
        node_scc = {node: scc for scc in components for node in scc}

        def isincycle(node):  # type: (SchemeNode) -> bool
            return len(node_scc[node]) > 1

        def dependents(node):  # type: (SchemeNode) -> List[SchemeNode]
            return dependent_nodes(workflow, node)

        # A list of all nodes currently active/executing a non-interruptable
        # task.
        blocking_nodes = set(self.blocking_nodes())
        # nodes marked as having invalidated outputs (not yet available)
        invalidated_nodes = set(self.invalidated_nodes())

        #: transitive invalidated nodes (including the legacy self.is_blocked
        #: behaviour - blocked nodes are both invalidated and cannot receive
        #: new inputs)
        invalidated_ = reduce(
            set.union,
            map(dependents, invalidated_nodes | blocking_nodes),
            set([]),
        )  # type: Set[SchemeNode]

        pending = self.pending_nodes()
        pending_ = set()
        for n in pending:
            depend = set(dependents(n))
            if isincycle(n):
                # a pending node in a cycle would would have a circular
                # dependency on itself, preventing any progress being made
                # by the workflow execution.
                cc = node_scc[n]
                depend -= set(cc)
            pending_.update(depend)

        def has_invalidated_ancestor(node):  # type: (SchemeNode) -> bool
            return node in invalidated_

        def has_pending_ancestor(node):  # type: (SchemeNode) -> bool
            return node in pending_

        #: nodes that are eligible for update.
        ready = list(filter(
            lambda node: not has_pending_ancestor(node)
                         and not has_invalidated_ancestor(node)
                         and not self.is_blocking(node),
            pending
        ))
        return ready

    @Slot()
    def __process_next(self):
        if not self.__state == SignalManager.Running:
            log.debug("Received 'UpdateRequest' while not in 'Running' state")
            return

        if self.__runtime_state == SignalManager.Processing:
            # This happens if QCoreApplication.processEvents is called from
            # the input handlers. A `__process_next` must be rescheduled when
            # exiting process_queued.
            log.warning("Received 'UpdateRequest' while in 'process_queued'. "
                        "An update will be re-scheduled when exiting the "
                        "current update.")
            return

        if not self.__input_queue:
            return

        if self.__process_next_helper(use_max_active=True):
            # Schedule another update (will be a noop if nothing to do).
            self._update()

    def __process_next_helper(self, use_max_active=True) -> bool:
        eligible = [n for n in self.node_update_front() if self.is_ready(n)]
        if not eligible:
            return False
        max_active = self.max_active()
        nactive = len(set(self.active_nodes()) | set(self.blocking_nodes()))

        log.debug(
            "Process next, queued signals: %i, nactive: %i "
            "(max_active: %i)",
            len(self.__input_queue), nactive, max_active
        )
        _ = lambda nodes: list(map(attrgetter('title'), nodes))
        log.debug("Pending nodes: %s", _(self.pending_nodes()))
        log.debug("Blocking nodes: %s", _(self.blocking_nodes()))
        log.debug("Invalidated nodes: %s", _(self.invalidated_nodes()))
        log.debug("Nodes ready for update: %s", _(eligible))

        # Select an node that is already running (effectively cancelling
        # already executing tasks that are immediately updatable)
        selected_node = None  # type: Optional[SchemeNode]
        for node in eligible:
            if self.is_active(node):
                selected_node = node
                break

        # Return if over committed, except in the case that the selected_node
        # is already active.
        if use_max_active and nactive >= max_active and selected_node is None:
            return False

        if selected_node is None:
            selected_node = eligible[0]

        self.process_node(selected_node)
        return True

    def _update(self):  # type: () -> None
        """
        Schedule processing at a later time.
        """
        if self.__state == SignalManager.Running and \
                not self.__update_timer.isActive():
            self.__update_timer.start()

    def post_update_request(self):
        """
        Schedule an update pass.

        Call this method whenever:

        * a node's outputs change (note that this is already done by `send`)
        * any change in the node that influences its eligibility to be picked
          for an input update (is_ready, is_blocking ...).

        Multiple update requests are merged into one.
        """
        self._update()

    def set_max_active(self, val: int) -> None:
        if self.__max_running != val:
            self.__max_running = val
            self._update()

    def max_active(self) -> int:
        value = self.__max_running  # type: Optional[int]
        if value is None:
            value = mapping_get(os.environ, "MAX_ACTIVE_NODES", int, None)
        if value is None:
            s = QSettings()
            s.beginGroup(__name__)
            value = s.value("max-active-nodes", defaultValue=1, type=int)

        if value < 0:
            ccount = os.cpu_count()
            if ccount is None:
                return 1
            else:
                return max(1, ccount + value)
        else:
            return max(1, value)


def can_enable_dynamic(link, value):
    # type: (SchemeLink, Any) -> bool
    """
    Can the a dynamic `link` (:class:`SchemeLink`) be enabled for`value`.
    """
    return isinstance(value, link.sink_types())


def compress_signals(signals: List[Signal]) -> List[Signal]:
    """
    Compress a list of signals by dropping 'stale' signals.

    * Multiple consecutive updates are dropped - preserving only the latest,
      except when one of the updates had `None` value in which case the
      `None` update signal is preserved (by historical convention this meant
      a reset of the input for pending nodes). So for instance if a link had:
      `1, 2, None, 3` scheduled updates then the list would be compressed
      to `None, 3`.
    * Updates preceding a Close signal are dropped - only Close is preserved.

    See Also
    --------
    SignalManager.compress_signals
    """
    # group by key in reverse order (to preserve order of last update)
    groups = group_by_all(reversed(signals), key=lambda sig: (sig.link, sig.id))
    out: List[Signal] = []
    id_to_index = {id(s): i for i, s in enumerate(signals)}
    for _, signals_rev in groups:
        signals = compress_single(list(reversed(signals_rev)))
        out.extend(reversed(signals))
    out = list(reversed(out))
    assert all(id(s) in id_to_index for s in out), 'Must preserve signal id'
    # maintain relative order of (surviving) signals
    return sorted(out, key=lambda s: id_to_index[id(s)])


def compress_single(signals: List[Signal]) -> List[Signal]:
    def is_none_update(signal: 'Optional[Signal]') -> bool:
        return is_update(signal) and signal is not None and signal.value is None

    def is_update(signal: 'Optional[Signal]') -> bool:
        return isinstance(signal, Update) or type(signal) is Signal

    def is_close(signal: 'Optional[Signal]') -> bool:
        return isinstance(signal, Close)

    out: List[Signal] = []
    # 1.) Merge all consecutive updates
    for i, sig in enumerate(signals):
        prev = out[-1] if out else None
        prev_prev = out[-2] if len(out) > 1 else None
        if is_none_update(prev_prev) and is_update(prev) and is_none_update(sig):
            # ..., None, X, None --> ..., None
            out[-2:] = [sig]
        elif is_none_update(prev_prev) and is_update(prev) and is_update(sig):
            # ..., None, X, Y -> ..., None, Y
            out[-1] = sig
        elif is_none_update(prev) and is_none_update(sig):
            # ..., None, None -> ..., None
            out[-1] = sig
        elif is_none_update(prev) and is_update(sig):
            # ..., None, X -> ..., None, X
            out.append(sig)
        elif is_update(prev) and is_update(sig):
            # ..., X, Y -> ..., Y
            out[-1] = sig
        else:
            # ..., X -> ..., X
            out.append(sig)
    signals = out

    # Sanity check. There cannot be more then 2 consecutive updates in the
    # compressed signals queue.
    for i in range(len(signals) - 3):
        assert not all(map(is_update, signals[i: i + 3]))

    out: List[Signal] = []
    # 2.) Drop all Update preceding a Close
    for i, sig in enumerate(signals):
        prev = out[-1] if out else None
        prev_prev = out[-2] if len(out) > 1 else None
        if is_update(prev_prev) and is_update(prev) and is_close(sig):
            # ..., Y, X, Close --> ..., Close
            assert is_none_update(prev_prev)
            out[-2:] = [sig]
        elif is_update(prev) and is_close(sig):
            # ..., X, Close -> ..., Close
            out[-1] = sig
        else:
            # ..., X -> ..., X
            out.append(sig)
    return out


def expand_node(workflow, node):
    # type: (Scheme, SchemeNode) -> List[SchemeNode]
    return [link.sink_node
            for link in workflow.find_links(source_node=node)
            if link.enabled]


def dependent_nodes(scheme, node):
    # type: (Scheme, SchemeNode) -> List[SchemeNode]
    """
    Return a list of all nodes (in breadth first order) in `scheme` that
    are dependent on `node`,

    Note
    ----
    This does not include nodes only reachable by disables links.
    """
    nodes = list(traverse_bf(node, partial(expand_node, scheme)))
    assert nodes[0] is node
    # Remove the first item (`node`).
    return nodes[1:]

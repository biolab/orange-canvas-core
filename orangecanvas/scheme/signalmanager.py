"""
=================================
SignalManager (``signalmanager``)
=================================

A SignalManager instance handles the runtime signal propagation between
widgets in a scheme workflow.

"""

import logging
import itertools
import warnings
import enum

from collections import defaultdict, deque
from operator import attrgetter
from functools import partial, reduce

import typing
from typing import Any, Optional, List, Tuple, NamedTuple, Iterable, Callable

from AnyQt.QtCore import QObject, QTimer, QEvent
from AnyQt.QtCore import pyqtSignal, pyqtSlot as Slot

from ..utils import unique
from ..registry import OutputSignal
from .scheme import Scheme, SchemeNode, SchemeLink


if typing.TYPE_CHECKING:
    T = typing.TypeVar("T")
    V = typing.TypeVar("V")
    K = typing.TypeVar("K")
    H = typing.TypeVar("H", bound=typing.Hashable)

log = logging.getLogger(__name__)


class Signal(
    NamedTuple(
        "Signal", (
            ("link", SchemeLink),
            ("value", Any),
            ("id", Any),
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
        A signal id used to (optionally) differentiate multiple signals
        (`Multiple` is in `link.sink_channel.flags`)

    See also
    --------
    InputSignal.flags, OutputSignal.flags
    """


is_enabled = attrgetter("enabled")

MAX_CONCURRENT = 1


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

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.__workflow = None  # type: Optional[Scheme]
        self.__input_queue = []  # type: List[Signal]

        # mapping a node to its current outputs
        self.__node_outputs = {}  # type: Dict[Node, Dict[OutputSignal, Dict[Any, Any]]]

        self.__state = SignalManager.Running
        self.__runtime_state = SignalManager.Waiting

        self.__update_timer = QTimer(self, interval=100, singleShot=True)
        self.__update_timer.timeout.connect(self.__process_next)

        if isinstance(parent, Scheme):
            self.set_workflow(parent)

    def _can_process(self):
        """
        Return a bool indicating if the manger can enter the main
        processing loop.

        """
        return self.__state not in [SignalManager.Error, SignalManager.Stopped]

    def workflow(self):
        # type: () -> Scheme
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
            for link in self.__workflow.links:
                link.enabled_changed.disconnect(self.__on_link_enabled_changed)

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
                self.__node_outputs[node] = defaultdict(dict)
            for link in workflow.links:
                link.enabled_changed.connect(self.__on_link_enabled_changed)
            workflow.installEventFilter(self)

    def has_pending(self):
        """
        Does the manager have any signals to deliver?
        """
        return bool(self.__input_queue)

    def start(self):
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

    def stop(self):
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

    def pause(self):
        """
        Pause the delivery of signals.
        """
        if self.__state != SignalManager.Paused:
            self.__state = SignalManager.Paused
            self.stateChanged.emit(SignalManager.Paused)
            self.__update_timer.stop()

    def resume(self):
        """
        Resume the delivery of signals.
        """
        if self.__state == SignalManager.Paused:
            self.__state = SignalManager.Running
            self.stateChanged.emit(self.__state)
            self._update()

    def step(self):
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
        """
        Set the runtime state.

        Should only be called by `SignalManager` implementations.
        """
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
        # remove all pending input signals for node so we don't get
        # stale references in process_node.
        # NOTE: This does not remove output signals for this node. In
        # particular the final 'None' will be delivered to the sink
        # nodes even after the source node is no longer in the scheme.
        log.info("Removing pending signals for '%s'.", node.title)
        self.remove_pending_signals(node)

        del self.__node_outputs[node]

    def __on_node_added(self, node):
        self.__node_outputs[node] = defaultdict(dict)

    def __on_link_added(self, link):
        # push all current source values to the sink
        link.set_runtime_state(SchemeLink.Empty)
        if link.enabled:
            log.info("Scheduling signal data update for '%s'.", link)
            self._schedule(self.signals_on_link(link))
            self._update()

        link.enabled_changed.connect(self.__on_link_enabled_changed)

    def __on_link_removed(self, link):
        # purge all values in sink's queue
        log.info("Scheduling signal data purge (%s).", link)
        self.purge_link(link)
        link.enabled_changed.disconnect(self.__on_link_enabled_changed)

    def __on_link_enabled_changed(self, enabled):
        if enabled:
            link = self.sender()
            log.info("Link %s enabled. Scheduling signal data update.", link)
            self._schedule(self.signals_on_link(link))

    def signals_on_link(self, link):
        # type: (SchemeLink) -> List[Signal]
        """
        Return :class:`Signal` instances representing the current values
        present on the link.
        """
        items = self.link_contents(link)
        signals = []

        for key, value in items.items():
            signals.append(Signal(link, value, key))

        return signals

    def link_contents(self, link):
        """
        Return the contents on link.
        """
        node, channel = link.source_node, link.source_channel

        if node in self.__node_outputs:
            return self.__node_outputs[node][channel]
        else:
            # if the the node was already removed its tracked outputs in
            # __node_outputs are cleared, however the final 'None' signal
            # deliveries for the link are left in the _input_queue.
            pending = [sig for sig in self.__input_queue
                       if sig.link is link]
            return {sig.id: sig.value for sig in pending}

    def send(self, node, channel, value, id):
        # type: (SchemeNode, OutputSignal, Any, Any) -> None
        """
        Send the `value` with `id` on an output `channel` from node.

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
        """
        log.debug("%r sending %r (id: %r) on channel %r",
                  node.title, type(value), id, channel.name)

        scheme = self.scheme()

        self.__node_outputs[node][channel][id] = value

        links = scheme.find_links(source_node=node, source_channel=channel)
        links = filter(is_enabled, links)

        signals = []
        for link in links:
            signals.append(Signal(link, value, id))

        self._schedule(signals)

    def purge_link(self, link):
        """
        Purge the link (send None for all ids currently present)
        """
        contents = self.link_contents(link)
        ids = contents.keys()
        signals = [Signal(link, None, id) for id in ids]

        self._schedule(signals)

    def _schedule(self, signals):
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

        if signals:
            self.updatesPending.emit()

        self._update()

    def _update_link(self, link):
        """
        Schedule update of a single link.
        """
        signals = self.signals_on_link(link)
        self._schedule(signals)

    def process_queued(self, max_nodes=None):
        """
        Process queued signals.

        Take one node node from the pending input queue and deliver
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

        log.info("SignalManager: Processing queued signals")

        node_update_front = self.node_update_front()
        log.debug("SignalManager: Nodes eligible for update %s",
                  [node.title for node in node_update_front])

        if node_update_front:
            self.process_node(node_update_front[0])

    def process_node(self, node):
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
                    link.dynamic_enabled = can_enable_dynamic(link, sig.value)
                    if not link.dynamic_enabled:
                        # Send None instead
                        sig = Signal(link, None, sig.id)
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

    def blocking_nodes(self):
        # type: () -> List[SchemeNode]
        """
        Return a list of nodes in a blocking state.
        """
        scheme = self.scheme()
        return [node for node in scheme.nodes if self.is_blocking(node)]

    def is_blocking(self, node):
        # type: (SchemeNode) -> bool
        """
        Is the node in `blocking` state.

        Is it currently in a state where will produce new outputs and
        therefore no signals should be delivered to dependent nodes until
        it does so.

        The default implementation returns False.
        """
        # TODO: this needs a different name
        return False

    def node_update_front(self):
        # type: () -> List[SchemeNode]
        """
        Return a list of nodes on the update front, i.e. nodes scheduled for
        an update that have no ancestor which is either itself scheduled
        for update or is in a blocking state).

        Note
        ----
        The node's ancestors are only computed over enabled links.
        """
        scheme = self.scheme()

        def expand(node):
            return [link.sink_node
                    for link in scheme.find_links(source_node=node)
                    if link.enabled]

        components = strongly_connected_components(scheme.nodes, expand)
        node_scc = {node: scc for scc in components for node in scc}

        def isincycle(node):
            return len(node_scc[node]) > 1

        # a list of all nodes currently active/executing a task.
        blocking_nodes = set(self.blocking_nodes())

        dependents = partial(dependent_nodes, scheme)

        blocked_nodes = reduce(set.union,
                               map(dependents, blocking_nodes),
                               set(blocking_nodes))

        pending = self.pending_nodes()
        pending_downstream = set()
        for n in pending:
            depend = set(dependents(n))
            if isincycle(n):
                # a pending node in a cycle would would have a circular
                # dependency on itself, preventing any progress being made
                # by the workflow execution.
                cc = node_scc[n]
                depend -= set(cc)
            pending_downstream.update(depend)

        log.debug("Pending nodes: %s", pending)
        log.debug("Blocking nodes: %s", blocking_nodes)

        noneligible = pending_downstream | blocked_nodes
        return [node for node in pending if node not in noneligible]

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

        nbusy = len(self.blocking_nodes())
        log.info("'UpdateRequest' event, queued signals: %i, nbusy: %i "
                 "(MAX_CONCURRENT: %i)",
                 len(self.__input_queue), nbusy, MAX_CONCURRENT)

        if self.__input_queue and nbusy < MAX_CONCURRENT:
            try:
                self.process_queued()
            finally:
                # Schedule another update (will be a noop if nothing to do).
                if self.__input_queue and self.__state == SignalManager.Running:
                    self.__update_timer.start()

    def _update(self):
        """
        Schedule processing at a later time.
        """
        if self.__state == SignalManager.Running and \
                not self.__update_timer.isActive():
            self.__update_timer.start()

    def eventFilter(self, receiver, event):
        """
        Reimplemented.
        """
        if event.type() == QEvent.DeferredDelete \
                and receiver is self.__workflow:
            # ?? This is really, probably, mostly, likely not needed. Should
            # just raise error from __process_next.
            state = self.runtime_state()
            if state == SignalManager.Processing:
                log.critical(
                    "The workflow model %r received a deferred delete request "
                    "while performing an input update. "
                    "Deferring a 'DeferredDelete' event for the workflow "
                    "until SignalManager exits the current update step.",
                    self.__workflow
                )
                warnings.warn(
                    "The workflow model received a deferred delete request "
                    "while updating inputs. In the future this will raise "
                    "a RuntimeError", _FutureRuntimeWarning,
                )
                event.setAccepted(False)
                self.processingFinished.connect(self.__workflow.deleteLater)
                self.stop()
                return True
        return super().eventFilter(receiver, event)


class _FutureRuntimeWarning(FutureWarning, RuntimeWarning):
    pass


def can_enable_dynamic(link, value):
    """
    Can the a dynamic `link` (:class:`SchemeLink`) be enabled for`value`.
    """
    return isinstance(value, link.sink_type())


def compress_signals(signals):
    # type: (List[Signal]) -> List[Signal]
    """
    Compress a list of signals by dropping 'stale' signals.

    Only the latest signal value on a link is preserved except when one of
    the signals on the link had `None` value in which case the None signal
    is preserved (by historical convention this meant a reset of the input
    for pending nodes).

    So for instance if a link had: `1, 2, None, 3` scheduled then the
    list would be compressed to `None, 3`

    See Also
    --------
    SignalManager.compress_signals
    """
    groups = group_by_all(reversed(signals),
                          key=lambda sig: (sig.link, sig.id))
    signals = []

    def has_none(signals):
        return any(sig.value is None for sig in signals)

    for (link, id), signals_grouped in groups:
        if len(signals_grouped) > 1 and has_none(signals_grouped[1:]):
            signals.append(signals_grouped[0])
            signals.append(Signal(link, None, id))
        else:
            signals.append(signals_grouped[0])

    return list(reversed(signals))


def dependent_nodes(scheme, node):
    # type: (Scheme, SchemeNode) -> List[SchemeNode]
    """
    Return a list of all nodes (in breadth first order) in `scheme` that
    are dependent on `node`,

    Note
    ----
    This does not include nodes only reachable by disables links.
    """
    def expand(node):
        return [link.sink_node
                for link in scheme.find_links(source_node=node)
                if link.enabled]

    nodes = list(traverse_bf(node, expand))
    assert nodes[0] is node
    # Remove the first item (`node`).
    return nodes[1:]


def traverse_bf(start, expand):
    # type: (T, Callable[[T], Iterable[T]]) -> Iterable[T]
    """
    Breadth first traversal of a DAG starting from `start`.

    Parameters
    ----------
    start : T
        A starting node
    expand : (T) -> Iterable[T]
        A function returning children of a node.
    """
    queue = deque([start])
    visited = set()
    while queue:
        item = queue.popleft()
        if item not in visited:
            yield item
            visited.add(item)
            queue.extend(expand(item))


def group_by_all(sequence, key=None):
    # type: (Iterable[V], Callable[[V], K]) -> List[Tuple[K, List[V]]]
    order_seen = []
    groups = {}
    for item in sequence:
        if key is not None:
            item_key = key(item)
        else:
            item_key = item
        if item_key in groups:
            groups[item_key].append(item)
        else:
            groups[item_key] = [item]
            order_seen.append(item_key)

    return [(key, groups[key]) for key in order_seen]


def strongly_connected_components(nodes, expand):
    """
    Return a list of strongly connected components.

    Implementation of Tarjan's SCC algorithm.
    """
    # SCC found
    components = []
    # node stack in BFS
    stack = []
    # == set(stack) : a set of all nodes in stack (for faster lookup)
    stackset = set()

    # node -> int increasing node numbering as encountered in DFS traversal
    index = {}
    # node -> int the lowest node index reachable from a node
    lowlink = {}

    indexgen = itertools.count()

    def push_node(v):
        """Push node onto the stack."""
        stack.append(v)
        stackset.add(v)
        index[v] = lowlink[v] = next(indexgen)

    def pop_scc(v):
        """Pop from the stack a SCC rooted at node v."""
        i = stack.index(v)
        scc = stack[i:]
        del stack[i:]
        stackset.difference_update(scc)
        return scc

    isvisited = lambda node: node in index

    def strong_connect(v):
        push_node(v)

        for w in expand(v):
            if not isvisited(w):
                strong_connect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in stackset:
                lowlink[v] = min(lowlink[v], index[w])

        if index[v] == lowlink[v]:
            scc = pop_scc(v)
            components.append(scc)

    for node in nodes:
        if not isvisited(node):
            strong_connect(node)

    return components

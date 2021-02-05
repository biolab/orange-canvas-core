"""
===============
Scheme Workflow
===============

The :class:`Scheme` class defines a DAG (Directed Acyclic Graph) workflow.

"""
import types
import logging
from contextlib import ExitStack
from operator import itemgetter
from collections import deque

import typing
from typing import List, Tuple, Optional, Set, Dict, Any, Mapping

from AnyQt.QtCore import QObject, QCoreApplication
from AnyQt.QtCore import pyqtSignal as Signal, pyqtProperty as Property

from .node import SchemeNode
from .link import SchemeLink, compatible_channels, _classify_connection
from .annotations import BaseSchemeAnnotation
from ..utils import check_arg, findf

from .errors import (
    SchemeCycleError, IncompatibleChannelTypeError, SinkChannelError,
    DuplicatedLinkError
)
from .events import NodeEvent, LinkEvent, AnnotationEvent, WorkflowEnvChanged

from ..registry import WidgetDescription, InputSignal, OutputSignal

if typing.TYPE_CHECKING:
    T = typing.TypeVar("T")

log = logging.getLogger(__name__)

Node = SchemeNode
Link = SchemeLink
Annotation = BaseSchemeAnnotation


class Scheme(QObject):
    """
    An :class:`QObject` subclass representing the scheme widget workflow
    with annotations.

    Parameters
    ----------
    parent : :class:`QObject`
        A parent QObject item (default `None`).
    title : str
        The scheme title.
    description : str
        A longer description of the scheme.
    env: Mapping[str, Any]
        Extra workflow environment definition (application defined).
    """
    # Flags indicating if loops are allowed in the workflow.
    NoLoops, AllowLoops, AllowSelfLoops = 0, 1, 2

    # Signal emitted when a `node` is added to the scheme.
    node_added = Signal(SchemeNode)

    # Signal emitted when a `node` is inserted to the scheme.
    node_inserted = Signal(int, Node)

    # Signal emitted when a `node` is removed from the scheme.
    node_removed = Signal(SchemeNode)

    # Signal emitted when a `link` is added to the scheme.
    link_added = Signal(SchemeLink)

    # Signal emitted when a `link` is added to the scheme.
    link_inserted = Signal(int, Link)

    # Signal emitted when a `link` is removed from the scheme.
    link_removed = Signal(SchemeLink)

    # Signal emitted when a `annotation` is added to the scheme.
    annotation_added = Signal(BaseSchemeAnnotation)

    # Signal emitted when a `annotation` is added to the scheme.
    annotation_inserted = Signal(int, BaseSchemeAnnotation)

    # Signal emitted when a `annotation` is removed from the scheme.
    annotation_removed = Signal(BaseSchemeAnnotation)

    # Signal emitted when the title of scheme changes.
    title_changed = Signal(str)

    # Signal emitted when the description of scheme changes.
    description_changed = Signal(str)

    #: Signal emitted when the associated runtime environment changes
    runtime_env_changed = Signal(str, object, object)

    def __init__(self, parent=None, title="", description="", env={},
                 **kwargs):
        # type: (Optional[QObject], str, str, Mapping[str, Any], Any) -> None
        super().__init__(parent, **kwargs)
        #: Workflow title (empty string by default).
        self.__title = title or ""
        #: Workflow description (empty string by default).
        self.__description = description or ""
        self.__annotations = []  # type: List[BaseSchemeAnnotation]
        self.__nodes = []        # type: List[SchemeNode]
        self.__links = []        # type: List[SchemeLink]
        self.__loop_flags = Scheme.NoLoops
        self.__env = dict(env)   # type: Dict[str, Any]

    @property
    def nodes(self):
        # type: () -> List[SchemeNode]
        """
        A list of all nodes (:class:`.SchemeNode`) currently in the scheme.
        """
        return list(self.__nodes)

    @property
    def links(self):
        # type: () -> List[SchemeLink]
        """
        A list of all links (:class:`.SchemeLink`) currently in the scheme.
        """
        return list(self.__links)

    @property
    def annotations(self):
        # type: () -> List[BaseSchemeAnnotation]
        """
        A list of all annotations (:class:`.BaseSchemeAnnotation`) in the
        scheme.
        """
        return list(self.__annotations)

    def set_loop_flags(self, flags):
        self.__loop_flags = flags

    def loop_flags(self):
        return self.__loop_flags

    def set_title(self, title):
        # type: (str) -> None
        """
        Set the scheme title text.
        """
        if self.__title != title:
            self.__title = title
            self.title_changed.emit(title)

    def _title(self):
        """
        The title (human readable string) of the scheme.
        """
        return self.__title

    title: str
    title = Property(str, _title, set_title)  # type: ignore

    def set_description(self, description):
        # type: (str) -> None
        """
        Set the scheme description text.
        """
        if self.__description != description:
            self.__description = description
            self.description_changed.emit(description)

    def _description(self):
        """
        Scheme description text.
        """
        return self.__description

    description: str
    description = Property(str, _description, set_description)  # type: ignore

    def add_node(self, node):
        # type: (SchemeNode) -> None
        """
        Add a node to the scheme. An error is raised if the node is
        already in the scheme.

        Parameters
        ----------
        node : :class:`.SchemeNode`
            Node instance to add to the scheme.

        """
        self.insert_node(len(self.__nodes), node)

    def insert_node(self, index: int, node: Node):
        """
        Insert `node` into self.nodes at the specified position `index`
        """
        assert isinstance(node, SchemeNode)
        check_arg(node not in self.__nodes,
                  "Node already in scheme.")
        self.__nodes.insert(index, node)

        ev = NodeEvent(NodeEvent.NodeAdded, node, index)
        QCoreApplication.sendEvent(self, ev)

        log.info("Added node %r to scheme %r." % (node.title, self.title))
        self.node_added.emit(node)
        self.node_inserted.emit(index, node)

    def new_node(self, description, title=None, position=None,
                 properties=None):
        # type: (WidgetDescription, str, Tuple[float, float], dict) -> SchemeNode
        """
        Create a new :class:`.SchemeNode` and add it to the scheme.

        Same as::

            scheme.add_node(SchemeNode(description, title, position,
                                       properties))

        Parameters
        ----------
        description : :class:`WidgetDescription`
            The new node's description.
        title : str, optional
            Optional new nodes title. By default `description.name` is used.
        position : Tuple[float, float]
            Optional position in a 2D space.
        properties : dict, optional
            A dictionary of optional extra properties.

        See also
        --------
        .SchemeNode, Scheme.add_node

        """
        if isinstance(description, WidgetDescription):
            node = SchemeNode(description, title=title, position=position,
                              properties=properties)
        else:
            raise TypeError("Expected %r, got %r." % \
                            (WidgetDescription, type(description)))

        self.add_node(node)
        return node

    def remove_node(self, node):
        # type: (SchemeNode) -> SchemeNode
        """
        Remove a `node` from the scheme. All links into and out of the
        `node` are also removed. If the node in not in the scheme an error
        is raised.

        Parameters
        ----------
        node : :class:`.SchemeNode`
            Node instance to remove.

        """
        check_arg(node in self.__nodes,
                  "Node is not in the scheme.")

        self.__remove_node_links(node)
        index = self.__nodes.index(node)
        self.__nodes.pop(index)
        ev = NodeEvent(NodeEvent.NodeRemoved, node, index)
        QCoreApplication.sendEvent(self, ev)
        log.info("Removed node %r from scheme %r." % (node.title, self.title))
        self.node_removed.emit(node)
        return node

    def __remove_node_links(self, node):
        # type: (SchemeNode) -> None
        """
        Remove all links for node.
        """
        links_in, links_out = [], []
        for link in self.__links:
            if link.source_node is node:
                links_out.append(link)
            elif link.sink_node is node:
                links_in.append(link)

        for link in links_out + links_in:
            self.remove_link(link)

    def insert_link(self, index: int, link: Link):
        """
        Insert `link` into `self.links` at the specified position `index`.
        """
        assert isinstance(link, SchemeLink)
        self.check_connect(link)
        self.__links.insert(index, link)
        source_index, _ = findf(
            enumerate(self.find_links(source_node=link.source_node)),
            lambda t: t[1] == link,
            default=(-1, None)
        )
        sink_index, _ = findf(
            enumerate(self.find_links(sink_node=link.sink_node)),
            lambda t: t[1] == link,
            default=(-1, None)
        )
        assert sink_index != -1 and source_index != -1
        QCoreApplication.sendEvent(
            link.source_node,
            LinkEvent(LinkEvent.OutputLinkAdded, link, source_index)
        )
        QCoreApplication.sendEvent(
            link.sink_node,
            LinkEvent(LinkEvent.InputLinkAdded, link, sink_index)
        )
        QCoreApplication.sendEvent(
            self, LinkEvent(LinkEvent.LinkAdded, link, index)
        )
        log.info("Added link %r (%r) -> %r (%r) to scheme %r." % \
                 (link.source_node.title, link.source_channel.name,
                  link.sink_node.title, link.sink_channel.name,
                  self.title)
                 )
        self.link_inserted.emit(index, link)
        self.link_added.emit(link)

    def add_link(self, link):
        # type: (SchemeLink) -> None
        """
        Add a `link` to the scheme.

        Parameters
        ----------
        link : :class:`.SchemeLink`
            An initialized link instance to add to the scheme.

        """
        self.insert_link(len(self.__links), link)

    def new_link(self, source_node, source_channel,
                 sink_node, sink_channel):
        # type: (SchemeNode, OutputSignal, SchemeNode, InputSignal) -> SchemeLink
        """
        Create a new :class:`.SchemeLink` from arguments and add it to
        the scheme. The new link is returned.

        Parameters
        ----------
        source_node : :class:`.SchemeNode`
            Source node of the new link.
        source_channel : :class:`.OutputSignal`
            Source channel of the new node. The instance must be from
            ``source_node.output_channels()``
        sink_node : :class:`.SchemeNode`
            Sink node of the new link.
        sink_channel : :class:`.InputSignal`
            Sink channel of the new node. The instance must be from
            ``sink_node.input_channels()``

        See also
        --------
        .SchemeLink, Scheme.add_link

        """
        link = SchemeLink(source_node, source_channel,
                          sink_node, sink_channel)
        self.add_link(link)
        return link

    def remove_link(self, link):
        # type: (SchemeLink) -> None
        """
        Remove a link from the scheme.

        Parameters
        ----------
        link : :class:`.SchemeLink`
            Link instance to remove.

        """
        check_arg(link in self.__links,
                  "Link is not in the scheme.")
        source_index, _ = findf(
            enumerate(self.find_links(source_node=link.source_node)),
            lambda t: t[1] == link,
            default=(-1, None)
        )
        sink_index, _ = findf(
            enumerate(self.find_links(sink_node=link.sink_node)),
            lambda t: t[1] == link,
            default=(-1, None)
        )
        assert sink_index != -1 and source_index != -1
        index = self.__links.index(link)
        self.__links.pop(index)
        QCoreApplication.sendEvent(
            link.sink_node,
            LinkEvent(LinkEvent.InputLinkRemoved, link, sink_index)
        )
        QCoreApplication.sendEvent(
            link.source_node,
            LinkEvent(LinkEvent.OutputLinkRemoved, link, source_index)
        )
        QCoreApplication.sendEvent(
            self, LinkEvent(LinkEvent.LinkRemoved, link, index)
        )
        log.info("Removed link %r (%r) -> %r (%r) from scheme %r." % \
                 (link.source_node.title, link.source_channel.name,
                  link.sink_node.title, link.sink_channel.name,
                  self.title)
                 )
        self.link_removed.emit(link)

    def check_connect(self, link):
        # type: (SchemeLink) -> None
        """
        Check if the `link` can be added to the scheme and raise an
        appropriate exception.

        Can raise:
            - :class:`.SchemeCycleError` if the `link` would introduce a loop
              in the graph which does not allow loops.
            - :class:`.IncompatibleChannelTypeError` if the channel types are
              not compatible
            - :class:`.SinkChannelError` if a sink channel has a `Single` flag
              specification and the channel is already connected.
            - :class:`.DuplicatedLinkError` if a `link` duplicates an already
              present link.

        """
        if not self.loop_flags() & Scheme.AllowSelfLoops and \
                link.source_node is link.sink_node:
            raise SchemeCycleError("Cannot create self cycle in the scheme")
        elif not self.loop_flags() & Scheme.AllowLoops and \
                self.creates_cycle(link):
            raise SchemeCycleError("Cannot create cycles in the scheme")

        if not self.compatible_channels(link):
            raise IncompatibleChannelTypeError(
                    "Cannot connect %r to %r." \
                    % (link.source_channel.type, link.sink_channel.type)
                )

        links = self.find_links(source_node=link.source_node,
                                source_channel=link.source_channel,
                                sink_node=link.sink_node,
                                sink_channel=link.sink_channel)

        if links:
            raise DuplicatedLinkError(
                    "A link from %r (%r) -> %r (%r) already exists" \
                    % (link.source_node.title, link.source_channel.name,
                       link.sink_node.title, link.sink_channel.name)
                )

        if link.sink_channel.single:
            links = self.find_links(sink_node=link.sink_node,
                                    sink_channel=link.sink_channel)
            if links:
                raise SinkChannelError(
                        "%r is already connected." % link.sink_channel.name
                    )

    def creates_cycle(self, link):
        # type: (SchemeLink) -> bool
        """
        Return `True` if `link` would introduce a cycle in the scheme.

        Parameters
        ----------
        link : :class:`.SchemeLink`
        """
        assert isinstance(link, SchemeLink)
        source_node, sink_node = link.source_node, link.sink_node
        upstream = self.upstream_nodes(source_node)
        upstream.add(source_node)
        return sink_node in upstream

    def compatible_channels(self, link):
        # type: (SchemeLink) -> bool
        """
        Return `True` if the channels in `link` have compatible types.

        Parameters
        ----------
        link : :class:`.SchemeLink`
        """
        assert isinstance(link, SchemeLink)
        return compatible_channels(link.source_channel, link.sink_channel)

    def can_connect(self, link):
        # type: (SchemeLink) -> bool
        """
        Return `True` if `link` can be added to the scheme.

        See also
        --------
        Scheme.check_connect

        """
        assert isinstance(link, SchemeLink)
        try:
            self.check_connect(link)
            return True
        except (SchemeCycleError, IncompatibleChannelTypeError,
                SinkChannelError, DuplicatedLinkError):
            return False

    def upstream_nodes(self, start_node):
        # type: (SchemeNode) -> Set[SchemeNode]
        """
        Return a set of all nodes upstream from `start_node` (i.e.
        all ancestor nodes).

        Parameters
        ----------
        start_node : :class:`.SchemeNode`

        """
        visited = set()  # type: Set[SchemeNode]
        queue = deque([start_node])
        while queue:
            node = queue.popleft()
            snodes = [link.source_node for link in self.input_links(node)]
            for source_node in snodes:
                if source_node not in visited:
                    queue.append(source_node)

            visited.add(node)
        visited.remove(start_node)
        return visited

    def downstream_nodes(self, start_node):
        # type: (SchemeNode) -> Set[SchemeNode]
        """
        Return a set of all nodes downstream from `start_node`.

        Parameters
        ----------
        start_node : :class:`.SchemeNode`

        """
        visited = set()  # type: Set[SchemeNode]
        queue = deque([start_node])
        while queue:
            node = queue.popleft()
            snodes = [link.sink_node for link in self.output_links(node)]
            for source_node in snodes:
                if source_node not in visited:
                    queue.append(source_node)

            visited.add(node)
        visited.remove(start_node)
        return visited

    def is_ancestor(self, node, child):
        # type: (SchemeNode, SchemeNode) -> bool
        """
        Return True if `node` is an ancestor node of `child` (is upstream
        of the child in the workflow). Both nodes must be in the scheme.

        Parameters
        ----------
        node : :class:`.SchemeNode`
        child : :class:`.SchemeNode`

        """
        return child in self.downstream_nodes(node)

    def children(self, node):
        # type: (SchemeNode) -> Set[SchemeNode]
        """
        Return a set of all children of `node`.
        """
        return set(link.sink_node for link in self.output_links(node))

    def parents(self, node):
        # type: (SchemeNode) -> Set[SchemeNode]
        """
        Return a set of all parents of `node`.
        """
        return set(link.source_node for link in self.input_links(node))

    def input_links(self, node):
        # type: (SchemeNode) -> List[SchemeLink]
        """
        Return a list of all input links (:class:`.SchemeLink`) connected
        to the `node` instance.
        """
        return self.find_links(sink_node=node)

    def output_links(self, node):
        # type: (SchemeNode) -> List[SchemeLink]
        """
        Return a list of all output links (:class:`.SchemeLink`) connected
        to the `node` instance.
        """
        return self.find_links(source_node=node)

    def find_links(self, source_node=None, source_channel=None,
                   sink_node=None, sink_channel=None):
        # type: (Optional[SchemeNode], Optional[OutputSignal], Optional[SchemeNode], Optional[InputSignal]) -> List[SchemeLink]
        # TODO: Speedup - keep index of links by nodes and channels
        result = []

        def match(query, value):
            # type: (Optional[T], T) -> bool
            return query is None or value == query

        for link in self.__links:
            if match(source_node, link.source_node) and \
                    match(sink_node, link.sink_node) and \
                    match(source_channel, link.source_channel) and \
                    match(sink_channel, link.sink_channel):
                result.append(link)

        return result

    def propose_links(
            self,
            source_node: SchemeNode,
            sink_node: SchemeNode,
            source_signal: Optional[OutputSignal] = None,
            sink_signal: Optional[InputSignal] = None
    ) -> List[Tuple[OutputSignal, InputSignal, int]]:
        """
        Return a list of ordered (:class:`OutputSignal`,
        :class:`InputSignal`, weight) tuples that could be added to
        the scheme between `source_node` and `sink_node`.

        .. note:: This can depend on the links already in the scheme.

        """
        if source_node is sink_node and \
                not self.loop_flags() & Scheme.AllowSelfLoops:
            # Self loops are not enabled
            return []

        elif not self.loop_flags() & Scheme.AllowLoops and \
                self.is_ancestor(sink_node, source_node):
            # Loops are not enabled.
            return []

        outputs = [source_signal] if source_signal \
             else source_node.output_channels()
        inputs = [sink_signal] if sink_signal \
            else sink_node.input_channels()

        # Get existing links to sink channels that are Single.
        links = self.find_links(None, None, sink_node)
        already_connected_sinks = [link.sink_channel for link in links \
                                   if link.sink_channel.single]

        def weight(out_c, in_c):
            # type: (OutputSignal, InputSignal) -> int
            if out_c.explicit or in_c.explicit:
                # Zero weight for explicit links
                weight = 0
            else:
                # Does the connection type check (can only ever be False for
                # dynamic signals)
                type_checks, _ = _classify_connection(out_c, in_c)
                # Dynamic signals that require runtime instance type check
                # are considered last.
                check = [type_checks,
                         in_c not in already_connected_sinks,
                         bool(in_c.default),
                         bool(out_c.default)
                         ]
                weights = [2 ** i for i in range(len(check), 0, -1)]
                weight = sum([w for w, c in zip(weights, check) if c])
            return weight

        proposed_links = []
        for out_c in outputs:
            for in_c in inputs:
                if compatible_channels(out_c, in_c):
                    proposed_links.append((out_c, in_c, weight(out_c, in_c)))

        return sorted(proposed_links, key=itemgetter(-1), reverse=True)

    def insert_annotation(self, index: int, annotation: Annotation) -> None:
        """
        Insert `annotation` into `self.annotations` at the specified
        position `index`.
        """
        assert isinstance(annotation, BaseSchemeAnnotation)
        if annotation in self.__annotations:
            raise ValueError("Cannot add the same annotation multiple times")
        self.__annotations.insert(index, annotation)
        ev = AnnotationEvent(AnnotationEvent.AnnotationAdded,
                             annotation, index)
        QCoreApplication.sendEvent(self, ev)
        self.annotation_inserted.emit(index, annotation)
        self.annotation_added.emit(annotation)

    def add_annotation(self, annotation):
        # type: (BaseSchemeAnnotation) -> None
        """
        Add an annotation (:class:`BaseSchemeAnnotation` subclass) instance
        to the scheme.
        """
        self.insert_annotation(len(self.__annotations), annotation)

    def remove_annotation(self, annotation):
        # type: (BaseSchemeAnnotation) -> None
        """
        Remove the `annotation` instance from the scheme.
        """
        index = self.__annotations.index(annotation)
        self.__annotations.pop(index)
        ev = AnnotationEvent(AnnotationEvent.AnnotationRemoved,
                             annotation, index)
        QCoreApplication.sendEvent(self, ev)
        self.annotation_removed.emit(annotation)

    def clear(self):
        # type: () -> None
        """
        Remove all nodes, links, and annotation items from the scheme.
        """
        def is_terminal(node):
            # type: (SchemeNode) -> bool
            return not bool(self.find_links(source_node=node))

        while self.nodes:
            terminal_nodes = filter(is_terminal, self.nodes)
            for node in terminal_nodes:
                self.remove_node(node)

        for annotation in self.annotations:
            self.remove_annotation(annotation)

        assert not (self.nodes or self.links or self.annotations)

    def sync_node_properties(self):
        # type: () -> None
        """
        Called before saving, allowing a subclass to update/sync.

        The default implementation does nothing.

        """
        pass

    def save_to(self, stream, pretty=True, **kwargs):
        """
        Save the scheme as an xml formatted file to `stream`

        See also
        --------
        readwrite.scheme_to_ows_stream
        """
        with ExitStack() as exitstack:
            if isinstance(stream, str):
                stream = exitstack.enter_context(open(stream, "wb"))
            self.sync_node_properties()
            readwrite.scheme_to_ows_stream(self, stream, pretty, **kwargs)

    def load_from(self, stream, *args, **kwargs):
        """
        Load the scheme from xml formatted `stream`.

        Any extra arguments are passed to `readwrite.scheme_load`

        See Also
        --------
        readwrite.scheme_load
        """
        if self.__nodes or self.__links or self.__annotations:
            raise ValueError("Scheme is not empty.")

        with ExitStack() as exitstack:
            if isinstance(stream, str):
                stream = exitstack.enter_context(open(stream, "rb"))
            readwrite.scheme_load(self, stream, *args, **kwargs)

    def set_runtime_env(self, key, value):
        # type: (str, Any) -> None
        """
        Set a runtime environment variable `key` to `value`
        """
        oldvalue = self.__env.get(key, None)
        if value != oldvalue:
            self.__env[key] = value
            QCoreApplication.sendEvent(
                self, WorkflowEnvChanged(key, value, oldvalue)
            )
            self.runtime_env_changed.emit(key, value, oldvalue)

    def get_runtime_env(self, key, default=None):
        # type: (str, Any) -> Any
        """
        Return a runtime environment variable for `key`.
        """
        return self.__env.get(key, default)

    def runtime_env(self):
        # type: () -> Mapping[str, Any]
        """
        Return (a view to) the full runtime environment.

        The return value is a types.MappingProxyType of the
        underlying environment dictionary. Changes to the env.
        will be reflected in it.
        """
        return types.MappingProxyType(self.__env)

    class WindowGroup(types.SimpleNamespace):
        name = None     # type: str
        default = None  # type: bool
        state = None    # type: List[Tuple[SchemeNode, bytes]]

        def __init__(self, name="", default=False, state=[]):
            super().__init__(name=name, default=default, state=state)

    window_group_presets_changed = Signal()

    def window_group_presets(self):
        # type: () -> List[WindowGroup]
        """
        Return a collection of preset window groups and their encoded states.

        The base implementation returns an empty list.
        """
        return self.property("_presets") or []

    def set_window_group_presets(self, groups):
        # type: (List[WindowGroup]) -> None
        self.setProperty("_presets", groups)
        self.window_group_presets_changed.emit()


from . import readwrite

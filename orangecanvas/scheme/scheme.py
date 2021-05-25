"""
===============
Scheme Workflow
===============

The :class:`Scheme` class defines a model for a hierarchical DAG (Directed
Acyclic Graph) workflow. The :func:`Scheme.root()` is the top level container
which can contains other :class:`.Node` and :class:`.MetaNode` instances.
"""
import types
import logging
import warnings
from contextlib import ExitStack

import typing
from typing import List, Tuple, Optional, Set, Dict, Any, Mapping, Sequence

from AnyQt.QtCore import QObject, QCoreApplication
from AnyQt.QtCore import pyqtSignal as Signal, pyqtProperty as Property


from .node import SchemeNode, Node
from .metanode import (
    MetaNode, node_dependents, node_dependencies, find_links,
    all_links_recursive
)
from .link import Link, compatible_channels
from .annotations import Annotation

from .errors import (
    SchemeCycleError, IncompatibleChannelTypeError, SinkChannelError,
    DuplicatedLinkError
)
from .events import WorkflowEnvChanged
from ..utils import unique
from ..utils.graph import traverse_bf
from ..registry import WidgetDescription, InputSignal, OutputSignal

if typing.TYPE_CHECKING:
    T = typing.TypeVar("T")

log = logging.getLogger(__name__)


class Scheme(QObject):
    """
    An :class:`QObject` subclass representing a hierarchical workflow with
    annotations.

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
    node_added = Signal(Node, MetaNode)

    # Signal emitted when a `node` is inserted to the scheme.
    node_inserted = Signal(int, Node, MetaNode)

    # Signal emitted when a `node` is removed from the scheme.
    node_removed = Signal(Node, MetaNode)

    # Signal emitted when a `link` is added to the scheme.
    link_added = Signal(Link, MetaNode)

    # Signal emitted when a `link` is added to the scheme.
    link_inserted = Signal(int, Link, MetaNode)

    # Signal emitted when a `link` is removed from the scheme.
    link_removed = Signal(Link, MetaNode)

    # Signal emitted when a `annotation` is added to the scheme.
    annotation_added = Signal(Annotation, MetaNode)

    # Signal emitted when a `annotation` is added to the scheme.
    annotation_inserted = Signal(int, Annotation, MetaNode)

    # Signal emitted when a `annotation` is removed from the scheme.
    annotation_removed = Signal(Annotation, MetaNode)

    # Signal emitted when the title of scheme changes.
    title_changed = Signal(str)

    # Signal emitted when the description of scheme changes.
    description_changed = Signal(str)

    # Signal emitted when the associated runtime environment changes
    runtime_env_changed = Signal(str, object, object)

    # Signal emitted by subclass upon a detected settings change
    node_properties_changed = Signal()

    def __init__(self, parent=None, title="", description="", env={},
                 **kwargs):
        # type: (Optional[QObject], str, str, Mapping[str, Any], Any) -> None
        super().__init__(parent, **kwargs)
        #: Workflow title (empty string by default).
        self.__title = title or ""
        #: Workflow description (empty string by default).
        self.__description = description or ""
        self.__root = MetaNode(self.tr("Root"))
        self.__root._set_workflow(self)
        self.__loop_flags = Scheme.NoLoops
        self.__env = dict(env)   # type: Dict[str, Any]

    @property
    def nodes(self):
        # type: () -> List[Node]
        """
        A list of all nodes (:class:`.Node`) currently in the scheme.

        .. deprecated:: 0.2.0
            Use `root().nodes()`
        """
        warnings.warn("'nodes' is deprecated use 'root().nodes()'",
                      DeprecationWarning, stacklevel=2)
        return self.__root.nodes()

    def all_nodes(self) -> List[Node]:
        """
        Return a list of all subnodes including all subnodes of subnodes.

        Equivalent to `root().all_nodes()`
        """
        return self.__root.all_nodes()

    @property
    def links(self):
        # type: () -> List[Link]
        """
        A list of all links (:class:`.Link`) currently in the scheme.

        .. deprecated:: 0.2.0
            Use `root().links()`
        """
        warnings.warn("'links' is deprecated use 'root().links()'",
                      DeprecationWarning, stacklevel=2)
        return self.__root.links()

    def all_links(self) -> List[Link]:
        """
        Return a list of all links including all links in subnodes.

        Equivalent to `root().all_links()`
        """
        return self.__root.all_links()

    @property
    def annotations(self):
        # type: () -> List[Annotation]
        """
        A list of all annotations (:class:`.Annotation`) in the scheme.

        .. deprecated:: 0.2.0
            Use `root().annotations()`
        """
        warnings.warn("'annotations' is deprecated use 'root().annotations()'",
                      DeprecationWarning, stacklevel=2)
        return self.__root.annotations()

    def all_annotations(self):
        """
        Return a list of all annotations including all annotations in subnodes.

        Equivalent to `root().all_annotations()`
        """
        return self.__root.all_annotations()

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
            self.__root.set_title(title)
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

    def root(self) -> MetaNode:
        """
        Return the root :class:`MetaNode`.

        This is the top level node containing the whole workflow.
        """
        return self.__root

    def add_node(self, node: Node, parent: MetaNode = None) -> None:
        """
        Add a node to the scheme. An error is raised if the node is
        already in the scheme.

        Parameters
        ----------
        node : Node
            Node instance to add to the scheme.
        parent: MetaNode
            An optional meta node into which the node is inserted. If `None` the
            node is inserted into the `root()` meta node.
        """
        if parent is None:
            parent = self.__root
        parent.add_node(node)

    def insert_node(self, index: int, node: Node, parent: MetaNode = None):
        """
        Insert `node` into self.nodes at the specified position `index`
        """
        if parent is None:
            parent = self.__root
        parent.insert_node(index, node)

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
            node = SchemeNode(
                description, title=title, position=position or (0, 0),
                properties=properties)
        else:
            raise TypeError("Expected %r, got %r." %
                            (WidgetDescription, type(description)))

        self.add_node(node)
        return node

    def remove_node(self, node):
        # type: (Node) -> Node
        """
        Remove a `node` from the scheme. All links into and out of the
        `node` are also removed. If the node in not in the scheme an error
        is raised.

        Parameters
        ----------
        node : :class:`.Node`
            Node instance to remove.
        """
        assert node.workflow() is self
        parent = node.parent_node()
        assert parent is not None
        parent.remove_node(node)
        return node

    def insert_link(self, index: int, link: Link, parent: MetaNode = None):
        """
        Insert `link` into `self.links` at the specified position `index`.
        """
        assert link.workflow() is None, "Link already in a workflow."
        if parent is None:
            parent = self.__root
        parent.insert_link(index, link)

    def add_link(self, link, parent=None):
        # type: (Link, MetaNode) -> None
        """
        Add a `link` to the scheme.

        Parameters
        ----------
        link : :class:`.Link`
            An initialized link instance to add to the scheme.

        """
        if parent is None:
            parent = self.__root
        parent.add_link(link)

    def new_link(self, source_node, source_channel,
                 sink_node, sink_channel):
        # type: (Node, OutputSignal, Node, InputSignal) -> Link
        """
        Create a new :class:`.Link` from arguments and add it to
        the scheme. The new link is returned.

        Parameters
        ----------
        source_node : :class:`.Node`
            Source node of the new link.
        source_channel : :class:`.OutputSignal`
            Source channel of the new node. The instance must be from
            ``source_node.output_channels()``
        sink_node : :class:`.Node`
            Sink node of the new link.
        sink_channel : :class:`.InputSignal`
            Sink channel of the new node. The instance must be from
            ``sink_node.input_channels()``

        See also
        --------
        .Link, Scheme.add_link

        """
        link = Link(source_node, source_channel, sink_node, sink_channel)
        self.add_link(link)
        return link

    def remove_link(self, link):
        # type: (Link) -> None
        """
        Remove a link from the scheme.

        Parameters
        ----------
        link : :class:`.Link`
            Link instance to remove.

        """
        assert link.workflow() is self
        parent = link.parent_node()
        assert parent is not None
        parent.remove_link(link)

    def check_connect(self, link):
        # type: (Link) -> None
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
        # type: (Link) -> bool
        """
        Return `True` if `link` would introduce a cycle in the scheme.

        Parameters
        ----------
        link : :class:`.Link`
        """
        assert isinstance(link, Link)
        source_node, sink_node = link.source_node, link.sink_node
        upstream = self.upstream_nodes(source_node)
        upstream.add(source_node)
        return sink_node in upstream

    def compatible_channels(self, link):
        # type: (Link) -> bool
        """
        Return `True` if the channels in `link` have compatible types.

        Parameters
        ----------
        link : :class:`.Link`
        """
        assert isinstance(link, Link)
        return compatible_channels(link.source_channel, link.sink_channel)

    def can_connect(self, link):
        # type: (Link) -> bool
        """
        Return `True` if `link` can be added to the scheme.

        See also
        --------
        Scheme.check_connect

        """
        assert isinstance(link, Link)
        try:
            self.check_connect(link)
            return True
        except (SchemeCycleError, IncompatibleChannelTypeError,
                SinkChannelError, DuplicatedLinkError):
            return False

    def upstream_nodes(self, start_node):
        # type: (Node) -> Set[Node]
        """
        Return a set of all nodes upstream from `start_node` (i.e.
        all ancestor nodes).

        Parameters
        ----------
        start_node : :class:`.Node`
        """
        return set(traverse_bf(start_node, node_dependencies))

    def downstream_nodes(self, start_node):
        # type: (Node) -> Set[Node]
        """
        Return a set of all nodes downstream from `start_node`.

        Parameters
        ----------
        start_node : :class:`.Node`
        """
        return set(traverse_bf(start_node, node_dependents))

    def is_ancestor(self, node, child):
        # type: (Node, Node) -> bool
        """
        Return True if `node` is an ancestor node of `child` (is upstream
        of the child in the workflow). Both nodes must be in the scheme.

        Parameters
        ----------
        node : :class:`.Node`
        child : :class:`.Node`
        """
        return child in self.downstream_nodes(node)

    def children(self, node):  # type: (Node) -> Set[Node]
        """
        .. deprecated:: 0.2.0
           Use `child_nodes()`
        """
        warnings.warn("'children()' is deprecated, use 'child_nodes()'",
                      DeprecationWarning, stacklevel=2)
        return set(self.child_nodes(node))

    def child_nodes(self, node: Node) -> Sequence[Node]:
        """
        Return all immediate descendant nodes of `node`.
        """
        return list(unique(link.sink_node for link in self.output_links(node)))

    def parents(self, node):  # type: (Node) -> Set[Node]
        """
        .. deprecated:: 0.2.0
           Use parent_nodes()
        """
        warnings.warn("'parents()' is deprecated, use 'parent_nodes()'",
                      DeprecationWarning, stacklevel=2)
        return set(self.parent_nodes(node))

    def parent_nodes(self, node: Node) -> Sequence[Node]:
        """
        Return all immediate ancestor nodes of `node`.
        """
        return list(unique(link.source_node for link in self.input_links(node)))

    def input_links(self, node):
        # type: (Node) -> List[Link]
        """
        Return a list of all input links (:class:`.Link`) connected
        to the `node` instance.
        """
        return self.find_links(sink_node=node)

    def output_links(self, node):
        # type: (Node) -> List[Link]
        """
        Return a list of all output links (:class:`.Link`) connected
        to the `node` instance.
        """
        return self.find_links(source_node=node)

    def find_links(
            self,
            source_node: Optional[Node] = None,
            source_channel: Optional[OutputSignal] = None,
            sink_node: Optional[Node] = None,
            sink_channel: Optional[InputSignal] = None
    ) -> List[Link]:
        """
        Find links in this workflow that match the specified
        {source,sink}_{node,channel} arguments (if `None` any will match).
        """
        return find_links(
            all_links_recursive(self.__root),
            source_node=source_node, source_channel=source_channel,
            sink_node=sink_node, sink_channel=sink_channel
        )

    def propose_links(
            self,
            source_node: Node,
            sink_node: Node,
            source_signal: Optional[OutputSignal] = None,
            sink_signal: Optional[InputSignal] = None
    ) -> List[Tuple[OutputSignal, InputSignal, int]]:
        """
        Return a list of ordered (:class:`OutputSignal`,
        :class:`InputSignal`, weight) tuples that could be added to
        the scheme between `source_node` and `sink_node`.

        .. note:: This can depend on the links already in the scheme.

        .. deprecated:: 0.2.0
           Use :func:`orangecanvas.document.interactions.propose_links`
        """
        from orangecanvas.document.interactions import propose_links
        warnings.warn("'propose_links' is deprecated use "
                      "'orangecanvas.document.interactions.propose_links'",
                      DeprecationWarning, stacklevel=2)
        return propose_links(
            self, source_node, sink_node, source_signal, sink_signal
        )

    def insert_annotation(self, index: int, annotation: Annotation, parent: MetaNode = None) -> None:
        """
        Insert `annotation` into `parent` at the specified position `index`.

        If `parent` is `None` then insert into `self.root()`
        """
        if parent is None:
            parent = self.__root
        parent.insert_annotation(index, annotation)

    def add_annotation(self, annotation: Annotation, parent: MetaNode = None) -> None:
        """
        Add an annotation (:class:`Annotation` subclass) instance to `parent`.

        If `parent` is `None` then insert into `self.root()`
        """
        if parent is None:
            parent = self.__root
        parent.add_annotation(annotation)

    def remove_annotation(self, annotation):
        # type: (Annotation) -> None
        """
        Remove the `annotation` instance from the scheme.
        """
        assert annotation.workflow() is self
        parent = annotation.parent_node()
        assert parent is not None
        parent.remove_annotation(annotation)

    def clear(self):
        # type: () -> None
        """
        Remove all nodes, links, and annotation items from the scheme.
        """
        self.__root.clear()

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
        root = self.__root
        if root.nodes() or root.links() or root.links():
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

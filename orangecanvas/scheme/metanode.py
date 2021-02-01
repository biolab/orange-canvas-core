from itertools import chain
from typing import TYPE_CHECKING, Optional, List, Iterable, TypeVar, Sequence

from AnyQt.QtCore import Signal, QCoreApplication

from ..registry import InputSignal, OutputSignal
from ..utils import findf, unique
from ..utils.graph import traverse_bf
from .node import Node
from .link import Link, compatible_channels
from .annotations import Annotation
from .events import NodeEvent, LinkEvent, AnnotationEvent
from .errors import (
    DuplicatedLinkError, SinkChannelError, SchemeCycleError,
    IncompatibleChannelTypeError
)

if TYPE_CHECKING:
    from . import Workflow


class MetaNode(Node):
    """
    A representation of a meta workflow node (a grouping of nodes defining
    a subgraph group within a workflow).

    Inputs and outputs to the meta node are defined by adding `InputNode` and
    `OutputNode` instances.
    """
    #: Emitted when a new subnode is inserted at index
    node_inserted = Signal(int, Node)
    #: Emitted when a subnode is removed
    node_removed = Signal(Node)

    #: Emitted when a link is inserted at index
    link_inserted = Signal(int, Link)
    #: Emitted when a link is removed
    link_removed = Signal(Link)

    #: Emitted when a annotation is inserted at index
    annotation_inserted = Signal(int, Annotation)
    #: Emitted when a annotation is removed
    annotation_removed = Signal(Annotation)

    def __init__(self, title="", position=(0, 0), **kwargs):
        super().__init__(title, position, **kwargs)
        self.__nodes: List[Node] = []
        self.__links: List[Link] = []
        self.__annotations: List[Annotation] = []

    def nodes(self) -> List[Node]:
        """Return a list of subnodes."""
        return list(self.__nodes)

    def all_nodes(self) -> List[Node]:
        """Return a list of all subnodes including all subnodes of subnodes.

        I.e. recursive `nodes()`
        """
        return list(all_nodes_recursive(self))

    def links(self) -> List[Link]:
        """Return a list of all links."""
        return list(self.__links)

    def all_links(self) -> List[Link]:
        """
        Return a list of all links including all links in subnodes.

        I.e. recursive `links()`
        """
        return list(all_links_recursive(self))

    def annotations(self) -> List[Annotation]:
        """Return a list of all annotations."""
        return list(self.__annotations)

    def all_annotations(self) -> List[Annotation]:
        """
        Return a list of all annotations including all annotations in subnodes.

        I.e. recursive `annotations()`
        """
        return list(all_annotations_recursive(self))

    def input_nodes(self) -> List['InputNode']:
        """Return a list of all `InputNode`\\s."""
        return [node for node in self.__nodes if isinstance(node, InputNode)]

    def output_nodes(self) -> List['OutputNode']:
        """Return a list of all `OutputNode`\\s."""
        return [node for node in self.__nodes if isinstance(node, OutputNode)]

    def create_input_node(self, input: InputSignal):
        """Create and add a new :class:`InputNode` instance for `input`"""
        output = OutputSignal(
            input.name, input.types, id=input.id, flags=input.flags
        )
        node = InputNode(input, output)
        node.set_title(input.name)
        self.add_node(node)
        return node

    def create_output_node(self, output: OutputSignal):
        """Create and add a new :class:`OutputNode` instance for `output`"""
        input = InputSignal(
            output.name, output.types, "-", flags=output.flags
        )
        node = OutputNode(input, output)
        node.set_title(output.name)
        self.add_node(node)
        return node

    def remove_input_channel(self, index: int) -> InputSignal:
        """Reimplemented"""
        parent = self.parent_node()
        if parent is not None:
            chn = self.input_channels()[index]
            in_node = self.node_for_input_channel(chn)
            if in_node is not None:
                links = parent.find_links(
                    sink_node=in_node, sink_channel=chn
                )
                for link in links:
                    parent.remove_link(link)
        return super().remove_input_channel(index)

    def remove_output_channel(self, index: int) -> OutputSignal:
        """Reimplemented"""
        parent = self.parent_node()
        if parent is not None:
            chn = self.output_channels()[index]
            out_node = self.node_for_output_channel(chn)
            if out_node is not None:
                links = parent.find_links(
                    source_node=out_node, source_channel=chn
                )
                for link in links:
                    parent.remove_link(link)
        return super().remove_output_channel(index)

    def add_node(self, node: Node):
        """
        Add the `node` to this meta node.

        An error is raised if the `node` is already part if a workflow.
        """
        self.insert_node(len(self.__nodes), node)

    def insert_node(self, index: int, node: Node):
        """
        Insert the `node` into `self.nodes()` at the specified position `index`.

        An error is raised if the `node` is already part if a workflow.
        """
        if node.workflow() is not None:
            raise RuntimeError("'node' is already in a workflow")
        workflow = self.workflow()
        self.__nodes.insert(index, node)
        if isinstance(node, InputNode):
            self.add_input_channel(node.sink_channel)
        elif isinstance(node, OutputNode):
            self.add_output_channel(node.source_channel)
        node._set_parent_node(self)
        node._set_workflow(workflow)
        ev = NodeEvent(NodeEvent.NodeAdded, node, index, self)
        QCoreApplication.sendEvent(self, ev)
        if workflow is not None:
            QCoreApplication.sendEvent(workflow, ev)
            workflow.node_added.emit(node, self)
            workflow.node_inserted.emit(index, node, self)
        self.node_inserted.emit(index, node)

    def remove_node(self, node: Node) -> None:
        """Remove the `node` from this meta node."""
        workflow = self.workflow()
        if isinstance(node, InputNode):
            self.remove_input_channel(self.input_channels().index(node.sink_channel))
        elif isinstance(node, OutputNode):
            self.remove_output_channel(self.output_channels().index(node.source_channel))
        self.__remove_node_links(node)
        index = self.__nodes.index(node)
        self.__nodes.pop(index)

        node._set_parent_node(None)
        node._set_workflow(None)
        ev = NodeEvent(NodeEvent.NodeRemoved, node, index, self)
        QCoreApplication.sendEvent(self, ev)
        if workflow is not None:
            QCoreApplication.sendEvent(workflow, ev)
            workflow.node_removed.emit(node, self)
        self.node_removed.emit(node)

    def __remove_node_links(self, node: Node):
        links = self.__links
        links_out = [link for link in links if link.source_node is node]
        links_in = [link for link in links if link.sink_node is node]
        for link in chain(links_out, links_in):
            self.remove_link(link)

    def input_links(self, node) -> List[Link]:
        """Return all input links to this meta node."""
        return self.find_links(sink_node=node)

    def output_links(self, node) -> List[Link]:
        """Return all output links from this meta node."""
        return self.find_links(source_node=node)

    def find_links(
            self, source_node: Optional[Node] = None,
            source_channel: Optional[OutputSignal] = None,
            sink_node: Optional[Node] = None,
            sink_channel: Optional[InputSignal] = None
    ) -> List[Link]:
        """Find and return links based on matching criteria."""
        return find_links(
            self.__links, source_node, source_channel, sink_node, sink_channel
        )

    def add_link(self, link: Link):
        """
        Add `link` to this meta node.

        `link.source_node` and `link.sink_node` must already be added.
        """
        self.insert_link(len(self.__links), link)

    def insert_link(self, index: int, link: Link):
        """
        Insert `link` into `self.links()` at the specified position `index`.
        """
        if link.workflow() is not None:
            raise RuntimeError("'link' is already in a workflow")
        if link.source_node not in self.__nodes:
            raise RuntimeError("'link.source_node' is not in self.nodes()")
        if link.sink_node not in self.__nodes:
            raise RuntimeError("'link.sink_node' is not in self.nodes()")
        workflow = self.workflow()
        self.__check_connect(link)
        self.__links.insert(index, link)
        link._set_workflow(workflow)
        link._set_parent_node(self)
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
            LinkEvent(LinkEvent.OutputLinkAdded, link, source_index, self)
        )
        QCoreApplication.sendEvent(
            link.sink_node,
            LinkEvent(LinkEvent.InputLinkAdded, link, sink_index, self)
        )
        ev = LinkEvent(LinkEvent.LinkAdded, link, index, self)
        QCoreApplication.sendEvent(self, ev)
        if workflow is not None:
            QCoreApplication.sendEvent(workflow, ev)
            workflow.link_inserted.emit(index, link, self)
            workflow.link_added.emit(link, self)
        self.link_inserted.emit(index, link)

    def remove_link(self, link: Link) -> None:
        """
        Remove the `link` from this meta node.
        """
        assert link in self.__links, "Link is not in the scheme."
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
        link._set_parent_node(None)
        link._set_workflow(None)
        QCoreApplication.sendEvent(
            link.sink_node,
            LinkEvent(LinkEvent.InputLinkRemoved, link, sink_index, self)
        )
        QCoreApplication.sendEvent(
            link.source_node,
            LinkEvent(LinkEvent.OutputLinkRemoved, link, source_index, self)
        )
        ev = LinkEvent(LinkEvent.LinkRemoved, link, index, self)
        QCoreApplication.sendEvent(self, ev)
        workflow = self.workflow()
        if workflow is not None:
            QCoreApplication.sendEvent(workflow, ev)
            workflow.link_removed.emit(link, self)
        self.link_removed.emit(link)

    def __check_connect(self, link: Link):
        w = self.workflow()
        if w is not None:
            return w.check_connect(link)
        else:
            return check_connect(self.__links, link)

    def add_annotation(self, annotation: Annotation):
        """Add the `annotation` to this meta node."""
        self.insert_annotation(len(self.__annotations), annotation)

    def insert_annotation(self, index: int, annotation: Annotation) -> None:
        """
        Insert `annotation` into `self.annotations()` at the specified
        position `index`.
        """
        if annotation.workflow() is not None:
            raise RuntimeError("'annotation' is already in a workflow")
        w = self.workflow()
        self.__annotations.insert(index, annotation)
        annotation._set_parent_node(self)
        annotation._set_workflow(w)
        ev = AnnotationEvent(AnnotationEvent.AnnotationAdded,
                             annotation, index, self)
        QCoreApplication.sendEvent(self, ev)
        if w is not None:
            QCoreApplication.sendEvent(w, ev)
            w.annotation_inserted.emit(index, annotation, self)
            w.annotation_added.emit(annotation, self)
        self.annotation_inserted.emit(index, annotation)

    def remove_annotation(self, annotation):
        """Remove the `annotation` from this meta node."""
        index = self.__annotations.index(annotation)
        self.__annotations.pop(index)
        annotation._set_workflow(None)
        annotation._set_parent_node(None)
        ev = AnnotationEvent(AnnotationEvent.AnnotationRemoved,
                             annotation, index, self)
        QCoreApplication.sendEvent(self, ev)
        w = self.workflow()
        if w is not None:
            QCoreApplication.sendEvent(w, ev)
            w.annotation_removed.emit(annotation, self)
        self.annotation_removed.emit(annotation)

    def clear(self):
        """
        Remove all subnodes, links and annotations from this node.
        """
        def is_terminal(node):
            # type: (Node) -> bool
            return not bool(self.find_links(source_node=node))

        while self.__nodes:
            terminal_nodes = list(filter(is_terminal, self.__nodes))
            for node in terminal_nodes:
                if isinstance(node, MetaNode):
                    node.clear()
                self.remove_node(node)

        for annotation in list(self.__annotations):
            self.remove_annotation(annotation)

        assert not (self.__nodes or self.__links or self.__annotations)

    def node_for_input_channel(self, channel: InputSignal) -> 'InputNode':
        """
        Return the :class:`InputNode` for the meta node's input `channel`.
        """
        node = findf(self.input_nodes(),
                     lambda n: n.input_channels()[0] == channel)
        if node is None:
            raise ValueError
        return node

    def node_for_output_channel(self, channel: OutputSignal) -> 'OutputNode':
        """
        Return the :class:`OutputNode` for the meta node's output `channel`.
        """
        node = findf(self.output_nodes(),
                     lambda n: n.output_channels()[0] == channel)
        if node is None:
            raise ValueError
        return node

    def _set_workflow(self, workflow: Optional['Workflow']) -> None:
        super()._set_workflow(workflow)
        for el in chain(self.__nodes, self.__links, self.__annotations):
            el._set_workflow(workflow)


class InputNode(Node):
    """
    An InputNode represents an input in a `MetaNode`.

    It acts as a bridge between the parent `MetaNode`\\'s input and
    its contents. I.e. inputs that are connected to the parent are
    redispatched to this node within the `MetaNode` for use by the other
    nodes.

    Parameters
    ----------
    input: InputSignal
        The parent meta nodes input signal.
    output: OutputSignal
        The corresponding output for this InputNode
    """
    def __init__(self, input: InputSignal, output: OutputSignal, **kwargs):
        super().__init__(**kwargs)
        self.sink_channel = input
        self.source_channel = output
        self.__input = input
        self.__output = output

    def input_channels(self):  # type: () -> List[InputSignal]
        return [self.__input]

    def output_channels(self):  # type: () -> List[OutputSignal]
        return [self.__output]


class OutputNode(Node):
    """
    An OutputNode represents an output in a `MetaNode`.

    It acts as a bridge between the parent `MetaNode`\\'s output and
    its contents. I.e. inputs that are connected to this node are
    redispatched to the parent `MetaNode`\\s outputs for use by the other
    nodes on the parent's node layer.

    Parameters
    ----------
    input: InputSignal
        The input output for this OutputNode
    output: OutputSignal
        The parent meta nodes output signal.
    """
    def __init__(self, input: InputSignal, output: OutputSignal, **kwargs):
        super().__init__(**kwargs)
        self.sink_channel = input
        self.source_channel = output
        self.__input = input
        self.__output = output

    def input_channels(self):  # type: () -> List[InputSignal]
        return [self.__input]

    def output_channels(self):  # type: () -> List[OutputSignal]
        return [self.__output]


T = TypeVar("T")


# helper utilities
def find_links(
        links: Iterable[Link],
        source_node: Optional[Node] = None,
        source_channel: Optional[OutputSignal] = None,
        sink_node: Optional[Node] = None,
        sink_channel: Optional[InputSignal] = None
) -> List[Link]:
    """
    Find links from `links` that match the specified
    {source,sink}_{node,channel} arguments (if `None` any will match) .
    """
    def match(query, value):
        # type: (Optional[T], T) -> bool
        return query is None or value == query
    return [
        link for link in links
        if match(source_node, link.source_node) and
           match(sink_node, link.sink_node) and
           match(source_channel, link.source_channel) and
           match(sink_channel, link.sink_channel)
    ]


def macro_link_step_in(link: Link) -> Node:
    sink = link.sink_node
    if isinstance(sink, MetaNode):
        inputs = sink.input_nodes()
        nodein = findf(inputs, lambda n: n.sink_channel == link.sink_channel)
        assert nodein is not None
        return nodein
    else:
        return sink


def macro_link_short_circuit_back(link: Link) -> Node:
    source = link.source_node
    if isinstance(source, MetaNode):
        outputs = source.output_nodes()
        nodeout = findf(outputs,
                        lambda n: n.source_channel == link.source_channel)
        assert nodeout is not None
        return nodeout
    else:
        return source


def node_dependents(node: Node) -> Sequence[Node]:
    parent = node.parent_node()
    links = []
    if parent is None:
        return []
    if isinstance(node, OutputNode):
        # step out of a macro
        macro = parent
        parent = macro.parent_node()
        if parent is not None:
            links = parent.find_links(macro, node.output_channels()[0])
    else:
        links = parent.find_links(node, None, None, None)
    return list(unique(map(macro_link_step_in, links)))


def node_dependencies(node) -> Sequence[Node]:
    parent = node.parent_node()
    links = []
    if parent is None:
        return []
    if isinstance(node, InputNode):
        # step out of a macro
        macro = parent
        parent = macro.parent_node()
        if parent is not None:
            links = parent.find_links(None, None, macro, node.input_channels()[0])
    else:
        links = parent.find_links(None, None, node, None)
    return list(unique(map(macro_link_short_circuit_back, links)))


def all_nodes_recursive(root: MetaNode) -> Iterable[Node]:
    for node in root.nodes():
        if isinstance(node, MetaNode):
            yield node
            yield from all_nodes_recursive(node)
        else:
            yield node


def all_links_recursive(root: MetaNode) -> Iterable[Link]:
    yield from root.links()
    for node in root.nodes():
        if isinstance(node, MetaNode):
            yield from all_links_recursive(node)


def all_annotations_recursive(root: MetaNode) -> Iterable[Annotation]:
    yield from root.annotations()
    for node in root.nodes():
        if isinstance(node, MetaNode):
            yield from all_annotations_recursive(node)


def check_connect(existing: Sequence[Link], link: Link, flags=0) -> None:
    """
    Check if the `link` can be added to the `existing` and raise an
    appropriate exception if not.

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
    from .scheme import Scheme
    if not flags & Scheme.AllowSelfLoops and link.source_node is link.sink_node:
        raise SchemeCycleError("Cannot create self cycle in the scheme")
    elif not flags & Scheme.AllowLoops and creates_cycle(existing, link):
        raise SchemeCycleError("Cannot create cycles in the scheme")

    if not compatible_channels(link.source_channel, link.sink_channel):
        raise IncompatibleChannelTypeError(
            "Cannot connect %r to %r."
            % (link.source_channel.type, link.sink_channel.type)
        )

    links = find_links(
        existing,
        source_node=link.source_node, source_channel=link.source_channel,
        sink_node=link.sink_node, sink_channel=link.sink_channel
    )
    if links:
        raise DuplicatedLinkError(
                "A link from %r (%r) -> %r (%r) already exists"
                % (link.source_node.title, link.source_channel.name,
                   link.sink_node.title, link.sink_channel.name)
            )

    if link.sink_channel.single:
        links = find_links(
            links, sink_node=link.sink_node, sink_channel=link.sink_channel
        )
        if links:
            raise SinkChannelError(
                    "%r is already connected." % link.sink_channel.name
                )


def creates_cycle(existing: Sequence[Link], link: Link) -> bool:
    """
    Return `True` if `link` would introduce a cycle in the `links`.
    """
    def expand(node: Node) -> Sequence[Node]:
        return [lnk.source_node for lnk in find_links(existing, sink_node=node)]
    source_node, sink_node = link.source_node, link.sink_node
    upstream = set(traverse_bf(source_node, expand))
    upstream.add(source_node)
    return sink_node in upstream

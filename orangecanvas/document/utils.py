import statistics
from copy import copy
from contextlib import contextmanager
from itertools import chain
from typing import Sequence, Tuple, Generator

from dataclasses import dataclass

from AnyQt.QtCore import QPointF, QRectF
from AnyQt.QtWidgets import QAction, QUndoStack

from orangecanvas.scheme import Node, Link, MetaNode, OutputNode, InputNode
from orangecanvas.utils import unique, enumerate_strings
from orangecanvas.utils.graph import traverse_bf

Pos = Tuple[float, float]


@dataclass
class PrepareMacroPatchResult:
    #: The created macro node
    macro_node: MetaNode
    #: The macro internal nodes
    nodes: Sequence[Node]
    #: The macro internal links
    links: Sequence[Link]
    #: The new input links to macro_node
    input_links: Sequence[Link]
    #: The new output links to the macro_node
    output_links: Sequence[Link]
    #: The links that should be removed/replaced by input/output_links.
    removed_links: Sequence[Link]


def prepare_macro_patch(
        parent: MetaNode, nodes: Sequence[Node]
) -> PrepareMacroPatchResult:
    assert all(n.parent_node() is parent for n in nodes)
    # exclude Input/OutputNodes
    nodes = [n for n in nodes if not isinstance(n, (InputNode, OutputNode))]

    # complete the nodes with any that lie in between nodes
    def ancestors(node: Node):
        return [link.source_node
                for link in parent.find_links(sink_node=node)]

    def descendants(node: Node):
        return [link.sink_node
                for link in parent.find_links(source_node=node)]

    all_ancestors = set(
        chain.from_iterable(traverse_bf(node, ancestors) for node in nodes)
    )
    all_descendants = set(
        chain.from_iterable(traverse_bf(node, descendants) for node in nodes)
    )
    expanded = all_ancestors & all_descendants
    nodes = list(unique(chain(nodes, expanded)))
    nodes_bbox = nodes_bounding_box(nodes)
    inputs_left = nodes_bbox.left() - 200
    outputs_right = nodes_bbox.right() + 200

    nodes_set = set(nodes)
    links_internal = [
        link for link in parent.links()
        if link.source_node in nodes_set and link.sink_node in nodes_set
    ]
    removed_links = list(links_internal)
    links_in = [
        link for link in parent.links()
        if link.source_node not in nodes_set and link.sink_node in nodes_set
    ]
    links_out = [
        link for link in parent.links()
        if link.source_node in nodes_set and link.sink_node not in nodes_set
    ]
    pos = (round(statistics.mean(n.position[0] for n in nodes)),
           round(statistics.mean(n.position[1] for n in nodes)))

    # group links_in, links_out by node, channel
    inputs_ = list(unique(
        map(lambda link: (link.sink_node, link.sink_channel), links_in)))
    outputs_ = list(unique(
        map(lambda link: (link.source_node, link.source_channel), links_out)))

    def copy_with_name(channel, name):
        c = copy(channel)
        c.name = name
        return c

    new_names = enumerate_strings(
        [c.name for _, c in inputs_], pattern="{item} ({_})"
    )
    new_inputs_ = [((node, channel), copy_with_name(channel, name=name))
                   for (node, channel), name in zip(inputs_, new_names)]
    inputs = [_2 for _1, _2 in new_inputs_]

    # new_outputs_ = [(node, channel) for ((node, channel), _) in outputs_]
    new_names = enumerate_strings(
        [c.name for _, c in outputs_], pattern="{item} ({_})"
    )
    new_outputs_ = [((node, channel), copy_with_name(channel, name=name))
                    for (node, channel), name in zip(outputs_, new_names)]
    outputs = [_2 for _1, _2 in new_outputs_]
    new_inputs = dict(new_inputs_); assert len(new_inputs) == len(new_inputs_)
    new_outputs = dict(new_outputs_); assert len(new_outputs) == len(new_outputs_)

    newnode = MetaNode('Macro', position=pos)

    input_nodes = [newnode.create_input_node(input) for input in inputs]
    for inode, (node, _) in zip(input_nodes, inputs_):
        inode.position = (inputs_left, node.position[1])
    output_nodes = [newnode.create_output_node(output) for output in outputs]
    for onode, (node, _)in zip(output_nodes, outputs_):
        onode.position = (outputs_right, node.position[1])

    # relink A -> (InputNode -> B ...)
    new_input_links = []
    for i, link in enumerate(links_in):
        new_input = new_inputs[link.sink_node, link.sink_channel]
        new_input_links += [
            Link(link.source_node, link.source_channel, newnode, new_input,
                 enabled=link.enabled)
        ]
    for inode, (node, channel) in zip(input_nodes, inputs_):
        links_internal += [
            Link(inode, inode.source_channel, node, channel),
        ]

    # relink (... C -> OutputNode) -> D
    new_output_links = []
    for i, link in enumerate(links_out):
        new_output = new_outputs[link.source_node, link.source_channel]
        new_output_links += [
            Link(newnode, new_output, link.sink_node, link.sink_channel,
                 enabled=link.enabled)
        ]
    for onode, (node, channel) in zip(output_nodes, outputs_):
        links_internal += [
            Link(node, channel, onode, onode.sink_channel),
        ]

    return PrepareMacroPatchResult(
        newnode, nodes,
        links_internal,
        new_input_links, new_output_links,
        removed_links + links_in + links_out
    )


@dataclass
class PrepareExpandMacroResult:
    nodes: Sequence[Node]
    links: Sequence[Link]


def prepare_expand_macro(
        parent: MetaNode, node: MetaNode) -> PrepareExpandMacroResult:
    nodes = node.nodes()
    links_in = parent.find_links(sink_node=node)
    links_out = parent.find_links(source_node=node)
    links_internal = [
        link for link in node.links() if not (
                isinstance(link.sink_node, OutputNode) or
                isinstance(link.source_node, InputNode)
        )
    ]
    links_in_new = []
    links_out_new = []
    # merge all X -> (Input_A -> Y ...) to X -> Y
    for ilink1 in links_in:
        inode = node.node_for_input_channel(ilink1.sink_channel)
        for ilink2 in node.find_links(
                source_node=inode, source_channel=inode.source_channel
        ):
            links_in_new.append(
                Link(ilink1.source_node, ilink1.source_channel,
                     ilink2.sink_node, ilink2.sink_channel,
                     enabled=ilink1.enabled)
            )

    # merge all (.. X -> Output_A) -> Y ...) to X -> Y
    for olink1 in links_out:
        onode = node.node_for_output_channel(olink1.source_channel)
        for olink2 in node.find_links(
                sink_node=onode, sink_channel=onode.sink_channel):
            links_out_new.append(
                Link(olink2.source_node, olink2.source_channel,
                     olink1.sink_node, olink1.sink_channel,
                     enabled=olink1.enabled)
            )
    nodes = [node for node in nodes
             if not isinstance(node, (InputNode, OutputNode))]
    return PrepareExpandMacroResult(
        nodes, links_in_new + links_internal + links_out_new
    )


@contextmanager
def disable_undo_stack_actions(
        undo: QAction, redo: QAction, stack: QUndoStack
) -> Generator[None, None, None]:
    """
    Disable the undo/redo actions of an undo stack.

    On exit restore the enabled state to match the `stack.canUndo()`
    and `stack.canRedo()`.

    Parameters
    ----------
    undo: QAction
    redo: QAction
    stack: QUndoStack

    Returns
    -------
    context: ContextManager
    """
    undo.setEnabled(False)
    redo.setEnabled(False)
    try:
        yield
    finally:
        undo.setEnabled(stack.canUndo())
        redo.setEnabled(stack.canRedo())


def nodes_bounding_box(nodes):
    # type: (Sequence[Node]) -> QRectF
    """Return bounding box containing all the node positions."""
    positions = [n.position for n in nodes]
    p1 = (min((x for x, _ in positions), default=0),
          min((y for _, y in positions), default=0))
    p2 = (max((x for x, _ in positions), default=0),
          max((y for _, y in positions), default=0))
    r = QRectF()
    r.setTopLeft(QPointF(*p1))
    r.setBottomRight(QPointF(*p2))
    return r

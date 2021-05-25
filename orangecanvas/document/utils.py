import statistics
from copy import copy
from itertools import chain
from typing import Sequence, Tuple

from dataclasses import dataclass

from orangecanvas.scheme import Node, Link, MetaNode, OutputNode, InputNode
from orangecanvas.utils import unique
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
    nodes_set = set(nodes)
    # TODO: MetaNode <-> InputNode/OutputNode link mapping
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

    # return nodes, links_internal, links_in, links_out, pos
    inputs = [copy(link.sink_channel) for link in links_in]
    outputs = [copy(link.source_channel) for link in links_out]

    newnode = MetaNode('Macro', position=pos)

    input_nodes = [newnode.create_input_node(input) for input in inputs]
    output_nodes = [newnode.create_output_node(output) for output in outputs]
    new_input_links = []
    for i, (link, node_in), in enumerate(zip(links_in, input_nodes)):
        # relink A -> (InputNode -> B ...)
        new_input_links += [
            Link(link.source_node, link.source_channel, newnode,
                 newnode.input_channels()[i], enabled=link.enabled)
        ]
        links_internal += [
            Link(node_in, node_in.output_channels()[0],
                 link.sink_node, link.sink_channel)
        ]

    new_output_links = []
    for i, (link, node_out) in enumerate(zip(links_out, output_nodes)):
        # relink (... C -> OutputNode) -> D
        links_internal += [
            Link(link.source_node, link.source_channel,
                 node_out, node_out.input_channels()[0], enabled=link.enabled),
        ]
        new_output_links += [
            Link(newnode, newnode.output_channels()[i], link.sink_node,
                 link.sink_channel)
        ]
    return PrepareMacroPatchResult(
        newnode, nodes,
        links_internal,
        new_input_links, new_output_links,
        removed_links + links_in + links_out
    )

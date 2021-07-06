"""
Scheme save/load routines.

"""
import numbers
import base64
import binascii
import math

from xml.etree.ElementTree import TreeBuilder, Element, ElementTree, parse
from itertools import chain

import pickle
import json
import pprint

import ast
from ast import literal_eval

import logging

from typing import (
    NamedTuple, Dict, Tuple, List, Union, Any, Optional, AnyStr, IO
)

from typing_extensions import TypeGuard

from .node import SchemeNode, Node
from .metanode import MetaNode, InputNode, OutputNode
from .link import Link
from .annotations import SchemeTextAnnotation, SchemeArrowAnnotation, Annotation
from .errors import IncompatibleChannelTypeError

from ..registry import global_registry, WidgetRegistry
from ..registry import WidgetDescription, InputSignal, OutputSignal
from ..utils import findf
from ..registry.description import Multiple, Single

log = logging.getLogger(__name__)

# protocol v4 is supported since Python 3.4, protocol v5 since Python 3.8
PICKLE_PROTOCOL = 4


class UnknownWidgetDefinition(Exception):
    pass


def _ast_parse_expr(source):
    # type: (str) -> ast.Expression
    node = ast.parse(source, "<source>", mode="eval")
    assert isinstance(node, ast.Expression)
    return node


def string_eval(source):
    # type: (str) -> str
    """
    Evaluate a python string literal `source`. Raise ValueError if
    `source` is not a string literal.

    >>> string_eval("'a string'")
    a string

    """
    node = _ast_parse_expr(source)
    body = node.body
    if not _is_constant(body, (str,)):
        raise ValueError("%r is not a string literal" % source)
    return body.value


def tuple_eval(source):
    # type: (str) -> tuple
    """
    Evaluate a python tuple literal `source` where the elements are
    constrained to be int, float or string. Raise ValueError if not
    a tuple literal.

    >>> tuple_eval("(1, 2, '3')")
    (1, 2, '3')

    """
    node = _ast_parse_expr(source)
    if not isinstance(node.body, ast.Tuple):
        raise ValueError("%r is not a tuple literal" % source)

    if not all(_is_constant(el, (str, float, complex, int)) or
               # allow signed number literals in Python3 (i.e. -1|+1|-1.0)
               (isinstance(el, ast.UnaryOp) and
                isinstance(el.op, (ast.UAdd, ast.USub)) and
                _is_constant(el.operand, (float, complex, int)))
               for el in node.body.elts):
        raise ValueError("Can only contain numbers or strings")

    return literal_eval(source)


def terminal_eval(source):
    # type: (str) -> Union[str, bytes, int, float, complex,  bool, None]
    """
    Evaluate a python 'constant' (string, number, None, True, False)
    `source`. Raise ValueError is not a terminal literal.

    >>> terminal_eval("True")
    True

    """
    node = _ast_parse_expr(source)
    return _terminal_value(node.body)


def _terminal_value(node):
    # type: (ast.AST) -> Union[str, bytes, int, float, complex, None]
    if _is_constant(node, (str, bytes, int, float, complex, type(None))):
        return node.value
    raise ValueError("Not a terminal")


def _is_constant(
        node: ast.AST, types: Tuple[type, ...]
) -> TypeGuard[ast.Constant]:
    return isinstance(node, ast.Constant) and isinstance(node.value, types)


# Intermediate scheme representation
class _scheme(NamedTuple):
    title: str
    version: str
    description: str
    nodes: List['_NodeType']
    links: List['_link']
    annotations: List['_annotation']
    session_state: '_session_data'

    @property
    def root(self):
        return _macro_node(
            id="", title=self.title, position=(0., 0.), version="",
            nodes=self.nodes, links=self.links, annotations=self.annotations,
        )

    def iter_all_nodes(self):
        def all_nodes(root):
            child_nodes = getattr(root, "nodes", [])
            yield from chain([root], *(all_nodes(c) for c in child_nodes))
        yield from chain.from_iterable(all_nodes(c) for c in self.nodes)


class _node(NamedTuple):
    id: str
    title: str
    position: Tuple[float, float]
    project_name: str
    qualified_name: str
    version: str
    added_inputs: Tuple[dict, ...]
    added_outputs: Tuple[dict, ...]
    data: Optional['_data']


class _macro_node(NamedTuple):
    id: str
    title: str
    position: Tuple[float, float]
    version: str
    nodes: List['_NodeType']
    links: List['_link']
    annotations: List['_annotation']


class _input_node(NamedTuple):
    id: str
    title: str
    position: Tuple[float, float]
    type: Tuple[str, ...]
    multiple: bool = False


class _output_node(NamedTuple):
    id: str
    title: str
    position: Tuple[float, float]
    type: Tuple[str, ...]


_NodeType = Union[_node, _macro_node, _input_node, _output_node]


class _data(NamedTuple):
    format: str
    data: Union[bytes, str]


class _link(NamedTuple):
    id: str
    source_node_id: str
    sink_node_id: str
    source_channel: str
    source_channel_id: str
    sink_channel: str
    sink_channel_id: str
    enabled: bool


class _annotation(NamedTuple):
    id: str
    type: str
    params: Union['_text_params', '_arrow_params']


class _text_params(NamedTuple):
    geometry: Tuple[float, float, float, float]
    text: str
    font: Dict[str, Any]
    content_type: str


class _arrow_params(NamedTuple):
    geometry: Tuple[Tuple[float, float], Tuple[float, float]]
    color: str


class _window_group(NamedTuple):
    name: str
    default: bool
    state: List[Tuple[str, bytes]]


class _session_data(NamedTuple):
    groups: List[_window_group]


def _parse_ows_etree_node(node: Element) -> _NodeType:
    node_id = node.get("id")
    px, py = tuple_eval(node.get("position"))
    added_inputs = []
    added_outputs = []

    for ai in node.findall("added_input"):
        added_inputs.append(dict(ai.attrib))
    for ao in node.findall("added_output"):
        added_outputs.append(dict(ao.attrib))

    return _node(  # type: ignore
            id=node_id,
            title=node.get("title"),
            # name=node.get("name"),
            position=(px, py),
            project_name=node.get("project_name"),
            qualified_name=node.get("qualified_name"),
            version=node.get("version", ""),
            added_inputs=tuple(added_inputs),
            added_outputs=tuple(added_outputs),
            data=None
        )


def _parse_ows_etree_macro_node(node: Element) -> _macro_node:
    node_id = node.get("id")
    px, py = tuple_eval(node.get("position", "0, 0"))
    nodes, links, annotations = [], [], []

    for enode in node.findall("./nodes/*"):
        parser = _parse_ows_etree_node_dispatch[enode.tag]
        nodes.append(parser(enode))
    for elink in node.findall("./links/link"):
        links.append(_parse_ows_etree_link(elink))
    for eannot in node.findall("./annotations/*"):
        parser = _parse_ows_etree_annotation_dispatch.get(eannot.tag, None)
        if parser is not None:
            annotations.append(parser(eannot))
        else:
            log.warning("Unknown annotation '%s'. Skipping.", eannot.tag)

    return _macro_node(
        id=node_id,
        title=node.get("title"),
        position=(px, py),
        nodes=nodes,
        links=links,
        annotations=annotations,
        version=node.get("version", ""),
    )


def parse_type_spec(string) -> Tuple[str, ...]:
    parts = [s.strip() for s in string.split("|")]
    return tuple(parts)


def _parse_ows_etree_input_node(node: Element) -> _input_node:
    node_id = node.get("id")
    px, py = tuple_eval(node.get("position"))
    types = parse_type_spec(node.get("type", ""))
    return _input_node(
            id=node_id,
            title=node.get("title"),
            position=(px, py),
            type=types,
            multiple=node.get("multiple", "false") == "true"
        )


def _parse_ows_etree_output_node(node: Element) -> _output_node:
    node_id = node.get("id")
    px, py = tuple_eval(node.get("position"))
    types = parse_type_spec(node.get("type", ""))
    return _output_node(
            id=node_id,
            title=node.get("title"),
            position=(px, py),
            type=types
        )


def _parse_ows_etree_link(link: Element):
    return _link(
        id=link.get("id"),
        source_node_id=link.get("source_node_id"),
        sink_node_id=link.get("sink_node_id"),
        source_channel=link.get("source_channel"),
        source_channel_id=link.get("source_channel_id", ""),
        sink_channel=link.get("sink_channel"),
        sink_channel_id=link.get("sink_channel_id", ""),
        enabled=link.get("enabled", "true") == "true",
    )


def _parse_ows_etree_text_annotation(annot: Element) -> _annotation:
    rect = tuple_eval(annot.get("rect", "0.0, 0.0, 20.0, 20.0"))
    font_family = annot.get("font-family", "").strip()
    font_size = annot.get("font-size", "").strip()
    font = {}  # type: Dict[str, Any]
    if font_family:
        font["family"] = font_family
    if font_size:
        font["size"] = int(font_size)

    content_type = annot.get("type", "text/plain")

    return _annotation(
        id=annot.get("id"),
        type="text",
        params=_text_params(  # type: ignore
            rect, annot.text or "", font, content_type),
    )


def _parse_ows_etree_arrow_annotation(annot: Element) -> _annotation:
    start = tuple_eval(annot.get("start", "0, 0"))
    end = tuple_eval(annot.get("end", "0, 0"))
    color = annot.get("fill", "red")
    return _annotation(
        id=annot.get("id"),
        type="arrow",
        params=_arrow_params((start, end), color)
    )


def _parse_ows_etree_window_group(group: Element) -> _window_group:
    name = group.get("name")  # type: str
    default = group.get("default", "false") == "true"
    state = []
    for state_ in group.findall("./window_state"):
        node_id = state_.get("node_id")
        text_ = state_.text
        if text_ is not None:
            try:
                data = base64.decodebytes(text_.encode("ascii"))
            except (binascii.Error, UnicodeDecodeError):
                data = b''
        else:
            data = b''
        state.append((node_id, data))
    return _window_group(name, default, state)


_parse_ows_etree_node_dispatch = {
    "node": _parse_ows_etree_node,
    "input_node": _parse_ows_etree_input_node,
    "output_node": _parse_ows_etree_output_node,
    "macro_node": _parse_ows_etree_macro_node,
}

_parse_ows_etree_annotation_dispatch = {
    "text": _parse_ows_etree_text_annotation,
    "arrow": _parse_ows_etree_arrow_annotation,
}


def parse_ows_etree_v_2_0(tree):
    # type: (ElementTree) -> _scheme
    """
    Parse an xml.etree.ElementTree struct into a intermediate workflow
    representation.
    """
    scheme = tree.getroot()
    version = scheme.get("version")
    nodes, links, annotations = [], [], []

    # First collect all properties
    properties = {}  # type: Dict[str, _data]
    for property in tree.findall("node_properties/properties"):
        node_id = property.get("node_id")  # type: str
        format = property.get("format")
        if version == "2.0" and "data" in property.attrib:
            data_str = property.get("data", default="")
        else:
            data_str = property.text or ""
        properties[node_id] = _data(format, data_str)

    # Collect all nodes
    for node in tree.findall("nodes/node"):
        node_id = node.get("id")
        _px, _py = tuple_eval(node.get("position"))
        added_inputs = []
        added_outputs = []

        for ai in node.findall("added_input"):
            added_inputs.append(dict(ai.attrib))
        for ao in node.findall("added_output"):
            added_outputs.append(dict(ao.attrib))

        nodes.append(
            _node(  # type: ignore
                id=node_id,
                title=node.get("title"),
                # name=node.get("name"),
                position=(_px, _py),
                project_name=node.get("project_name"),
                qualified_name=node.get("qualified_name"),
                version=node.get("version", ""),
                added_inputs=tuple(added_inputs),
                added_outputs=tuple(added_outputs),
                data=properties.get(node_id, None)
            )
        )

    for link in tree.findall("links/link"):
        params = _link(
            id=link.get("id"),
            source_node_id=link.get("source_node_id"),
            sink_node_id=link.get("sink_node_id"),
            source_channel=link.get("source_channel"),
            source_channel_id=link.get("source_channel_id", ""),
            sink_channel=link.get("sink_channel"),
            sink_channel_id=link.get("sink_channel_id", ""),
            enabled=link.get("enabled") == "true",
        )
        links.append(params)

    for annot in tree.findall("annotations/*"):
        if annot.tag == "text":
            rect = tuple_eval(annot.get("rect", "0.0, 0.0, 20.0, 20.0"))

            font_family = annot.get("font-family", "").strip()
            font_size = annot.get("font-size", "").strip()

            font = {}  # type: Dict[str, Any]
            if font_family:
                font["family"] = font_family
            if font_size:
                font["size"] = int(font_size)

            content_type = annot.get("type", "text/plain")

            annotation = _annotation(
                id=annot.get("id"),
                type="text",
                params=_text_params(  # type: ignore
                    rect, annot.text or "", font,  content_type),
            )
        elif annot.tag == "arrow":
            start = tuple_eval(annot.get("start", "0, 0"))
            end = tuple_eval(annot.get("end", "0, 0"))
            color = annot.get("fill", "red")
            annotation = _annotation(
                id=annot.get("id"),
                type="arrow",
                params=_arrow_params((start, end), color)  # type: ignore
            )
        else:
            log.warning("Unknown annotation '%s'. Skipping.", annot.tag)
            continue
        annotations.append(annotation)

    window_presets = []

    for window_group in tree.findall("session_state/window_groups/group"):
        name = window_group.get("name")  # type: str
        default = window_group.get("default", "false") == "true"
        state = []
        for state_ in window_group.findall("window_state"):
            node_id = state_.get("node_id")
            text_ = state_.text
            if text_ is not None:
                try:
                    data = base64.decodebytes(text_.encode("ascii"))
                except (binascii.Error, UnicodeDecodeError):
                    data = b''
            else:
                data = b''
            state.append((node_id, data))

        window_presets.append(_window_group(name, default, state))

    session_state = _session_data(window_presets)

    return _scheme(
        version=version,
        title=scheme.get("title", ""),
        description=scheme.get("description"),
        nodes=nodes,
        links=links,
        annotations=annotations,
        session_state=session_state,
    )


def parse_ows_etree_v_3_0(tree):
    # type: (ElementTree) -> _scheme
    """
    Parse an xml.etree.ElementTree struct into a intermediate workflow
    representation.
    """
    scheme = tree.getroot()
    version = scheme.get("version")

    # First collect all properties
    properties = {}  # type: Dict[str, _data]
    for property in tree.findall("node_properties/properties"):
        node_id = property.get("node_id")  # type: str
        format = property.get("format")
        if version == "2.0" and "data" in property.attrib:
            data_str = property.get("data", default="")
        else:
            data_str = property.text or ""
        properties[node_id] = _data(format, data_str)

    root = _parse_ows_etree_macro_node(scheme)

    def add_node_data(node: _NodeType) -> _NodeType:
        if isinstance(node, _macro_node):
            return node._replace(nodes=[add_node_data(n) for n in node.nodes])
        elif isinstance(node, _node):
            return node._replace(data=properties.get(node.id, None))
        else:
            return node
    window_presets = []

    for window_group in tree.findall("session_state/window_groups/group"):
        window_presets.append(_parse_ows_etree_window_group(window_group))
    session_state = _session_data(window_presets)
    root = root._replace(nodes=[add_node_data(n) for n in root.nodes])

    return _scheme(
        version=version,
        title=scheme.get("title", ""),
        description=scheme.get("description"),
        nodes=root.nodes,
        links=root.links,
        annotations=root.annotations,
        session_state=session_state,
    )


class InvalidFormatError(ValueError):
    pass


class UnsupportedFormatVersionError(ValueError):
    pass


def parse_ows_stream(stream):
    # type: (Union[AnyStr, IO]) -> _scheme
    doc = parse(stream)
    scheme_el = doc.getroot()
    if scheme_el.tag != "scheme":
        raise InvalidFormatError(
            "Invalid Orange Workflow Scheme file"
        )
    version = scheme_el.get("version", None)
    if version is None:
        # Check for "widgets" tag - old Orange<2.7 format
        if scheme_el.find("widgets") is not None:
            raise UnsupportedFormatVersionError(
                "Cannot open Orange Workflow Scheme v1.0. This format is no "
                "longer supported"
            )
        else:
            raise InvalidFormatError(
                "Invalid Orange Workflow Scheme file (missing version)."
            )
    version_info = tuple(map(int, version.split(".")))
    if (2, 0) <= version_info < (3, 0):
        return parse_ows_etree_v_2_0(doc)
    elif (3, 0) <= version_info < (4, 0):
        return parse_ows_etree_v_3_0(doc)
    else:
        raise UnsupportedFormatVersionError(
            f"Unsupported format version {version}")


def resolve_replaced(scheme_desc: _scheme, registry: WidgetRegistry) -> _scheme:
    widgets = registry.widgets()
    nodes_by_id = {}  # type: Dict[str, _node]
    replacements = {}
    replacements_channels = {}  # type: Dict[str, Tuple[dict, dict]]
    # collect all the replacement mappings
    for desc in widgets:  # type: WidgetDescription
        if desc.replaces:
            for repl_qname in desc.replaces:
                replacements[repl_qname] = desc.qualified_name

        input_repl = {}
        for idesc in desc.inputs or []:  # type: InputSignal
            for repl_qname in idesc.replaces or []:  # type: str
                input_repl[repl_qname] = idesc.name
        output_repl = {}
        for odesc in desc.outputs:  # type: OutputSignal
            for repl_qname in odesc.replaces or []:  # type: str
                output_repl[repl_qname] = odesc.name
        replacements_channels[desc.qualified_name] = (input_repl, output_repl)

    # replace the nodes
    def replace_macro(root: _macro_node):
        nodes = root.nodes
        for i, node in list(enumerate(nodes)):
            if isinstance(node, _node) and \
                    not registry.has_widget(node.qualified_name) and \
                    node.qualified_name in replacements:
                qname = replacements[node.qualified_name]
                desc = registry.widget(qname)
                nodes[i] = node._replace(qualified_name=desc.qualified_name,
                                         project_name=desc.project_name)
            if isinstance(node, _macro_node):
                nodes[i] = replace_macro(node)
            nodes_by_id[node.id] = nodes[i]

        # replace links
        links = root.links
        for i, link in list(enumerate(links)):
            nsource = nodes_by_id[link.source_node_id]
            nsink = nodes_by_id[link.sink_node_id]
            source_rep = sink_rep = {}
            if isinstance(nsource, _node):
                _, source_rep = replacements_channels.get(
                    nsource.qualified_name, ({}, {}))
            if isinstance(nsink, _node):
                sink_rep, _ = replacements_channels.get(
                    nsink.qualified_name, ({}, {}))

            if link.source_channel in source_rep:
                link = link._replace(
                    source_channel=source_rep[link.source_channel])
            if link.sink_channel in sink_rep:
                link = link._replace(
                    sink_channel=sink_rep[link.sink_channel])
            links[i] = link
        return root._replace(nodes=nodes, links=links)
    root = _macro_node(
        "", "", (0, 0), "", scheme_desc.nodes, scheme_desc.links,
        scheme_desc.annotations
    )
    root = replace_macro(root)
    return scheme_desc._replace(nodes=root.nodes, links=root.links)


def scheme_load(scheme, stream, registry=None, error_handler=None):
    desc = parse_ows_stream(stream)  # type: _scheme
    if registry is None:
        registry = global_registry()

    if error_handler is None:
        def error_handler(exc):
            raise exc

    desc = resolve_replaced(desc, registry)
    nodes_not_found = []
    nodes_by_id = {}
    links = []

    scheme.title = desc.title
    scheme.description = desc.description
    root = scheme.root()

    def build_scheme_node(node: _node, parent: MetaNode) -> SchemeNode:
        try:
            desc = registry.widget(node.qualified_name)
        except KeyError as ex:
            error_handler(UnknownWidgetDefinition(*ex.args))
            nodes_not_found.append(node.id)
        else:
            snode = SchemeNode(
                desc, title=node.title, position=node.position)
            for ai in node.added_inputs:
                snode.add_input_channel(
                    InputSignal(ai["name"], ai["type"], "")
                )
            for ao in node.added_outputs:
                snode.add_output_channel(
                    OutputSignal(ao["name"], ao["type"])
                )
            if node.data:
                try:
                    properties = loads(node.data.data, node.data.format)
                except Exception:
                    log.error("Could not load properties for %r.", node.title,
                              exc_info=True)
                else:
                    snode.properties = properties
            parent.add_node(snode)
            nodes_by_id[node.id] = snode
            return snode

    def build_macro_node(node: _macro_node, parent: MetaNode) -> MetaNode:
        meta = WidgetDescription(
            "Macro", id="orangecanvas.meta", category="Utils/Meta",
            qualified_name="orangecanvas.scheme.node.MetaNode",
            inputs=[], outputs=[]
        )
        mnode = MetaNode(node.title, position=node.position)
        mnode.description = meta
        parent.add_node(mnode)
        nodes_by_id[node.id] = mnode
        build_macro_helper(mnode, node)
        mnode.description.inputs = tuple(mnode.input_channels())
        mnode.description.outputs = tuple(mnode.output_channels())
        return mnode

    def build_macro_helper(mnode: MetaNode, node: _macro_node):
        for node_d in node.nodes:
            node_dispatch[type(node_d)](node_d, mnode)

        for link_d in node.links:
            source_id = link_d.source_node_id
            sink_id = link_d.sink_node_id
            if source_id in nodes_not_found or sink_id in nodes_not_found:
                continue
            source = nodes_by_id[source_id]
            sink = nodes_by_id[sink_id]
            try:
                link = Link(
                    source, _find_source_channel(source, link_d),
                    sink, _find_sink_channel(sink, link_d),
                    enabled=link_d.enabled
                )
            except (ValueError, IncompatibleChannelTypeError) as ex:
                error_handler(ex)
            else:
                mnode.add_link(link)

        for annot_d in node.annotations:
            params = annot_d.params
            if annot_d.type == "text":
                annot = SchemeTextAnnotation(
                    params.geometry, params.text, params.content_type,
                    params.font
                )
            elif annot_d.type == "arrow":
                start, end = params.geometry
                annot = SchemeArrowAnnotation(start, end, params.color)
            else:
                log.warning("Ignoring unknown annotation type: %r",
                            annot_d.type)
                continue
            mnode.add_annotation(annot)
        return mnode

    def build_input_node(node: _input_node, parent: MetaNode) -> InputNode:
        flags = Multiple if node.multiple else Single
        inode = InputNode(
            InputSignal(node.title, node.type, "", flags=flags),
            OutputSignal(node.title, node.type, flags=flags),
            title=node.title, position=node.position
        )
        parent.add_node(inode)
        nodes_by_id[node.id] = inode
        return inode

    def build_output_node(node: _output_node, parent: MetaNode) -> OutputNode:
        onode = OutputNode(
            InputSignal(node.title, node.type, ""),
            OutputSignal(node.title, node.type),
            title=node.title, position=node.position
        )
        parent.add_node(onode)
        nodes_by_id[node.id] = onode
        return onode

    node_dispatch = {
        _node: build_scheme_node, _macro_node: build_macro_node,
        _input_node: build_input_node, _output_node: build_output_node
    }
    _root_node = _macro_node(
        "", "", (0., 0.), "", desc.nodes, desc.links, desc.annotations
    )
    build_macro_helper(root, _root_node)

    if desc.session_state.groups:
        groups = []
        for g in desc.session_state.groups:  # type: _window_group
            # resolve node_id -> node
            state = [(nodes_by_id[node_id], data)
                     for node_id, data in g.state if node_id in nodes_by_id]

            groups.append(Scheme.WindowGroup(g.name, g.default, state))
        scheme.set_window_group_presets(groups)
    return scheme


def _find_source_channel(node: SchemeNode, link: _link) -> OutputSignal:
    source_channel: Optional[OutputSignal] = None
    if link.source_channel_id:
        source_channel = findf(
            node.output_channels(),
            lambda c: c.id == link.source_channel_id,
        )
    if source_channel is not None:
        return source_channel
    source_channel = findf(
        node.output_channels(),
        lambda c: c.name == link.source_channel,
    )
    if source_channel is not None:
        return source_channel
    raise ValueError(
        f"{link.source_channel!r} is not a valid output channel "
        f"for {node.description.name!r}."
    )


def _find_sink_channel(node: SchemeNode, link: _link) -> InputSignal:
    sink_channel: Optional[InputSignal] = None
    if link.sink_channel_id:
        sink_channel = findf(
            node.input_channels(),
            lambda c: c.id == link.sink_channel_id,
        )
    if sink_channel is not None:
        return sink_channel
    sink_channel = findf(
        node.input_channels(),
        lambda c: c.name == link.sink_channel,
    )
    if sink_channel is not None:
        return sink_channel
    raise ValueError(
        f"{link.sink_channel!r} is not a valid input channel "
        f"for {node.description.name!r}."
    )

def _meta_node_to_interm(node: MetaNode, ids) -> _macro_node:
    nodes = []
    node_dispatch = {
        SchemeNode: _node_to_interm,
        MetaNode: _meta_node_to_interm,
        OutputNode: _output_node_to_interm,
        InputNode: _input_node_to_interm,
    }
    for n in node.nodes():
        nodes.append(node_dispatch[type(n)](n, ids))
    links = [_link_to_interm(link, ids) for link in node.links()]
    annotations = [_annotation_to_interm(annot, ids) for annot in node.annotations()]

    return _macro_node(
        id=ids[node],
        title=node.title,
        position=node.position,
        version="",
        nodes=nodes,
        links=links,
        annotations=annotations,
    )


def _node_to_interm(node: SchemeNode, ids) -> _node:
    desc = node.description
    input_defs = output_defs = []
    if node.input_channels() != desc.inputs:
        input_defs = node.input_channels()[len(desc.inputs):]
    if node.output_channels() != desc.outputs:
        output_defs = node.output_channels()[len(desc.outputs):]

    ttype = lambda s: ",".join(map(str, s))
    added_inputs = tuple({"name": idef.name, "type": ttype(idef.type)}
                         for idef in input_defs)
    added_outputs = tuple({"name": odef.name, "type": ttype(odef.type)}
                          for odef in output_defs)

    return _node(
        id=ids[node],
        title=node.title,
        position=node.position,
        qualified_name=desc.qualified_name,
        project_name=desc.project_name or "",
        version=desc.version,
        added_inputs=added_inputs,
        added_outputs=added_outputs,
        data=None,
    )


def _input_node_to_interm(node: InputNode, ids) -> _input_node:
    return _input_node(
        id=ids[node],
        title=node.title,
        position=node.position,
        type=node.input_channels()[0].types,
        multiple=not node.input_channels()[0].single
    )


def _output_node_to_interm(node: OutputNode, ids) -> _output_node:
    return _output_node(
        id=ids[node],
        title=node.title,
        position=node.position,
        type=node.output_channels()[0].types,
    )


def _link_to_interm(link: Link, ids):
    return _link(
        id=ids[link],
        enabled=link.enabled,
        source_node_id=ids[link.source_node],
        source_channel=link.source_channel.name,
        source_channel_id=link.source_channel.id,
        sink_node_id=ids[link.sink_node],
        sink_channel=link.sink_channel.name,
        sink_channel_id=link.sink_channel.id,
    )


def _annotation_to_interm(annot: Annotation, ids) -> _annotation:
    if isinstance(annot, SchemeTextAnnotation):
        params = _text_params(
            geometry=annot.geometry,
            text=annot.text,
            content_type=annot.content_type,
            font={},  # deprecated.
        )
        type_ = "text"
    elif isinstance(annot, SchemeArrowAnnotation):
        params = _arrow_params(
            geometry=annot.geometry,
            color=annot.color
        )
        type_ = "arrow"
    else:
        raise TypeError()

    return _annotation(
        id=ids[annot],
        type=type_,
        params=params,
    )


def scheme_to_interm(scheme, data_format="literal", pickle_fallback=False):
    # type: (Scheme, str, bool) -> _scheme
    """
    Return a workflow scheme in its intermediate representation for
    serialization.
    """
    node_ids: Dict[Node, str] = {
        node: str(i + 1) for i, node in enumerate(scheme.all_nodes())
    }
    link_ids: Dict[Link, str] = {
        link: str(i + 1) for i, link in enumerate(scheme.all_links())
    }
    annot_ids: Dict[Link, str] = {
        annot: str(i + 1) for i, annot in enumerate(scheme.all_annotations())
    }
    window_presets = []
    ids = {**node_ids, **link_ids, **annot_ids}
    # Nodes
    root = scheme.root()
    ids[root] = ""
    iroot = _meta_node_to_interm(root, ids)
    node_properties = {}
    for node in root.all_nodes():
        if node.properties:
            try:
                data, format_ = dumps(node.properties, format=data_format,
                                      pickle_fallback=pickle_fallback)
                data = _data(format_, data)
            except Exception:
                log.error("Error serializing properties for node %r",
                          node.title, exc_info=True)
                raise
        else:
            data = None
        node_properties[node_ids[node]] = data

    def fix_props(node: Union[_node, _macro_node, _input_node, _output_node]):
        if isinstance(node, _macro_node):
            return node._replace(nodes=[fix_props(n) for n in node.nodes])
        elif isinstance(node, _node):
            return node._replace(data=node_properties.get(node.id))
        else:
            return node
    iroot = fix_props(iroot)
    for preset in scheme.window_group_presets():
        state = [(node_ids[n], state) for n, state in preset.state]
        window_presets.append(
            _window_group(preset.name, preset.default, state)
        )

    return _scheme(
        scheme.title, "2.0", scheme.description, iroot.nodes, iroot.links,
        iroot.annotations, session_state=_session_data(window_presets),
    )


def scheme_to_etree_2_0(scheme, data_format="literal", pickle_fallback=False):
    """
    Return an `xml.etree.ElementTree` representation of the `scheme`.
    """
    scheme = scheme_to_interm(scheme, data_format=data_format,
                              pickle_fallback=pickle_fallback)
    builder = TreeBuilder(element_factory=Element)
    builder.start(
        "scheme", {
            "version": "2.0",
            "title": scheme.title,
            "description": scheme.description,
        }
    )

    # Nodes
    builder.start("nodes", {})
    for node in scheme.nodes:  # type: _node
        builder.start(
            "node", {
                "id": node.id,
                # "name": node.name,
                "qualified_name": node.qualified_name,
                "project_name": node.project_name,
                "version": node.version,
                "title": node.title,
                "position": node.position,
            }
        )
        for input_def in node.added_inputs:
            builder.start("added_input", {
                "name": input_def["name"],
                "type": input_def["type"],
            })
            builder.end("added_input")
        for output_def in node.added_outputs:
            builder.start("added_output", {
                "name": output_def["name"],
                "type": output_def["type"],
            })
            builder.end("added_output")
        builder.end("node")
    builder.end("nodes")

    # Links
    builder.start("links", {})
    for link in scheme.links:
        extra = {}
        if link.source_channel_id:
            extra["source_channel_id"] = link.source_channel_id
        if link.sink_channel_id:
            extra["sink_channel_id"] = link.sink_channel_id
        builder.start(
            "link", {
                "id": link.id,
                "source_node_id": link.source_node_id,
                "sink_node_id": link.sink_node_id,
                "source_channel": link.source_channel,
                "sink_channel": link.sink_channel,
                "enabled": "true" if link.enabled else "false",
                **extra
            }
        )
        builder.end("link")
    builder.end("links")

    # Annotations
    builder.start("annotations", {})
    for annotation in scheme.annotations:
        attrs = {"id": annotation.id}
        if annotation.type == "text":
            params = annotation.params  # type: _text_params
            assert isinstance(params, _text_params)
            attrs.update({
                "type": params.content_type,
                "rect": "{!r}, {!r}, {!r}, {!r}".format(*params.geometry)
            })
            # Save the font attributes
            attrs.update({key: str(value) for key, value in params.font.items()
                          if value is not None})
            data = params.text
        elif annotation.type == "arrow":
            params = annotation.params  # type: _arrow_params
            start, end = params.geometry
            attrs.update({
                "start": "{!r}, {!r}".format(*start),
                "end": "{!r}, {!r}".format(*end),
                "fill": params.color
            })
            data = None
        else:
            log.warning("Can't save %r", annotation)
            continue
        builder.start(annotation.type, attrs)
        if data is not None:
            builder.data(data)
        builder.end(annotation.type)

    builder.end("annotations")

    # Node properties/settings
    builder.start("node_properties", {})
    for node in scheme.nodes:
        if node.data is not None:
            data = node.data
            builder.start(
                "properties", {
                    "node_id": node.id,
                    "format": data.format
                }
            )
            builder.data(data.data)
            builder.end("properties")

    builder.end("node_properties")
    builder.start("session_state", {})
    builder.start("window_groups", {})

    for g in scheme.session_state.groups:  # type: _window_group
        builder.start(
            "group", {"name": g.name, "default": str(g.default).lower()}
        )
        for node_id, data in g.state:
            builder.start("window_state", {"node_id": node_id})
            builder.data(base64.encodebytes(data).decode("ascii"))
            builder.end("window_state")
        builder.end("group")
    builder.end("window_group")
    builder.end("session_state")
    builder.end("scheme")
    root = builder.close()
    tree = ElementTree(root)
    return tree


# back-compatibility alias
scheme_to_etree = scheme_to_etree_2_0


def scheme_to_etree_3_0(scheme, data_format="literal", pickle_fallback=False):
    scheme = scheme_to_interm(scheme, data_format=data_format,
                              pickle_fallback=pickle_fallback)
    builder = TreeBuilder(element_factory=Element)
    all_nodes = []
    builder.start(
        "scheme", {
            "version": "3.0",
            "title": scheme.title,
            "description": scheme.description,
        }
    )

    iroot = _macro_node("", "", (0, 0), "", scheme.nodes, scheme.links, scheme.annotations)
    # Nodes

    def build_node(node: _node):
        all_nodes.append(node)
        builder.start(
            "node", {
                "id": node.id,
                # "name": node.name,
                "qualified_name": node.qualified_name,
                "project_name": node.project_name,
                "version": node.version or "",
                "title": node.title,
                "position": node.position,
            }
        )
        for input_def in node.added_inputs:
            builder.start("added_input", {
                "name": input_def["name"],
                "type": input_def["type"],
            })
            builder.end("added_input")
        for output_def in node.added_outputs:
            builder.start("added_output", {
                "name": output_def["name"],
                "type": output_def["type"],
            })
            builder.end("added_output")
        builder.end("node")

    def build_input_node(node: _input_node):
        builder.start(
            "input_node", {
                "id": node.id,
                "title": node.title,
                "position": f"{node.position[0]}, {node.position[1]}",
                "type": ",".join(node.type),
                "multiple": str(node.multiple).lower()
            }
        )
        builder.end("input_node")

    def build_output_node(node: _output_node):
        builder.start(
            "output_node", {
                "id": node.id,
                "title": node.title,
                "position": f"{node.position[0]}, {node.position[1]}",
                "type": ",".join(node.type)
            }
        )
        builder.end("output_node")

    def build_macro_node(node: _macro_node):
        builder.start(
            "macro_node", {
                "id": node.id,
                "title": node.title,
                "position": f'{node.position[0]}, {node.position[1]}',
                "version": "",
            }
        )
        build_macro_node_helper(node)
        builder.end("macro_node")

    def build_macro_node_helper(node: _macro_node):
        builder.start("nodes", {})
        for n in node.nodes:
            dispatch_node[type(n)](n)
        builder.end("nodes")

        # Links
        builder.start("links", {})
        for link in node.links:
            builder.start(
                "link", {
                    "id": link.id,
                    "source_node_id": link.source_node_id,
                    "sink_node_id": link.sink_node_id,
                    "source_channel": link.source_channel,
                    "source_channel_id": link.source_channel_id or "",
                    "sink_channel": link.sink_channel,
                    "sink_channel_id": link.sink_channel_id or "",
                    "enabled": "true" if link.enabled else "false",
                }
            )
            builder.end("link")
        builder.end("links")

        # Annotations
        builder.start("annotations", {})
        for annotation in node.annotations:
            attrs = {"id": annotation.id}
            if annotation.type == "text":
                tag = "text"
                params = annotation.params  # type: _text_params
                assert isinstance(params, _text_params)
                attrs.update({
                    "type": params.content_type,
                    "rect": "{!r}, {!r}, {!r}, {!r}".format(*params.geometry)
                })
                data = params.text
            elif annotation.type == "arrow":
                tag = "arrow"
                params = annotation.params  # type: _arrow_params
                start, end = params.geometry
                attrs.update({
                    "start": "{!r}, {!r}".format(*start),
                    "end": "{!r}, {!r}".format(*end),
                    "fill": params.color
                })
                data = None
            else:
                log.warning("Can't save %r", annotation)
                continue
            builder.start(annotation.type, attrs)
            if data is not None:
                builder.data(data)
            builder.end(tag)

        builder.end("annotations")

    dispatch_node = {
        _macro_node: build_macro_node,
        _node: build_node,
        _input_node: build_input_node,
        _output_node: build_output_node,
    }
    build_macro_node_helper(iroot)
    # Node properties/settings
    builder.start("node_properties", {})
    for node in all_nodes:
        if node.data is not None:
            data = node.data
            builder.start(
                "properties", {
                    "node_id": node.id,
                    "format": data.format
                }
            )
            builder.data(data.data)
            builder.end("properties")

    builder.end("node_properties")
    builder.start("session_state", {})
    builder.start("window_groups", {})

    for g in scheme.session_state.groups:  # type: _window_group
        builder.start(
            "group", {"name": g.name, "default": str(g.default).lower()}
        )
        for node_id, data in g.state:
            builder.start("window_state", {"node_id": node_id})
            builder.data(base64.encodebytes(data).decode("ascii"))
            builder.end("window_state")
        builder.end("group")
    builder.end("window_group")
    builder.end("session_state")
    builder.end("scheme")
    root = builder.close()
    tree = ElementTree(root)
    return tree


def scheme_to_ows_stream(scheme, stream, pretty=False, pickle_fallback=False):
    """
    Write scheme to a a stream in Orange Scheme .ows (v 2.0) format.

    Parameters
    ----------
    scheme : :class:`.Scheme`
        A :class:`.Scheme` instance to serialize.
    stream : file-like object
        A file-like object opened for writing.
    pretty : bool, optional
        If `True` the output xml will be pretty printed (indented).
    pickle_fallback : bool, optional
        If `True` allow scheme node properties to be saves using pickle
        protocol if properties cannot be saved using the default
        notation.

    """
    tree = scheme_to_etree_3_0(scheme, data_format="literal",
                               pickle_fallback=pickle_fallback)
    if pretty:
        indent(tree.getroot(), 0)
    tree.write(stream, encoding="utf-8", xml_declaration=True)


def indent(element, level=0, indent="\t"):
    """
    Indent an instance of a :class:`Element`. Based on
    (http://effbot.org/zone/element-lib.htm#prettyprint).

    """
    def empty(text):
        return not text or not text.strip()

    def indent_(element, level, last):
        child_count = len(element)

        if child_count:
            if empty(element.text):
                element.text = "\n" + indent * (level + 1)

            if empty(element.tail):
                element.tail = "\n" + indent * (level + (-1 if last else 0))

            for i, child in enumerate(element):
                indent_(child, level + 1, i == child_count - 1)

        else:
            if empty(element.tail):
                element.tail = "\n" + indent * (level + (-1 if last else 0))

    return indent_(element, level, True)


def dumps(obj, format="literal", prettyprint=False, pickle_fallback=False):
    """
    Serialize `obj` using `format` ('json' or 'literal') and return its
    string representation and the used serialization format ('literal',
    'json' or 'pickle').

    If `pickle_fallback` is True and the serialization with `format`
    fails object's pickle representation will be returned

    """
    if format == "literal":
        try:
            return (literal_dumps(obj, indent=1 if prettyprint else None),
                    "literal")
        except (ValueError, TypeError) as ex:
            if not pickle_fallback:
                raise

            log.warning("Could not serialize to a literal string",
                        exc_info=True)

    elif format == "json":
        try:
            return (json.dumps(obj, indent=1 if prettyprint else None),
                    "json")
        except (ValueError, TypeError):
            if not pickle_fallback:
                raise

            log.warning("Could not serialize to a json string",
                        exc_info=True)

    elif format == "pickle":
        return base64.encodebytes(pickle.dumps(obj, protocol=PICKLE_PROTOCOL)). \
                   decode('ascii'), "pickle"

    else:
        raise ValueError("Unsupported format %r" % format)

    if pickle_fallback:
        log.warning("Using pickle fallback")
        return base64.encodebytes(pickle.dumps(obj, protocol=PICKLE_PROTOCOL)). \
                   decode('ascii'), "pickle"
    else:
        raise Exception("Something strange happened.")


def loads(string, format):
    if format == "literal":
        return literal_eval(string)
    elif format == "json":
        return json.loads(string)
    elif format == "pickle":
        return pickle.loads(base64.decodebytes(string.encode('ascii')))
    else:
        raise ValueError("Unknown format")


# This is a subset of PyON serialization.
def literal_dumps(obj, indent=None, relaxed_types=True):
    """
    Write obj into a string as a python literal.

    Note
    ----
    :class:`set` objects are not supported as the empty set is not
    representable as a literal.

    Parameters
    ----------
    obj : Any
    indent : Optional[int]
        If not None then it is the indent for the pretty printer.
    relaxed_types : bool
        Relaxed type checking. In addition to exact builtin numeric types,
        the numbers.Integer, numbers.Real are checked and allowed if their
        repr matches that of the builtin.

        .. warning:: The exact type of the values will be lost.

    Returns
    -------
    repr : str
        String representation of `obj`

    See Also
    --------
    ast.literal_eval

    Raises
    ------
    TypeError
        If obj contains non builtin types that cannot be represented as a
        literal value.

    ValueError
        If obj is a recursive structure.
    """
    memo = {}
    # non compounds
    builtins = {int, float, bool, type(None), str, bytes}
    # sequences
    builtins_seq = {list, tuple}
    # mappings
    builtins_mapping = {dict}

    def check(obj):
        if type(obj) == float and not math.isfinite(obj):
            raise TypeError("Non-finite values can not be "
                            "serialized as a python literal")

        if type(obj) in builtins:
            return True

        if id(obj) in memo:
            raise ValueError("{0} is a recursive structure".format(obj))

        memo[id(obj)] = obj

        if type(obj) in builtins_seq:
            return all(map(check, obj))
        elif type(obj) in builtins_mapping:
            return all(map(check, chain(obj.keys(), obj.values())))
        else:
            raise TypeError("{0} can not be serialized as a python "
                            "literal".format(type(obj)))

    def check_relaxed(obj):
        if isinstance(obj, numbers.Real) and not math.isfinite(obj):
            raise TypeError("Non-finite values can not be "
                            "serialized as a python literal")

        if type(obj) in builtins:
            return True

        if id(obj) in memo:
            raise ValueError("{0} is a recursive structure".format(obj))

        memo[id(obj)] = obj

        if type(obj) in builtins_seq:
            return all(map(check_relaxed, obj))
        elif type(obj) in builtins_mapping:
            return all(map(check_relaxed, chain(obj.keys(), obj.values())))

        # numpy.int, uint, ...
        elif isinstance(obj, numbers.Integral):
            if repr(obj) == repr(int(obj)):
                return True
        # numpy.float, ...
        elif isinstance(obj, numbers.Real):
            if repr(obj) == repr(float(obj)):
                return True

        raise TypeError("{0} can not be serialized as a python "
                        "literal".format(type(obj)))

    if relaxed_types:
        check_relaxed(obj)
    else:
        check(obj)

    if indent is not None:
        return pprint.pformat(obj, width=80 * 2, indent=indent, compact=True)
    else:
        return repr(obj)


literal_loads = literal_eval

from .scheme import Scheme  # pylint: disable=all

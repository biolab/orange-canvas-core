"""
Scheme save/load routines.

"""
import numbers
import sys
import types
import warnings
import base64
import binascii
import itertools

from xml.etree.ElementTree import TreeBuilder, Element, ElementTree, parse

from collections import defaultdict
from itertools import chain, count

import pickle
import json
import pprint

import ast
from ast import literal_eval

import logging

from typing import (
    NamedTuple, Dict, Tuple, List, Union, Any, Optional, AnyStr, IO
)

from . import SchemeNode, SchemeLink
from .annotations import SchemeTextAnnotation, SchemeArrowAnnotation
from .errors import IncompatibleChannelTypeError

from ..registry import global_registry, WidgetRegistry
from ..registry import WidgetDescription, InputSignal, OutputSignal

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
    if not isinstance(node.body, ast.Str):
        raise ValueError("%r is not a string literal" % source)
    return node.body.s


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

    if not all(isinstance(el, (ast.Str, ast.Num)) or
               # allow signed number literals in Python3 (i.e. -1|+1|-1.0)
               (isinstance(el, ast.UnaryOp) and
                isinstance(el.op, (ast.UAdd, ast.USub)) and
                isinstance(el.operand, ast.Num))
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
    if isinstance(node, ast.Str):
        return node.s
    elif isinstance(node, ast.Bytes):
        return node.s
    elif isinstance(node, ast.Num):
        return node.n
    elif isinstance(node, ast.NameConstant):
        return node.value

    raise ValueError("Not a terminal")


# Intermediate scheme representation
_scheme = NamedTuple(
    "_scheme", [
        ("title", str),
        ("version", str),
        ("description", str),
        ("nodes", List['_node']),
        ("links", List['_link']),
        ("annotations", List['_annotation']),
        ("session_state", '_session_data')
    ]
)

_node = NamedTuple(
    "_node", [
        ("id", str),
        ("title", str),
        ("name", str),
        ("position", Tuple[float, float]),
        ("project_name", str),
        ("qualified_name", str),
        ("version", str),
        ("data", Optional['_data'])
    ]
)

_data = NamedTuple(
    "_data", [
        ("format", str),
        ("data", Union[bytes, str])
    ]
)

_link = NamedTuple(
    "_link", [
        ("id", str),
        ("source_node_id", str),
        ("sink_node_id", str),
        ("source_channel", str),
        ("sink_channel", str),
        ("enabled", bool),
    ]
)

_annotation = NamedTuple(
    "_annotation", [
        ("id", str),
        ("type", str),
        ("params", Union['_text_params', '_arrow_params']),
    ]
)

_text_params = NamedTuple(
    "_text_params", [
        ("geometry", Tuple[float, float, float, float]),
        ("text", str),
        ("font", Dict[str, Any]),
        ("content_type", str),
    ]
)

_arrow_params = NamedTuple(
    "_arrow_params", [
        ("geometry", Tuple[Tuple[float, float], Tuple[float, float]]),
        ("color", str),
    ])

_window_group = NamedTuple(
    "_window_group", [
        ("name", str),
        ("default", bool),
        ("state", List[Tuple[str, bytes]])
    ]
)

_session_data = NamedTuple(
    "_session_data", [
        ("groups", List[_window_group])
    ]
)


def parse_ows_etree_v_2_0(tree):
    # type: (ElementTree) -> _scheme
    """
    Parset an xml.etree.ElementTree struct into a intermediate workflow
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
        nodes.append(
            _node(  # type: ignore
                id=node_id,
                title=node.get("title"),
                name=node.get("name"),
                position=(_px, _py),
                project_name=node.get("project_name"),
                qualified_name=node.get("qualified_name"),
                version=node.get("version", ""),
                data=properties.get(node_id, None)
            )
        )

    for link in tree.findall("links/link"):
        params = _link(
            id=link.get("id"),
            source_node_id=link.get("source_node_id"),
            sink_node_id=link.get("sink_node_id"),
            source_channel=link.get("source_channel"),
            sink_channel=link.get("sink_channel"),
            enabled=link.get("enabled") == "true",
        )
        links.append(params)

    for annot in tree.findall("annotations/*"):
        if annot.tag == "text":
            rect = tuple_eval(annot.get("rect", "(0.0, 0.0, 20.0, 20.0)"))

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
            start = tuple_eval(annot.get("start", "(0, 0)"))
            end = tuple_eval(annot.get("end", "(0, 0)"))
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


def parse_ows_stream(stream):
    # type: (Union[AnyStr, IO]) -> _scheme
    doc = parse(stream)
    scheme_el = doc.getroot()
    if scheme_el.tag != "scheme":
        raise ValueError(
            "Invalid Orange Workflow Scheme file"
        )
    version = scheme_el.get("version", None)
    if version is None:
        # Check for "widgets" tag - old Orange<2.7 format
        if scheme_el.find("widgets") is not None:
            raise ValueError(
                "Cannot open Orange Workflow Scheme v1.0. This format is no "
                "longer supported"
            )
        else:
            raise ValueError(
                "Invalid Orange Workflow Scheme file (missing version)."
            )
    if version in {"2.0", "2.1"}:
        return parse_ows_etree_v_2_0(doc)
    else:
        raise ValueError()


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
    nodes = scheme_desc.nodes
    for i, node in list(enumerate(nodes)):
        if not registry.has_widget(node.qualified_name) and \
                node.qualified_name in replacements:
            qname = replacements[node.qualified_name]
            desc = registry.widget(qname)
            nodes[i] = node._replace(qualified_name=desc.qualified_name,
                                     project_name=desc.project_name)
        nodes_by_id[node.id] = nodes[i]

    # replace links
    links = scheme_desc.links
    for i, link in list(enumerate(links)):
        nsource = nodes_by_id[link.source_node_id]
        nsink = nodes_by_id[link.sink_node_id]

        _, source_rep = replacements_channels.get(
            nsource.qualified_name, ({}, {}))
        sink_rep, _ = replacements_channels.get(
            nsink.qualified_name, ({}, {}))

        if link.source_channel in source_rep:
            link = link._replace(
                source_channel=source_rep[link.source_channel])
        if link.sink_channel in sink_rep:
            link = link._replace(
                sink_channel=sink_rep[link.sink_channel])
        links[i] = link

    return scheme_desc._replace(nodes=nodes, links=links)


def scheme_load(scheme, stream, registry=None, error_handler=None):
    desc = parse_ows_stream(stream)  # type: _scheme

    if registry is None:
        registry = global_registry()

    if error_handler is None:
        def error_handler(exc):
            raise exc

    desc = resolve_replaced(desc, registry)
    nodes_not_found = []
    nodes = []
    nodes_by_id = {}
    links = []
    annotations = []

    scheme.title = desc.title
    scheme.description = desc.description

    for node_d in desc.nodes:
        try:
            w_desc = registry.widget(node_d.qualified_name)
        except KeyError as ex:
            error_handler(UnknownWidgetDefinition(*ex.args))
            nodes_not_found.append(node_d.id)
        else:
            node = SchemeNode(
                w_desc, title=node_d.title, position=node_d.position)
            data = node_d.data

            if data:
                try:
                    properties = loads(data.data, data.format)
                except Exception:
                    log.error("Could not load properties for %r.", node.title,
                              exc_info=True)
                else:
                    node.properties = properties

            nodes.append(node)
            nodes_by_id[node_d.id] = node

    for link_d in desc.links:
        source_id = link_d.source_node_id
        sink_id = link_d.sink_node_id

        if source_id in nodes_not_found or sink_id in nodes_not_found:
            continue

        source = nodes_by_id[source_id]
        sink = nodes_by_id[sink_id]
        try:
            link = SchemeLink(source, link_d.source_channel,
                              sink, link_d.sink_channel,
                              enabled=link_d.enabled)
        except (ValueError, IncompatibleChannelTypeError) as ex:
            error_handler(ex)
        else:
            links.append(link)

    for annot_d in desc.annotations:
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
            log.warning("Ignoring unknown annotation type: %r", annot_d.type)
            continue
        annotations.append(annot)

    for node in nodes:
        scheme.add_node(node)

    for link in links:
        scheme.add_link(link)

    for annot in annotations:
        scheme.add_annotation(annot)

    if desc.session_state.groups:
        groups = []
        for g in desc.session_state.groups:  # type: _window_group
            # resolve node_id -> node
            state = [(nodes_by_id[node_id], data)
                     for node_id, data in g.state if node_id in nodes_by_id]

            groups.append(Scheme.WindowGroup(g.name, g.default, state))
        scheme.set_window_group_presets(groups)
    return scheme


def scheme_to_etree(scheme, data_format="literal", pickle_fallback=False):
    """
    Return an `xml.etree.ElementTree` representation of the `scheme`.
    """
    builder = TreeBuilder(element_factory=Element)
    builder.start("scheme", {"version": "2.0",
                             "title": scheme.title or "",
                             "description": scheme.description or ""})

    # Nodes
    node_ids = defaultdict(lambda c=itertools.count(): next(c))
    builder.start("nodes", {})
    for node in scheme.nodes:  # type: SchemeNode
        desc = node.description
        attrs = {"id": str(node_ids[node]),
                 "name": desc.name,
                 "qualified_name": desc.qualified_name,
                 "project_name": desc.project_name or "",
                 "version": desc.version or "",
                 "title": node.title,
                 }
        if node.position is not None:
            attrs["position"] = str(node.position)

        if type(node) is not SchemeNode:
            attrs["scheme_node_type"] = "%s.%s" % (type(node).__name__,
                                                   type(node).__module__)
        builder.start("node", attrs)
        builder.end("node")

    builder.end("nodes")

    # Links
    link_ids = defaultdict(lambda c=itertools.count(): next(c))
    builder.start("links", {})
    for link in scheme.links:
        source = link.source_node
        sink = link.sink_node
        source_id = node_ids[source]
        sink_id = node_ids[sink]
        attrs = {"id": str(link_ids[link]),
                 "source_node_id": str(source_id),
                 "sink_node_id": str(sink_id),
                 "source_channel": link.source_channel.name,
                 "sink_channel": link.sink_channel.name,
                 "enabled": "true" if link.enabled else "false",
                 }
        builder.start("link", attrs)
        builder.end("link")

    builder.end("links")

    # Annotations
    annotation_ids = defaultdict(lambda c=itertools.count(): next(c))
    builder.start("annotations", {})
    for annotation in scheme.annotations:
        annot_id = annotation_ids[annotation]
        attrs = {"id": str(annot_id)}
        data = None
        if isinstance(annotation, SchemeTextAnnotation):
            tag = "text"
            attrs.update({"type": annotation.content_type})
            attrs.update({"rect": repr(annotation.rect)})

            # Save the font attributes
            font = annotation.font
            attrs.update({"font-family": font.get("family", None),
                          "font-size": font.get("size", None)})
            attrs = [(key, value) for key, value in attrs.items()
                     if value is not None]
            attrs = dict((key, str(value)) for key, value in attrs)
            data = annotation.content
        elif isinstance(annotation, SchemeArrowAnnotation):
            tag = "arrow"
            attrs.update({"start": repr(annotation.start_pos),
                          "end": repr(annotation.end_pos),
                          "fill": annotation.color})
            data = None
        else:
            log.warning("Can't save %r", annotation)
            continue
        builder.start(tag, attrs)
        if data is not None:
            builder.data(data)
        builder.end(tag)

    builder.end("annotations")

    builder.start("thumbnail", {})
    builder.end("thumbnail")

    # Node properties/settings
    builder.start("node_properties", {})
    for node in scheme.nodes:
        data = None
        if node.properties:
            try:
                data, format = dumps(node.properties, format=data_format,
                                     pickle_fallback=pickle_fallback)
            except Exception:
                log.error("Error serializing properties for node %r",
                          node.title, exc_info=True)
            if data is not None:
                builder.start("properties",
                              {"node_id": str(node_ids[node]),
                               "format": format})
                builder.data(data)
                builder.end("properties")

    builder.end("node_properties")
    builder.start("session_state", {})
    builder.start("window_groups", {})

    for g in scheme.window_group_presets():
        builder.start(
            "group", {"name": g.name, "default": str(g.default).lower()}
        )
        for node, data in g.state:
            if node not in node_ids:
                continue
            builder.start("window_state", {"node_id": str(node_ids[node])})
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
    tree = scheme_to_etree(scheme, data_format="literal",
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
        Relaxed type checking. In addition to exact builtin numberic types,
        the numbers.Integer, numbers.Real are checked and alowed if their
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

"""
Scheme save/load routines.

"""
import io
import numbers
import warnings
import base64
import binascii
import pickle
from functools import partial

from xml.etree.ElementTree import TreeBuilder, Element, ElementTree, parse

from itertools import chain

import json
import pprint

import ast
from ast import literal_eval

import logging

from typing import (
    NamedTuple, Dict, Tuple, List, Union, Any, Optional, AnyStr, IO, Callable
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


class DeserializationWarning(UserWarning):
    pass


class PickleDataWarning(DeserializationWarning):
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


def default_error_handler(err: Exception):
    raise err


def default_warning_handler(err: Warning):
    warnings.warn(err, stacklevel=2)


def default_serializer(node: SchemeNode, data_format="literal") -> Optional[Tuple[AnyStr, str]]:
    if node.properties:
        return dumps(node.properties, format=data_format), data_format
    else:
        return None


def default_serializer_with_pickle_fallback(
        node: SchemeNode, data_format="literal"
) -> Optional[Tuple[AnyStr, str]]:
    try:
        return default_serializer(node, data_format=data_format)
    except (UnserializableTypeError, UnserializableValueError):
        data = pickle.dumps(node.properties, protocol=PICKLE_PROTOCOL)
        data = base64.encodebytes(data).decode("ascii")
        return data, "pickle"


DataSerializerType = Callable[[SchemeNode], Optional[Tuple[AnyStr, str]]]


def default_deserializer(payload, format_):
    return loads(payload, format_)


def default_deserializer_with_pickle_fallback(
        payload, format_, *, unpickler_class=None
):
    if format_ == "pickle":
        if isinstance(payload, str):
            payload = payload.encode("ascii")
        if unpickler_class is None:
            unpickler_class = pickle.Unpickler
        unpickler = unpickler_class(io.BytesIO(base64.decodebytes(payload)))
        return unpickler.load()
    else:
        return default_deserializer(payload, format_)


DataDeserializerType = Callable[[AnyStr, str], Any]


def scheme_load(
        scheme, stream, registry=None,
        error_handler=None, warning_handler=None,
        data_deserializer: DataDeserializerType = None
):
    """
    Populate a Scheme instance with workflow read from an ows data stream.

    Parameters
    ----------
    scheme: Scheme
    stream: typing.IO
    registry: WidgetRegistry
    error_handler:  Callable[[Exception], None]
    warning_handler: Callable[[Warning], None]
    data_deserializer: Callable[[AnyStr, str], Any]
    """
    desc = parse_ows_stream(stream)  # type: _scheme

    if registry is None:
        registry = global_registry()

    if error_handler is None:
        def error_handler(exc):
            raise exc

    if warning_handler is None:
        warning_handler = warnings.warn

    if data_deserializer is None:
        data_deserializer = default_deserializer

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

            if data is not None:
                try:
                    properties = data_deserializer(data.data, data.format)
                except UnsupportedPickleFormatError:
                    log.error("Could not load pickled properties for %r.", node.title,
                              exc_info=True)
                    warning_handler(
                        PickleDataWarning(
                            "The file contains pickle data. The settings for '{}' "
                            "were not restored.".format(node_d.title)
                        )
                    )
                except Exception as err:  # pylint: disable=broad-except
                    log.error("Could not load properties for %r.", node.title,
                              exc_info=True)
                    warning_handler(
                        DeserializationWarning(
                            "Could not load properties for %r.", node.title
                        )
                    )
                    node.setProperty("__ows_data_deserialization_error", (type(err), err.args))
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


def scheme_to_interm(
        scheme: 'Scheme',
        data_serializer: DataSerializerType = None,
        error_handler: Callable[[Exception], None] = None,
        warning_handler: Callable[[Warning], None] = None,
) -> _scheme:
    """
    Return a workflow scheme in its intermediate representation for
    serialization.
    """
    node_ids = {}  # type: Dict[SchemeNode, str]
    nodes = []
    links = []
    annotations = []
    window_presets = []

    if warning_handler is None:
        warning_handler = default_warning_handler

    if error_handler is None:
        error_handler = default_error_handler

    if data_serializer is None:
        data_serializer = default_serializer

    # Nodes
    for node_id, node in enumerate(scheme.nodes):  # type: SchemeNode
        data_payload = None
        try:
            data_payload_ = data_serializer(node)
        except Exception as err:
            error_handler(err)
        else:
            if data_payload_ is not None:
                assert len(data_payload_) == 2
                data_, format_ = data_payload_
                data_payload = _data(format_, data_)
        desc = node.description
        inode = _node(
            id=str(node_id),
            title=node.title,
            name=node.description.name,
            position=node.position,
            qualified_name=desc.qualified_name,
            project_name=desc.project_name or "",
            version=desc.version or "",
            data=data_payload,
        )
        node_ids[node] = str(node_id)
        nodes.append(inode)

    for link_id, link in enumerate(scheme.links):
        ilink = _link(
            id=str(link_id),
            source_node_id=node_ids[link.source_node],
            source_channel=link.source_channel.name,
            sink_node_id=node_ids[link.sink_node],
            sink_channel=link.sink_channel.name,
            enabled=link.enabled,
        )
        links.append(ilink)

    for annot_id, annot in enumerate(scheme.annotations):
        if isinstance(annot, SchemeTextAnnotation):
            atype = "text"
            params = _text_params(
                geometry=annot.geometry,
                text=annot.text,
                content_type=annot.content_type,
                font={},  # deprecated.
            )
        elif isinstance(annot, SchemeArrowAnnotation):
            atype = "arrow"
            params = _arrow_params(
                geometry=annot.geometry,
                color=annot.color,
            )
        else:
            assert False

        iannot = _annotation(
            str(annot_id), type=atype, params=params,
        )
        annotations.append(iannot)

    for preset in scheme.window_group_presets():  # type: Scheme.WindowGroup
        state = [(node_ids[n], state) for n, state in preset.state]
        window_presets.append(
            _window_group(preset.name, preset.default, state)
        )

    return _scheme(
        scheme.title, "2.0", scheme.description, nodes, links, annotations,
        session_state=_session_data(window_presets),
    )


def scheme_to_etree_2_0(
        scheme: 'Scheme',
        data_serializer=None,
        **kwargs
):
    return interm_to_etree_2_0(
        scheme_to_interm(scheme, data_serializer=data_serializer, **kwargs)
    )


def interm_to_etree_2_0(scheme: _scheme) -> ElementTree:
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
                "name": node.name,
                "qualified_name": node.qualified_name,
                "project_name": node.project_name,
                "version": node.version,
                "title": node.title,
                "position": node.position,
            }
        )
        builder.end("node")

    builder.end("nodes")

    # Links
    builder.start("links", {})
    for link in scheme.links:
        builder.start(
            "link", {
                "id": link.id,
                "source_node_id": link.source_node_id,
                "sink_node_id": link.sink_node_id,
                "source_channel": link.source_channel,
                "sink_channel": link.sink_channel,
                "enabled": "true" if link.enabled else "false",
            }
        )
        builder.end("link")
    builder.end("links")

    # Annotations
    builder.start("annotations", {})
    for annotation in scheme.annotations:
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


def scheme_to_etree(scheme, data_format="literal", pickle_fallback=False):
    """
    Return an `xml.etree.ElementTree` representation of the `scheme`.
    """
    if pickle_fallback:
        data_serializer = default_serializer_with_pickle_fallback
    else:
        data_serializer = default_serializer
    data_serializer = partial(data_serializer, data_format=data_format)
    return interm_to_etree_2_0(
        scheme_to_interm(scheme, data_serializer=data_serializer)
    )


def scheme_to_ows_stream(scheme, stream, pretty=False, pickle_fallback=False, data_serializer=None, **kwargs):
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
        If `True` allow scheme node properties to be saved using pickle
        protocol if properties cannot be saved using the default
        notation.

    """
    if pickle_fallback is not False and data_serializer is not None:
        raise TypeError("pickle_fallback and data_serializer are mutually "
                        "exclusive parameters")
    if data_serializer is None:
        if pickle_fallback:
            data_serializer = default_serializer_with_pickle_fallback
        else:
            data_serializer = default_serializer

    tree = scheme_to_etree_2_0(scheme, data_serializer=data_serializer, **kwargs)
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


class UnsupportedFormatError(ValueError):
    pass


class UnsupportedPickleFormatError(UnsupportedFormatError): ...


class UnserializableValueError(ValueError):
    pass


class UnserializableTypeError(TypeError):
    pass


def dumps(obj, format="literal", indent=4):
    """
    Serialize `obj` using `format` ('json' or 'literal') and return its
    string representation.

    Raises
    ------
    TypeError
        If object is not a supported type for serialization format
    ValueError
        If object is a recursive structure
    """
    if format == "literal":
        return literal_dumps(obj, indent=indent)
    elif format == "json":
        try:
            return json.dumps(obj, indent=indent)
        except TypeError as e:
            raise UnserializableTypeError(*e.args) from e
        except ValueError as e:
            raise UnserializableValueError(*e.args) from e
    elif format == "pickle":
        raise UnsupportedPickleFormatError()
    else:
        raise UnsupportedFormatError("Unsupported format %r" % format)


def loads(string, format):
    if format == "literal":
        return literal_eval(string)
    elif format == "json":
        return json.loads(string)
    elif format == "pickle":
        raise UnsupportedPickleFormatError()
    else:
        raise UnsupportedFormatError("Unsupported format %r" % format)


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
        if type(obj) in builtins:
            return True

        if id(obj) in memo:
            raise ValueError("{0} is a recursive structure".format(obj))

        memo[id(obj)] = obj

        if type(obj) in builtins_seq:
            return all(map(check, obj))
        elif type(obj) in builtins_mapping:
            return all(map(check, chain(obj.keys(), obj.values())))

        raise UnserializableTypeError("{0} can not be serialized as a python"
                                      "literal".format(type(obj)))

    def check_relaxed(obj):
        if type(obj) in builtins:
            return True

        if id(obj) in memo:
            raise UnserializableValueError("{0} is a recursive structure".format(obj))

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

        raise UnserializableTypeError("{0} can not be serialized as a python "
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

from .scheme import Scheme  # pylint: disable=wrong-import-position

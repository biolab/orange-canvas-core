"""
======
Scheme
======

The scheme package implements and defines the underlying workflow model.

The :class:`.Scheme` class represents the workflow and is composed of a set
of :class:`.Node`\\s connected with :class:`.Link`\\s, defining an
directed acyclic graph (DAG). Additionally instances of
:class:`~.annotations.ArrowAnnotation` or :class:`~.annotations.TextAnnotation`
can be inserted into the scheme.
"""

from .node import Node, SchemeNode
from .metanode import MetaNode, InputNode, OutputNode
from .link import Link, compatible_channels, can_connect, possible_links
from .scheme import Scheme
from .annotations import Annotation, ArrowAnnotation, TextAnnotation
from ..registry import InputSignal, OutputSignal

from .errors import *
from .events import *

__all__ = [
    "Node", "InputNode", "OutputNode", "SchemeNode", "MetaNode", "Link",
    "Workflow", "Scheme", "Annotation", "ArrowAnnotation", "TextAnnotation",
    "InputSignal", "OutputSignal", "compatible_channels", "can_connect",
    "possible_links",
    # from .events import *
    "WorkflowEvent", "NodeEvent", "NodeInputChannelEvent",
    "NodeOutputChannelEvent", "LinkEvent", "AnnotationEvent",
    "WorkflowEnvChanged"
]

#: Alias for SchemeLink
SchemeLink = Link
#: Alias for Scheme
Workflow = Scheme
#: Alias for BaseSchemeAnnotation
BaseSchemeAnnotation = Annotation
#: Alias for SchemeArrowAnnotation
SchemeArrowAnnotation = Arrow = ArrowAnnotation
#: Alias for SchemeTextAnnotation
SchemeTextAnnotation = Text = TextAnnotation

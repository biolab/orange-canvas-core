"""
============================
Workflow Events (``events``)
============================

Here defined are events dispatched to and from an Scheme workflow
instance.

"""
import typing
from typing import Any

from AnyQt.QtCore import QEvent

if typing.TYPE_CHECKING:
    from orangecanvas.scheme import SchemeLink, SchemeNode, BaseSchemeAnnotation

__all__ = [
    "WorkflowEvent", "NodeEvent", "LinkEvent", "AnnotationEvent",
    "WorkflowEnvChanged"
]


class WorkflowEvent(QEvent):
    #: Delivered to Scheme when a node has been added (:class:`NodeEvent`)
    NodeAdded = QEvent.Type(QEvent.registerEventType())

    #: Delivered to Scheme when a node has been removed (:class:`NodeEvent`)
    NodeRemoved = QEvent.Type(QEvent.registerEventType())

    #: A Link has been added to the scheme (:class:`LinkEvent`)
    LinkAdded = QEvent.Type(QEvent.registerEventType())

    #: A Link has been removed from the scheme (:class:`LinkEvent`)
    LinkRemoved = QEvent.Type(QEvent.registerEventType())

    #: An input Link has been added to a node (:class:`LinkEvent`)
    InputLinkAdded = QEvent.Type(QEvent.registerEventType())

    #: An output Link has been added to a node (:class:`LinkEvent`)
    OutputLinkAdded = QEvent.Type(QEvent.registerEventType())

    #: An input Link has been removed from a node (:class:`LinkEvent`)
    InputLinkRemoved = QEvent.Type(QEvent.registerEventType())

    #: An output Link has been removed from a node (:class:`LinkEvent`)
    OutputLinkRemoved = QEvent.Type(QEvent.registerEventType())

    #: Node's (runtime) state has changed (:class:`NodeEvent`)
    NodeStateChange = QEvent.Type(QEvent.registerEventType())

    #: Link's (runtime) state has changed (:class:`LinkEvent`)
    LinkStateChange = QEvent.Type(QEvent.registerEventType())

    #: Input link's (runtime) state has changed (:class:`LinkEvent`)
    InputLinkStateChange = QEvent.Type(QEvent.registerEventType())

    #: Output link's (runtime) state has changed (:class:`LinkEvent`)
    OutputLinkStateChange = QEvent.Type(QEvent.registerEventType())

    #: Request for Node's runtime initialization (e.g.
    #: load required data, establish connection, ...)
    NodeInitialize = QEvent.Type(QEvent.registerEventType())

    #: Restore the node from serialized state
    NodeRestore = QEvent.Type(QEvent.registerEventType())
    NodeSaveStateRequest = QEvent.Type(QEvent.registerEventType())

    #: Node user activate request (e.g. on double click in the
    #: canvas GUI)
    NodeActivateRequest = QEvent.Type(QEvent.registerEventType())

    # Workflow runtime changed (Running/Paused/Stopped, ...)
    RuntimeStateChange = QEvent.Type(QEvent.registerEventType())

    #: Workflow resource changed (e.g. work directory, env variable)
    WorkflowResourceChange = QEvent.Type(QEvent.registerEventType())
    WorkflowEnvironmentChange = WorkflowResourceChange
    #: Workflow is about to close.
    WorkflowAboutToClose = QEvent.Type(QEvent.registerEventType())
    WorkflowClose = QEvent.Type(QEvent.registerEventType())

    AnnotationAdded = QEvent.Type(QEvent.registerEventType())
    AnnotationRemoved = QEvent.Type(QEvent.registerEventType())
    AnnotationChange = QEvent.Type(QEvent.registerEventType())

    #: Request activation (show and raise) of the window containing
    #: the workflow view
    ActivateParentRequest = QEvent.Type(QEvent.registerEventType())


class NodeEvent(WorkflowEvent):
    """
    An event notifying the receiver of an workflow link change.

    This event is used with:

        * :data:`WorkflowEvent.NodeAdded`
        * :data:`WorkflowEvent.NodeRemoved`
        * :data:`WorkflowEvent.NodeStateChange`
        * :data:`WorkflowEvent.NodeActivateRequest`
        * :data:`WorkflowEvent.ActivateParentRequest`
        * :data:`WorkflowEvent.OutputLinkRemoved`

    Parameters
    ----------
    etype: QEvent.Type
    node: SchemeNode
    """
    def __init__(self, etype, node):
        # type: (QEvent.Type, SchemeNode) -> None
        super().__init__(etype)
        self.__node = node

    def node(self):
        # type: () -> SchemeNode
        """
        Return
        ------
        node : SchemeNode
            The node instance.
        """
        return self.__node


class LinkEvent(WorkflowEvent):
    """
    An event notifying the receiver of an workflow link change.

    This event is used with:

        * :data:`WorkflowEvent.LinkAdded`
        * :data:`WorkflowEvent.LinkRemoved`
        * :data:`WorkflowEvent.InputLinkAdded`
        * :data:`WorkflowEvent.InputLinkRemoved`
        * :data:`WorkflowEvent.OutputLinkAdded`
        * :data:`WorkflowEvent.OutputLinkRemoved`
        * :data:`WorkflowEvent.InputLinkStateChange`
        * :data:`WorkflowEvent.OutputLinkStateChange`

    Parameters
    ----------
    etype: QEvent.Type
    link: SchemeLink
        The link subject to change
    """
    def __init__(self, etype, link):
        # type: (QEvent.Type, SchemeLink) -> None
        super().__init__(etype)
        self.__link = link

    def link(self):
        # type: () -> SchemeLink
        """
        Return
        ------
        link : SchemeLink
            The link instance.
        """
        return self.__link


class AnnotationEvent(WorkflowEvent):
    """
    An event notifying the receiver of an workflow annotation changes

    This event is used with:

        * :data:`WorkflowEvent.AnnotationAdded`
        * :data:`WorkflowEvent.AnnotationRemoved`

    Parameters
    ----------
    etype: QEvent.Type
    annotation: BaseSchemeAnnotation
        The annotation that is a subject of change.
    """
    def __init__(self, etype, annotation):
        # type: (QEvent.Type, BaseSchemeAnnotation) -> None
        super().__init__(etype)
        self.__annotation = annotation

    def annotation(self):
        # type: () -> BaseSchemeAnnotation
        """
        Return
        ------
        annotation : BaseSchemeAnnotation
            The annotation instance.
        """
        return self.__annotation


class WorkflowEnvChanged(WorkflowEvent):
    """
    An event notifying the receiver of a workflow environment change.

    Parameters
    ----------
    name: str
        The name of the environment property that was changed
    newValue: Any
        The new value
    oldValue: Any
        The old value

    See Also
    --------
    Scheme.runtime_env
    """
    def __init__(self, name, newValue, oldValue):
        # type: (str, Any, Any) -> None
        super().__init__(WorkflowEvent.WorkflowEnvironmentChange)
        self.__name = name
        self.__oldValue = oldValue
        self.__newValue = newValue

    def name(self):
        # type: () -> str
        """
        The name of the environment property.
        """
        return self.__name

    def oldValue(self):
        # type: () -> Any
        """
        The old value.
        """
        return self.__oldValue

    def newValue(self):
        # type: () -> Any
        """
        The new value.
        """
        return self.__newValue

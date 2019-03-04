"""
Workflow Events
---------------

Here defined are events dispatched to and from an Scheme workflow
instance.

"""
import typing

from AnyQt.QtCore import QEvent

from typing import Any

if typing.TYPE_CHECKING:
    from orangecanvas.scheme import SchemeLink, SchemeNode, BaseSchemeAnnotation

__all__ = [
    "WorkflowEvent", "NodeEvent", "LinkEvent", "AnnotationEvent",
    "WorkflowEnvChanged"
]


class WorkflowEvent(QEvent):
    #: Delivered to Scheme when a node has been added
    NodeAdded = QEvent.registerEventType()
    #: Delivered to Scheme when a node has been removed
    NodeRemoved = QEvent.registerEventType()
    #: A Link has been added to the scheme
    LinkAdded = QEvent.registerEventType()
    #: A Link has been removed from the scheme
    LinkRemoved = QEvent.registerEventType()

    #: An input Link has been added to a node
    InputLinkAdded = QEvent.registerEventType()
    #: An output Link has been added to a node
    OutputLinkAdded = QEvent.registerEventType()
    #: An input Link has been removed from a node
    InputLinkRemoved = QEvent.registerEventType()
    #: An output Link has been removed from a node
    OutputLinkRemoved = QEvent.registerEventType()

    #: Node's (runtime) state has changed
    NodeStateChange = QEvent.registerEventType()
    #: Link's (runtime) state has changed
    LinkStateChange = QEvent.registerEventType()
    #: Request for Node's runtime initialization (e.g.
    #: load required data, establish connection, ...)
    NodeInitialize = QEvent.registerEventType()
    #: Restore the node from serialized state
    NodeRestore = QEvent.registerEventType()
    NodeSaveStateRequest = QEvent.registerEventType()  # ?
    #: Node user activate request (e.g. on double click in the
    #: canvas GUI)
    NodeActivateRequest = QEvent.registerEventType()

    # Workflow runtime changed (Running/Paused/Stopped, ...)
    RuntimeStateChange = QEvent.registerEventType()

    #: Workflow resource changed (e.g. work directory, env variable)
    WorkflowResourceChange = QEvent.registerEventType()
    WorkflowEnvironmentChange = WorkflowResourceChange
    #: Workflow is about to close.
    WorkflowAboutToClose = QEvent.registerEventType()
    WorkflowClose = QEvent.registerEventType()

    AnnotationAdded = QEvent.registerEventType()
    AnnotationRemoved = QEvent.registerEventType()
    AnnotationChange = QEvent.registerEventType()

    #: Request activation (show and raise) of the window containing
    #: the workflow view
    ActivateParentRequest = QEvent.registerEventType()


class NodeEvent(WorkflowEvent):
    def __init__(self, etype, node):
        # type: (QEvent.Type, SchemeNode) -> None
        super().__init__(etype)
        self.__node = node

    def node(self):
        return self.__node


class LinkEvent(WorkflowEvent):
    def __init__(self, etype, link):
        # type: (QEvent.Type, SchemeLink) -> None
        super().__init__(etype)
        self.__link = link

    def link(self):
        return self.__link


class AnnotationEvent(WorkflowEvent):
    def __init__(self, etype, annotation):
        # type: (QEvent.Type, BaseSchemeAnnotation) -> None
        super().__init__(etype)
        self.__annotation = annotation

    def annotation(self):
        return self.__annotation


class WorkflowEnvChanged(WorkflowEvent):
    """
    An event notifying the receiver of a workflow environment change.

    See Also
    --------
    Scheme.runtime_env
    """
    def __init__(self, name, newValue, oldValue):
        super().__init__(QEvent.Type(WorkflowEvent.WorkflowEnvironmentChange))
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

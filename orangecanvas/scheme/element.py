from typing import TYPE_CHECKING, Optional

from AnyQt.QtCore import QObject

if TYPE_CHECKING:
    from . import MetaNode, Workflow


class Element(QObject):
    """
    Base class for workflow elements.
    """
    __parent_node: Optional['MetaNode'] = None

    def _set_parent_node(self, node: Optional['MetaNode']) -> None:
        """Internal. Set the parent node."""
        self.__parent_node = node

    def parent_node(self) -> Optional['MetaNode']:
        """Return the parent workflow node."""
        return self.__parent_node

    __workflow: Optional['Workflow'] = None

    def _set_workflow(self, workflow: Optional['Workflow']):
        """Internal. Set the parent workflow."""
        self.__workflow = workflow

    def workflow(self) -> Optional['Workflow']:
        """Return the parent workflow."""
        return self.__workflow

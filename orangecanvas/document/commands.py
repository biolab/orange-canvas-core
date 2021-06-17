"""
Undo/Redo Commands

"""
from typing import Callable, Optional, Tuple, List, Any

from AnyQt.QtWidgets import QUndoCommand

from ..scheme import (
    Workflow, Node, Link, MetaNode, Annotation, Text, Arrow, InputNode,
    OutputNode,
)

Pos = Tuple[float, float]
Rect = Tuple[float, float, float, float]
Line = Tuple[Pos, Pos]


class UndoCommand(QUndoCommand):
    """
    For pickling
    """
    def __init__(self, text, parent=None):
        QUndoCommand.__init__(self, text, parent)
        self.__parent = parent
        self.__initialized = True

        # defined and initialized in __setstate__
        # self.__child_states = {}
        # self.__children = []

    def __getstate__(self):
        return {
            **{k: v for k, v in self.__dict__.items()},
            '_UndoCommand__initialized': False,
            '_UndoCommand__text': self.text(),
            '_UndoCommand__children':
                [self.child(i) for i in range(self.childCount())]
        }

    def __setstate__(self, state):
        if hasattr(self, '_UndoCommand__initialized') and \
                self.__initialized:
            return

        text = state['_UndoCommand__text']
        parent = state['_UndoCommand__parent']  # type: UndoCommand

        if parent is not None and \
                (not hasattr(parent, '_UndoCommand__initialized') or
                 not parent.__initialized):
            # will be initialized in parent's __setstate__
            if not hasattr(parent, '_UndoCommand__child_states'):
                setattr(parent, '_UndoCommand__child_states', {})
            parent.__child_states[self] = state
            return

        # init must be called on unpickle-time to recreate Qt object
        UndoCommand.__init__(self, text, parent)
        if hasattr(self, '_UndoCommand__child_states'):
            for child, s in self.__child_states.items():
                child.__setstate__(s)

        self.__dict__ = {k: v for k, v in state.items()}
        self.__initialized = True

    @staticmethod
    def from_QUndoCommand(qc: QUndoCommand, parent=None):
        if type(qc) == QUndoCommand:
            qc.__class__ = UndoCommand

        qc.__parent = parent

        children = [qc.child(i) for i in range(qc.childCount())]
        for child in children:
            UndoCommand.from_QUndoCommand(child, parent=qc)

        return qc


class AddNodeCommand(UndoCommand):
    def __init__(
            self,
            scheme: Workflow,
            node: Node,
            parent_node: MetaNode, *,
            parent=None
    ) -> None:
        super().__init__("Add %s" % node.title, parent)
        self.scheme = scheme
        self.node = node
        self.parent_node = parent_node

    def redo(self):
        self.scheme.add_node(self.node, self.parent_node)

    def undo(self):
        self.scheme.remove_node(self.node)


def input_links(node: Node):
    parent = node.parent_node()
    ilinks = parent.input_links(node)
    if isinstance(node, InputNode):
        parent_ = parent.parent_node()
        imacro = parent_.find_links(
            sink_node=parent,
            sink_channel=node.input_channels()[0],
        )
    else:
        imacro = []
    return ilinks, imacro


def output_links(node: Node):
    parent = node.parent_node()
    olinks = parent.output_links(node)
    if isinstance(node, OutputNode):
        parent_ = parent.parent_node()
        omacro = parent_.find_links(
            source_node=parent,
            source_channel=node.output_channels()[0],
        )
    else:
        omacro = []
    return olinks, omacro


class RemoveNodeCommand(UndoCommand):
    def __init__(self, scheme, node, parent_node, parent=None):
        # type: (Workflow, Node, MetaNode, Optional[UndoCommand]) -> None
        super().__init__("Remove %s" % node.title, parent=parent)
        self.scheme = scheme
        self.node = node
        self.parent_node = parent_node
        self._index = -1
        ilinks, imacro = input_links(node)
        olinks, omacro = output_links(node)
        for link in ilinks + olinks:
            RemoveLinkCommand(scheme, link, parent_node, parent=self)
        for link in imacro + omacro:
            RemoveLinkCommand(scheme, link, parent_node.parent_node(), parent=self)

    def redo(self):
        # redo child commands
        super().redo()
        self._index = self.parent_node.nodes().index(self.node)
        self.scheme.remove_node(self.node)

    def undo(self):
        assert self._index != -1
        self.scheme.insert_node(self._index, self.node, self.parent_node)
        # Undo child commands
        super().undo()


class AddLinkCommand(UndoCommand):
    def __init__(self, scheme, link, parent_node, parent=None):
        # type: (Workflow, Link, MetaNode, Optional[UndoCommand]) -> None
        super().__init__("Add link", parent)
        self.scheme = scheme
        self.link = link
        self.parent_node = parent_node

    def redo(self):
        self.scheme.add_link(self.link, self.parent_node)

    def undo(self):
        self.scheme.remove_link(self.link)


class RemoveLinkCommand(UndoCommand):
    def __init__(self, scheme, link, parent_node, parent=None):
        # type: (Workflow, Link, MetaNode, Optional[UndoCommand]) -> None
        super().__init__("Remove link", parent)
        self.scheme = scheme
        self.link = link
        self.parent_node = parent_node
        self._index = -1

    def redo(self):
        self._index = self.parent_node.links().index(self.link)
        self.scheme.remove_link(self.link)

    def undo(self):
        assert self._index != -1
        self.scheme.insert_link(self._index, self.link, self.parent_node)
        self._index = -1


class InsertNodeCommand(UndoCommand):
    def __init__(
            self,
            scheme: Workflow,
            new_node: Node,
            old_link: Link,
            new_links: Tuple[Link, Link],
            parent_node: MetaNode,
            parent: Optional[UndoCommand] = None,
    ) -> None:
        super().__init__("Insert widget into link", parent=parent)
        AddNodeCommand(scheme, new_node, parent_node, parent=self)
        RemoveLinkCommand(scheme, old_link, parent_node, parent=self)
        for link in new_links:
            AddLinkCommand(scheme, link, parent_node, parent=self)


class AddAnnotationCommand(UndoCommand):
    def __init__(self, scheme, annotation, parent_node, parent=None):
        # type: (Workflow, Annotation, MetaNode, Optional[UndoCommand]) -> None
        super().__init__("Add annotation", parent)
        self.scheme = scheme
        self.annotation = annotation
        self.parent_node = parent_node

    def redo(self):
        self.scheme.add_annotation(self.annotation, self.parent_node)

    def undo(self):
        self.scheme.remove_annotation(self.annotation)


class RemoveAnnotationCommand(UndoCommand):
    def __init__(self, scheme, annotation, parent_node, parent=None):
        # type: (Workflow, Annotation, MetaNode, Optional[UndoCommand]) -> None
        super().__init__("Remove annotation", parent)
        self.scheme = scheme
        self.annotation = annotation
        self.parent_node = parent_node
        self._index = -1

    def redo(self):
        self._index = self.parent_node.annotations().index(self.annotation)
        self.scheme.remove_annotation(self.annotation)

    def undo(self):
        assert self._index != -1
        self.scheme.insert_annotation(self._index, self.annotation, self.parent_node)
        self._index = -1


class MoveNodeCommand(UndoCommand):
    def __init__(self, scheme, node, old, new, parent=None):
        # type: (Workflow, Node, Pos, Pos, Optional[UndoCommand]) -> None
        super().__init__("Move", parent)
        self.scheme = scheme
        self.node = node
        self.old = old
        self.new = new

    def redo(self):
        self.node.position = self.new

    def undo(self):
        self.node.position = self.old


class ResizeCommand(UndoCommand):
    def __init__(self, scheme, item, new_geom, parent=None):
        # type: (Workflow, Text, Rect, Optional[UndoCommand]) -> None
        super().__init__("Resize", parent)
        self.scheme = scheme
        self.item = item
        self.new_geom = new_geom
        self.old_geom = item.rect

    def redo(self):
        self.item.rect = self.new_geom

    def undo(self):
        self.item.rect = self.old_geom


class ArrowChangeCommand(UndoCommand):
    def __init__(self, scheme, item, new_line, parent=None):
        # type: (Workflow, Arrow, Line, Optional[UndoCommand]) -> None
        super().__init__("Move arrow", parent)
        self.scheme = scheme
        self.item = item
        self.new_line = new_line
        self.old_line = (item.start_pos, item.end_pos)

    def redo(self):
        self.item.set_line(*self.new_line)

    def undo(self):
        self.item.set_line(*self.old_line)


class AnnotationGeometryChange(UndoCommand):
    def __init__(
            self,
            scheme,  # type: Workflow
            annotation,  # type: Annotation
            old,  # type: Any
            new,  # type: Any
            parent=None  # type: Optional[UndoCommand]
    ):  # type: (...) -> None
        super().__init__("Change Annotation Geometry", parent)
        self.scheme = scheme
        self.annotation = annotation
        self.old = old
        self.new = new

    def redo(self):
        self.annotation.geometry = self.new  # type: ignore

    def undo(self):
        self.annotation.geometry = self.old  # type: ignore


class RenameNodeCommand(UndoCommand):
    def __init__(self, scheme, node, old_name, new_name, parent=None):
        # type: (Workflow, Node, str, str, Optional[UndoCommand]) -> None
        super().__init__("Rename", parent)
        self.scheme = scheme
        self.node = node
        self.old_name = old_name
        self.new_name = new_name

    def redo(self):
        self.node.set_title(self.new_name)

    def undo(self):
        self.node.set_title(self.old_name)


class TextChangeCommand(UndoCommand):
    def __init__(
            self,
            scheme,       # type: Workflow
            annotation,   # type: Text
            old_content,  # type: str
            old_content_type,  # type: str
            new_content,  # type: str
            new_content_type,  # type: str
            parent=None   # type: Optional[UndoCommand]
    ):  # type: (...) -> None
        super().__init__("Change text", parent)
        self.scheme = scheme
        self.annotation = annotation
        self.old_content = old_content
        self.old_content_type = old_content_type
        self.new_content = new_content
        self.new_content_type = new_content_type

    def redo(self):
        self.annotation.set_content(self.new_content, self.new_content_type)

    def undo(self):
        self.annotation.set_content(self.old_content, self.old_content_type)


class SetAttrCommand(UndoCommand):
    def __init__(
            self,
            obj,         # type: Any
            attrname,    # type: str
            newvalue,    # type: Any
            name=None,   # type: Optional[str]
            parent=None  # type: Optional[UndoCommand]
    ):  # type: (...) -> None
        if name is None:
            name = "Set %r" % attrname
        super().__init__(name, parent)
        self.obj = obj
        self.attrname = attrname
        self.newvalue = newvalue
        self.oldvalue = getattr(obj, attrname)

    def redo(self):
        setattr(self.obj, self.attrname, self.newvalue)

    def undo(self):
        setattr(self.obj, self.attrname, self.oldvalue)


class SetWindowGroupPresets(UndoCommand):
    def __init__(
            self,
            scheme: 'Workflow',
            presets: List['Workflow.WindowGroup'],
            parent: Optional[UndoCommand] = None,
            **kwargs
    ) -> None:
        text = kwargs.pop("text", "Set Window Presets")
        super().__init__(text, parent, **kwargs)
        self.scheme = scheme
        self.presets = presets
        self.__undo_presets = None

    def redo(self):
        presets = self.scheme.window_group_presets()
        self.scheme.set_window_group_presets(self.presets)
        self.__undo_presets = presets

    def undo(self):
        self.scheme.set_window_group_presets(self.__undo_presets)
        self.__undo_presets = None


class SimpleUndoCommand(UndoCommand):
    """
    Simple undo/redo command specified by callable function pair.
    Parameters
    ----------
    redo: Callable[[], None]
        A function expressing a redo action.
    undo : Callable[[], None]
        A function expressing a undo action.
    text : str
        The command's text (see `UndoCommand.setText`)
    parent : Optional[UndoCommand]
    """

    def __init__(
            self,
            redo,  # type: Callable[[], None]
            undo,  # type: Callable[[], None]
            text,  # type: str
            parent=None  # type: Optional[UndoCommand]
    ):  # type: (...) -> None
        super().__init__(text, parent)
        self._redo = redo
        self._undo = undo

    def undo(self):
        # type: () -> None
        """Reimplemented."""
        self._undo()

    def redo(self):
        # type: () -> None
        """Reimplemented."""
        self._redo()

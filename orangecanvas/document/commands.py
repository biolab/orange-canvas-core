"""
Undo/Redo Commands

"""
import typing
from typing import Callable, Optional, Tuple, List, Any

from AnyQt.QtWidgets import QUndoCommand

if typing.TYPE_CHECKING:
    from ..scheme import (
        Scheme, SchemeNode, SchemeLink, BaseSchemeAnnotation,
        SchemeTextAnnotation, SchemeArrowAnnotation
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
        for child in state['_UndoCommand__children']:
            child.__setstate__(self.__child_states[child])

        self.__dict__ = {k: v for k, v in state.items()}

    @staticmethod
    def from_QUndoCommand(qc: QUndoCommand, parent=None):
        if type(qc) == QUndoCommand:
            qc.__class__ = UndoCommand
            qc.__initialized = True

        qc.__parent = parent

        children = [qc.child(i) for i in range(qc.childCount())]
        for child in children:
            UndoCommand.from_QUndoCommand(child, parent=qc)

        return qc


class AddNodeCommand(UndoCommand):
    def __init__(self, scheme, node, parent=None):
        # type: (Scheme, SchemeNode, Optional[UndoCommand]) -> None
        super().__init__("Add %s" % node.title, parent)
        self.scheme = scheme
        self.node = node

    def redo(self):
        self.scheme.add_node(self.node)

    def undo(self):
        self.scheme.remove_node(self.node)


class RemoveNodeCommand(UndoCommand):
    def __init__(self, scheme, node, parent=None):
        # type: (Scheme, SchemeNode, Optional[UndoCommand]) -> None
        super().__init__("Remove %s" % node.title, parent)
        self.scheme = scheme
        self.node = node
        self._index = -1
        links = scheme.input_links(self.node) + \
                scheme.output_links(self.node)

        for link in links:
            RemoveLinkCommand(scheme, link, parent=self)

    def redo(self):
        # redo child commands
        super().redo()
        self._index = self.scheme.nodes.index(self.node)
        self.scheme.remove_node(self.node)

    def undo(self):
        assert self._index != -1
        self.scheme.insert_node(self._index, self.node)
        # Undo child commands
        super().undo()


class AddLinkCommand(UndoCommand):
    def __init__(self, scheme, link, parent=None):
        # type: (Scheme, SchemeLink, Optional[UndoCommand]) -> None
        super().__init__("Add link", parent)
        self.scheme = scheme
        self.link = link

    def redo(self):
        self.scheme.add_link(self.link)

    def undo(self):
        self.scheme.remove_link(self.link)


class RemoveLinkCommand(UndoCommand):
    def __init__(self, scheme, link, parent=None):
        # type: (Scheme, SchemeLink, Optional[UndoCommand]) -> None
        super().__init__("Remove link", parent)
        self.scheme = scheme
        self.link = link
        self._index = -1

    def redo(self):
        self._index = self.scheme.links.index(self.link)
        self.scheme.remove_link(self.link)

    def undo(self):
        assert self._index != -1
        self.scheme.insert_link(self._index, self.link)
        self._index = -1


class InsertNodeCommand(UndoCommand):
    def __init__(
            self,
            scheme,     # type: Scheme
            new_node,   # type: SchemeNode
            old_link,   # type: SchemeLink
            new_links,  # type: Tuple[SchemeLink, SchemeLink]
            parent=None # type: Optional[UndoCommand]
    ):  # type: (...) -> None
        super().__init__("Insert widget into link", parent)

        AddNodeCommand(scheme, new_node, parent=self)
        RemoveLinkCommand(scheme, old_link, parent=self)
        for link in new_links:
            AddLinkCommand(scheme, link, parent=self)


class AddAnnotationCommand(UndoCommand):
    def __init__(self, scheme, annotation, parent=None):
        # type: (Scheme, BaseSchemeAnnotation, Optional[UndoCommand]) -> None
        super().__init__("Add annotation", parent)
        self.scheme = scheme
        self.annotation = annotation

    def redo(self):
        self.scheme.add_annotation(self.annotation)

    def undo(self):
        self.scheme.remove_annotation(self.annotation)


class RemoveAnnotationCommand(UndoCommand):
    def __init__(self, scheme, annotation, parent=None):
        # type: (Scheme, BaseSchemeAnnotation, Optional[UndoCommand]) -> None
        super().__init__("Remove annotation", parent)
        self.scheme = scheme
        self.annotation = annotation
        self._index = -1

    def redo(self):
        self._index = self.scheme.annotations.index(self.annotation)
        self.scheme.remove_annotation(self.annotation)

    def undo(self):
        assert self._index != -1
        self.scheme.insert_annotation(self._index, self.annotation)
        self._index = -1


class MoveNodeCommand(UndoCommand):
    def __init__(self, scheme, node, old, new, parent=None):
        # type: (Scheme, SchemeNode, Pos, Pos, Optional[UndoCommand]) -> None
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
        # type: (Scheme, SchemeTextAnnotation, Rect, Optional[UndoCommand]) -> None
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
        # type: (Scheme, SchemeArrowAnnotation, Line, Optional[UndoCommand]) -> None
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
            scheme,  # type: Scheme
            annotation,  # type: BaseSchemeAnnotation
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
        # type: (Scheme, SchemeNode, str, str, Optional[UndoCommand]) -> None
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
            scheme,       # type: Scheme
            annotation,   # type: SchemeTextAnnotation
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
            scheme: 'Scheme',
            presets: List['Scheme.WindowGroup'],
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

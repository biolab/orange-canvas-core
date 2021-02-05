"""
=====================
Canvas Graphics Scene
=====================

"""
import typing
from typing import Dict, List, Optional, Any, Type, Tuple, Union

import logging
import itertools

from operator import attrgetter

from xml.sax.saxutils import escape

from AnyQt.QtWidgets import QGraphicsScene, QGraphicsItem
from AnyQt.QtGui import QPainter, QColor, QFont
from AnyQt.QtCore import (
    Qt, QPointF, QRectF, QSizeF, QLineF, QBuffer, QObject, QSignalMapper,
    QParallelAnimationGroup, QT_VERSION
)
from AnyQt.QtSvg import QSvgGenerator
from AnyQt.QtCore import pyqtSignal as Signal

from ..registry import (
    WidgetRegistry, WidgetDescription, CategoryDescription,
    InputSignal, OutputSignal
)
from .. import scheme
from ..scheme import Scheme, SchemeNode, SchemeLink, BaseSchemeAnnotation
from . import items
from .items import NodeItem, LinkItem
from .items.annotationitem import Annotation

from .layout import AnchorLayout

if typing.TYPE_CHECKING:
    from ..document.interactions import UserInteraction
    T = typing.TypeVar("T", bound=QGraphicsItem)


__all__ = [
    "CanvasScene", "grab_svg"
]

log = logging.getLogger(__name__)


class CanvasScene(QGraphicsScene):
    """
    A Graphics Scene for displaying an :class:`~.scheme.Scheme` instance.
    """

    #: Signal emitted when a :class:`NodeItem` has been added to the scene.
    node_item_added = Signal(object)

    #: Signal emitted when a :class:`NodeItem` has been removed from the
    #: scene.
    node_item_removed = Signal(object)

    #: Signal emitted when a new :class:`LinkItem` has been added to the
    #: scene.
    link_item_added = Signal(object)

    #: Signal emitted when a :class:`LinkItem` has been removed.
    link_item_removed = Signal(object)

    #: Signal emitted when a :class:`Annotation` item has been added.
    annotation_added = Signal(object)

    #: Signal emitted when a :class:`Annotation` item has been removed.
    annotation_removed = Signal(object)

    #: Signal emitted when the position of a :class:`NodeItem` has changed.
    node_item_position_changed = Signal(object, QPointF)

    #: Signal emitted when an :class:`NodeItem` has been double clicked.
    node_item_double_clicked = Signal(object)

    #: An node item has been activated (double-clicked)
    node_item_activated = Signal(object)

    #: An node item has been hovered
    node_item_hovered = Signal(object)

    #: Link item has been activated (double-clicked)
    link_item_activated = Signal(object)

    #: Link item has been hovered
    link_item_hovered = Signal(object)

    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None
        super().__init__(*args, **kwargs)

        self.scheme = None    # type: Optional[Scheme]
        self.registry = None  # type: Optional[WidgetRegistry]

        # All node items
        self.__node_items = []  # type: List[NodeItem]
        # Mapping from SchemeNodes to canvas items
        self.__item_for_node = {}  # type: Dict[SchemeNode, NodeItem]
        # All link items
        self.__link_items = []  # type: List[LinkItem]
        # Mapping from SchemeLinks to canvas items.
        self.__item_for_link = {}  # type: Dict[SchemeLink, LinkItem]

        # All annotation items
        self.__annotation_items = []  # type: List[Annotation]
        # Mapping from SchemeAnnotations to canvas items.
        self.__item_for_annotation = {}  # type: Dict[BaseSchemeAnnotation, Annotation]

        # Is the scene editable
        self.editable = True

        # Anchor Layout
        self.__anchor_layout = AnchorLayout()
        self.addItem(self.__anchor_layout)

        self.__channel_names_visible = True
        self.__node_animation_enabled = True
        self.__animations_temporarily_disabled = False

        self.user_interaction_handler = None  # type: Optional[UserInteraction]

        self.activated_mapper = QSignalMapper(self)
        self.activated_mapper.mapped[QObject].connect(
            lambda node: self.node_item_activated.emit(node)
        )
        self.hovered_mapper = QSignalMapper(self)
        self.hovered_mapper.mapped[QObject].connect(
            lambda node: self.node_item_hovered.emit(node)
        )
        self.position_change_mapper = QSignalMapper(self)
        self.position_change_mapper.mapped[QObject].connect(
            self._on_position_change
        )
        self.link_activated_mapper = QSignalMapper(self)
        self.link_activated_mapper.mapped[QObject].connect(
            lambda node: self.link_item_activated.emit(node)
        )

        self.__anchors_opened = False

    def clear_scene(self):  # type: () -> None
        """
        Clear (reset) the scene.
        """
        if self.scheme is not None:
            self.scheme.node_added.disconnect(self.add_node)
            self.scheme.node_removed.disconnect(self.remove_node)

            self.scheme.link_added.disconnect(self.add_link)
            self.scheme.link_removed.disconnect(self.remove_link)

            self.scheme.annotation_added.disconnect(self.add_annotation)
            self.scheme.annotation_removed.disconnect(self.remove_annotation)

            # Remove all items to make sure all signals from scheme items
            # to canvas items are disconnected.

            for annot in self.scheme.annotations:
                if annot in self.__item_for_annotation:
                    self.remove_annotation(annot)

            for link in self.scheme.links:
                if link in self.__item_for_link:
                    self.remove_link(link)

            for node in self.scheme.nodes:
                if node in self.__item_for_node:
                    self.remove_node(node)

        self.scheme = None
        self.__node_items = []
        self.__item_for_node = {}
        self.__link_items = []
        self.__item_for_link = {}
        self.__annotation_items = []
        self.__item_for_annotation = {}

        self.__anchor_layout.deleteLater()

        self.user_interaction_handler = None

        self.clear()

    def set_scheme(self, scheme):
        # type: (Scheme) -> None
        """
        Set the scheme to display. Populates the scene with nodes and links
        already in the scheme. Any further change to the scheme will be
        reflected in the scene.

        Parameters
        ----------
        scheme : :class:`~.scheme.Scheme`

        """
        if self.scheme is not None:
            # Clear the old scheme
            self.clear_scene()

        self.scheme = scheme
        if self.scheme is not None:
            self.scheme.node_added.connect(self.add_node)
            self.scheme.node_removed.connect(self.remove_node)

            self.scheme.link_added.connect(self.add_link)
            self.scheme.link_removed.connect(self.remove_link)

            self.scheme.annotation_added.connect(self.add_annotation)
            self.scheme.annotation_removed.connect(self.remove_annotation)

        for node in scheme.nodes:
            self.add_node(node)

        for link in scheme.links:
            self.add_link(link)

        for annot in scheme.annotations:
            self.add_annotation(annot)

        self.__anchor_layout.activate()

    def set_registry(self, registry):
        # type: (WidgetRegistry) -> None
        """
        Set the widget registry.
        """
        # TODO: Remove/Deprecate. Is used only to get the category/background
        # color. That should be part of the SchemeNode/WidgetDescription.
        self.registry = registry

    def set_anchor_layout(self, layout):
        """
        Set an :class:`~.layout.AnchorLayout`
        """
        if self.__anchor_layout != layout:
            if self.__anchor_layout:
                self.__anchor_layout.deleteLater()
                self.__anchor_layout = None

            self.__anchor_layout = layout

    def anchor_layout(self):
        """
        Return the anchor layout instance.
        """
        return self.__anchor_layout

    def set_channel_names_visible(self, visible):
        # type: (bool) -> None
        """
        Set the channel names visibility.
        """
        self.__channel_names_visible = visible
        for link in self.__link_items:
            link.setChannelNamesVisible(visible)

    def channel_names_visible(self):
        # type: () -> bool
        """
        Return the channel names visibility state.
        """
        return self.__channel_names_visible

    def set_node_animation_enabled(self, enabled):
        # type: (bool) -> None
        """
        Set node animation enabled state.
        """
        if self.__node_animation_enabled != enabled:
            self.__node_animation_enabled = enabled

            for node in self.__node_items:
                node.setAnimationEnabled(enabled)

            for link in self.__link_items:
                link.setAnimationEnabled(enabled)

    def add_node_item(self, item):
        # type: (NodeItem) -> NodeItem
        """
        Add a :class:`.NodeItem` instance to the scene.
        """
        if item in self.__node_items:
            raise ValueError("%r is already in the scene." % item)

        if item.pos().isNull():
            if self.__node_items:
                pos = self.__node_items[-1].pos() + QPointF(150, 0)
            else:
                pos = QPointF(150, 150)

            item.setPos(pos)

        item.setFont(self.font())

        # Set signal mappings
        self.activated_mapper.setMapping(item, item)
        item.activated.connect(self.activated_mapper.map)

        self.hovered_mapper.setMapping(item, item)
        item.hovered.connect(self.hovered_mapper.map)

        self.position_change_mapper.setMapping(item, item)
        item.positionChanged.connect(self.position_change_mapper.map)

        self.addItem(item)

        self.__node_items.append(item)

        self.clearSelection()
        item.setSelected(True)

        self.node_item_added.emit(item)

        return item

    def add_node(self, node):
        # type: (SchemeNode) -> NodeItem
        """
        Add and return a default constructed :class:`.NodeItem` for a
        :class:`SchemeNode` instance `node`. If the `node` is already in
        the scene do nothing and just return its item.

        """
        if node in self.__item_for_node:
            # Already added
            return self.__item_for_node[node]

        item = self.new_node_item(node.description)

        if node.position:
            pos = QPointF(*node.position)
            item.setPos(pos)

        item.setTitle(node.title)
        item.setProcessingState(node.processing_state)
        item.setProgress(node.progress)

        for message in node.state_messages():
            item.setStateMessage(message)

        item.setStatusMessage(node.status_message())

        self.__item_for_node[node] = item

        node.position_changed.connect(self.__on_node_pos_changed)
        node.title_changed.connect(item.setTitle)
        node.progress_changed.connect(item.setProgress)
        node.processing_state_changed.connect(item.setProcessingState)
        node.state_message_changed.connect(item.setStateMessage)
        node.status_message_changed.connect(item.setStatusMessage)

        return self.add_node_item(item)

    def new_node_item(self, widget_desc, category_desc=None):
        # type: (WidgetDescription, Optional[CategoryDescription]) -> NodeItem
        """
        Construct an new :class:`.NodeItem` from a `WidgetDescription`.
        Optionally also set `CategoryDescription`.

        """
        item = items.NodeItem()
        item.setWidgetDescription(widget_desc)

        if category_desc is None and self.registry and widget_desc.category:
            category_desc = self.registry.category(widget_desc.category)

        if category_desc is None and self.registry is not None:
            try:
                category_desc = self.registry.category(widget_desc.category)
            except KeyError:
                pass

        if category_desc is not None:
            item.setWidgetCategory(category_desc)

        item.setAnimationEnabled(self.__node_animation_enabled)
        return item

    def remove_node_item(self, item):
        # type: (NodeItem) -> None
        """
        Remove `item` (:class:`.NodeItem`) from the scene.
        """
        desc = item.widget_description

        self.activated_mapper.removeMappings(item)
        self.hovered_mapper.removeMappings(item)
        self.position_change_mapper.removeMappings(item)
        self.link_activated_mapper.removeMappings(item)

        item.hide()
        self.removeItem(item)
        self.__node_items.remove(item)

        self.node_item_removed.emit(item)

    def remove_node(self, node):
        # type: (SchemeNode) -> None
        """
        Remove the :class:`.NodeItem` instance that was previously
        constructed for a :class:`SchemeNode` `node` using the `add_node`
        method.

        """
        item = self.__item_for_node.pop(node)

        node.position_changed.disconnect(self.__on_node_pos_changed)
        node.title_changed.disconnect(item.setTitle)
        node.progress_changed.disconnect(item.setProgress)
        node.processing_state_changed.disconnect(item.setProcessingState)
        node.state_message_changed.disconnect(item.setStateMessage)

        self.remove_node_item(item)

    def node_items(self):
        # type: () -> List[NodeItem]
        """
        Return all :class:`.NodeItem` instances in the scene.
        """
        return list(self.__node_items)

    def add_link_item(self, item):
        # type: (LinkItem) -> LinkItem
        """
        Add a link (:class:`.LinkItem`) to the scene.
        """
        self.link_activated_mapper.setMapping(item, item)
        item.activated.connect(self.link_activated_mapper.map)

        if item.scene() is not self:
            self.addItem(item)

        item.setFont(self.font())
        self.__link_items.append(item)

        self.link_item_added.emit(item)

        self.__anchor_layout.invalidateLink(item)

        return item

    def add_link(self, scheme_link):
        # type: (SchemeLink) -> LinkItem
        """
        Create and add a :class:`.LinkItem` instance for a
        :class:`SchemeLink` instance. If the link is already in the scene
        do nothing and just return its :class:`.LinkItem`.

        """
        if scheme_link in self.__item_for_link:
            return self.__item_for_link[scheme_link]

        source = self.__item_for_node[scheme_link.source_node]
        sink = self.__item_for_node[scheme_link.sink_node]

        item = self.new_link_item(source, scheme_link.source_channel,
                                  sink, scheme_link.sink_channel)

        item.setEnabled(scheme_link.is_enabled())
        scheme_link.enabled_changed.connect(item.setEnabled)

        if scheme_link.is_dynamic():
            item.setDynamic(True)
            item.setDynamicEnabled(scheme_link.is_dynamic_enabled())
            scheme_link.dynamic_enabled_changed.connect(item.setDynamicEnabled)

        item.setRuntimeState(scheme_link.runtime_state())
        scheme_link.state_changed.connect(item.setRuntimeState)

        self.add_link_item(item)
        self.__item_for_link[scheme_link] = item
        return item

    def new_link_item(self, source_item, source_channel,
                      sink_item, sink_channel):
        # type: (NodeItem, OutputSignal, NodeItem, InputSignal) -> LinkItem
        """
        Construct and return a new :class:`.LinkItem`
        """
        item = items.LinkItem()
        item.setSourceItem(source_item, source_channel)
        item.setSinkItem(sink_item, sink_channel)

        def channel_name(channel):
            # type: (Union[OutputSignal, InputSignal, str]) -> str
            if isinstance(channel, str):
                return channel
            else:
                return channel.name

        source_name = channel_name(source_channel)
        sink_name = channel_name(sink_channel)

        fmt = "<b>{0}</b>&nbsp; \u2192 &nbsp;<b>{1}</b>"

        item.setSourceName(source_name)
        item.setSinkName(sink_name)
        item.setChannelNamesVisible(self.__channel_names_visible)

        item.setAnimationEnabled(self.__node_animation_enabled)

        return item

    def remove_link_item(self, item):
        # type: (LinkItem) -> LinkItem
        """
        Remove a link (:class:`.LinkItem`) from the scene.
        """
        # Invalidate the anchor layout.
        self.__anchor_layout.invalidateLink(item)
        self.__link_items.remove(item)

        # Remove the anchor points.
        item.removeLink()
        self.removeItem(item)

        self.link_item_removed.emit(item)
        return item

    def remove_link(self, scheme_link):
        # type: (SchemeLink) -> None
        """
        Remove a :class:`.LinkItem` instance that was previously constructed
        for a :class:`SchemeLink` instance `link` using the `add_link` method.

        """
        item = self.__item_for_link.pop(scheme_link)
        scheme_link.enabled_changed.disconnect(item.setEnabled)

        if scheme_link.is_dynamic():
            scheme_link.dynamic_enabled_changed.disconnect(
                item.setDynamicEnabled
            )
        scheme_link.state_changed.disconnect(item.setRuntimeState)
        self.remove_link_item(item)

    def link_items(self):
        # type: () -> List[LinkItem]
        """
        Return all :class:`.LinkItem` s in the scene.
        """
        return list(self.__link_items)

    def add_annotation_item(self, annotation):
        # type: (Annotation) -> Annotation
        """
        Add an :class:`.Annotation` item to the scene.
        """
        self.__annotation_items.append(annotation)
        self.addItem(annotation)
        self.annotation_added.emit(annotation)
        return annotation

    def add_annotation(self, scheme_annot):
        # type: (BaseSchemeAnnotation) -> Annotation
        """
        Create a new item for :class:`SchemeAnnotation` and add it
        to the scene. If the `scheme_annot` is already in the scene do
        nothing and just return its item.

        """
        if scheme_annot in self.__item_for_annotation:
            # Already added
            return self.__item_for_annotation[scheme_annot]

        if isinstance(scheme_annot, scheme.SchemeTextAnnotation):
            item = items.TextAnnotation()
            x, y, w, h = scheme_annot.rect
            item.setPos(x, y)
            item.resize(w, h)
            item.setTextInteractionFlags(Qt.TextEditorInteraction)

            font = font_from_dict(scheme_annot.font, item.font())
            item.setFont(font)
            item.setContent(scheme_annot.content, scheme_annot.content_type)
            scheme_annot.content_changed.connect(item.setContent)
        elif isinstance(scheme_annot, scheme.SchemeArrowAnnotation):
            item = items.ArrowAnnotation()
            start, end = scheme_annot.start_pos, scheme_annot.end_pos
            item.setLine(QLineF(QPointF(*start), QPointF(*end)))
            item.setColor(QColor(scheme_annot.color))

        scheme_annot.geometry_changed.connect(
            self.__on_scheme_annot_geometry_change
        )

        self.add_annotation_item(item)
        self.__item_for_annotation[scheme_annot] = item

        return item

    def remove_annotation_item(self, annotation):
        # type: (Annotation) -> None
        """
        Remove an :class:`.Annotation` instance from the scene.

        """
        self.__annotation_items.remove(annotation)
        self.removeItem(annotation)
        self.annotation_removed.emit(annotation)

    def remove_annotation(self, scheme_annotation):
        # type: (BaseSchemeAnnotation) -> None
        """
        Remove an :class:`.Annotation` instance that was previously added
        using :func:`add_anotation`.

        """
        item = self.__item_for_annotation.pop(scheme_annotation)

        scheme_annotation.geometry_changed.disconnect(
            self.__on_scheme_annot_geometry_change
        )

        if isinstance(scheme_annotation, scheme.SchemeTextAnnotation):
            scheme_annotation.content_changed.disconnect(item.setContent)
        self.remove_annotation_item(item)

    def annotation_items(self):
        # type: () -> List[Annotation]
        """
        Return all :class:`.Annotation` items in the scene.
        """
        return self.__annotation_items.copy()

    def item_for_annotation(self, scheme_annotation):
        # type: (BaseSchemeAnnotation) -> Annotation
        return self.__item_for_annotation[scheme_annotation]

    def annotation_for_item(self, item):
        # type: (Annotation) -> BaseSchemeAnnotation
        rev = {v: k for k, v in self.__item_for_annotation.items()}
        return rev[item]

    def commit_scheme_node(self, node):
        """
        Commit the `node` into the scheme.
        """
        if not self.editable:
            raise Exception("Scheme not editable.")

        if node not in self.__item_for_node:
            raise ValueError("No 'NodeItem' for node.")

        item = self.__item_for_node[node]

        try:
            self.scheme.add_node(node)
        except Exception:
            log.error("An error occurred while committing node '%s'",
                      node, exc_info=True)
            # Cleanup (remove the node item)
            self.remove_node_item(item)
            raise

        log.debug("Commited node '%s' from '%s' to '%s'" % \
                  (node, self, self.scheme))

    def commit_scheme_link(self, link):
        """
        Commit a scheme link.
        """
        if not self.editable:
            raise Exception("Scheme not editable")

        if link not in self.__item_for_link:
            raise ValueError("No 'LinkItem' for link.")

        self.scheme.add_link(link)
        log.debug("Commited link '%s' from '%s' to '%s'" % \
                  (link, self, self.scheme))

    def node_for_item(self, item):
        # type: (NodeItem) -> SchemeNode
        """
        Return the `SchemeNode` for the `item`.
        """
        rev = dict([(v, k) for k, v in self.__item_for_node.items()])
        return rev[item]

    def item_for_node(self, node):
        # type: (SchemeNode) -> NodeItem
        """
        Return the :class:`NodeItem` instance for a :class:`SchemeNode`.
        """
        return self.__item_for_node[node]

    def link_for_item(self, item):
        # type: (LinkItem) -> SchemeLink
        """
        Return the `SchemeLink for `item` (:class:`LinkItem`).
        """
        rev = dict([(v, k) for k, v in self.__item_for_link.items()])
        return rev[item]

    def item_for_link(self, link):
        # type: (SchemeLink) -> LinkItem
        """
        Return the :class:`LinkItem` for a :class:`SchemeLink`
        """
        return self.__item_for_link[link]

    def selected_node_items(self):
        # type: () -> List[NodeItem]
        """
        Return the selected :class:`NodeItem`'s.
        """
        return [item for item in self.__node_items if item.isSelected()]

    def selected_link_items(self):
        # type: () -> List[LinkItem]
        return [item for item in self.__link_items if item.isSelected()]

    def selected_annotation_items(self):
        # type: () -> List[Annotation]
        """
        Return the selected :class:`Annotation`'s
        """
        return [item for item in self.__annotation_items if item.isSelected()]

    def node_links(self, node_item):
        # type: (NodeItem) -> List[LinkItem]
        """
        Return all links from the `node_item` (:class:`NodeItem`).
        """
        return self.node_output_links(node_item) + \
               self.node_input_links(node_item)

    def node_output_links(self, node_item):
        # type: (NodeItem) -> List[LinkItem]
        """
        Return a list of all output links from `node_item`.
        """
        return [link for link in self.__link_items
                if link.sourceItem == node_item]

    def node_input_links(self, node_item):
        # type: (NodeItem) -> List[LinkItem]
        """
        Return a list of all input links for `node_item`.
        """
        return [link for link in self.__link_items
                if link.sinkItem == node_item]

    def neighbor_nodes(self, node_item):
        # type: (NodeItem) -> List[NodeItem]
        """
        Return a list of `node_item`'s (class:`NodeItem`) neighbor nodes.
        """
        neighbors = list(map(attrgetter("sourceItem"),
                             self.node_input_links(node_item)))

        neighbors.extend(map(attrgetter("sinkItem"),
                             self.node_output_links(node_item)))
        return neighbors

    def set_widget_anchors_open(self, enabled):
        if self.__anchors_opened == enabled:
            return
        self.__anchors_opened = enabled

        for item in self.node_items():
            item.inputAnchorItem.setAnchorOpen(enabled)
            item.outputAnchorItem.setAnchorOpen(enabled)

    def _on_position_change(self, item):
        # type: (NodeItem) -> None
        # Invalidate the anchor point layout for the node and schedule a layout.
        self.__anchor_layout.invalidateNode(item)
        self.node_item_position_changed.emit(item, item.pos())

    def __on_node_pos_changed(self, pos):
        # type: (Tuple[float, float]) -> None
        node = self.sender()
        item = self.__item_for_node[node]
        item.setPos(*pos)

    def __on_scheme_annot_geometry_change(self):
        # type: () -> None
        annot = self.sender()
        item = self.__item_for_annotation[annot]
        if isinstance(annot, scheme.SchemeTextAnnotation):
            item.setGeometry(QRectF(*annot.rect))
        elif isinstance(annot, scheme.SchemeArrowAnnotation):
            p1 = item.mapFromScene(QPointF(*annot.start_pos))
            p2 = item.mapFromScene(QPointF(*annot.end_pos))
            item.setLine(QLineF(p1, p2))
        else:
            pass

    def item_at(self, pos, type_or_tuple=None, buttons=Qt.NoButton):
        # type: (QPointF, Optional[Type[T]], Qt.MouseButtons) -> Optional[T]
        """Return the item at `pos` that is an instance of the specified
        type (`type_or_tuple`). If `buttons` (`Qt.MouseButtons`) is given
        only return the item if it is the top level item that would
        accept any of the buttons (`QGraphicsItem.acceptedMouseButtons`).
        """
        rect = QRectF(pos, QSizeF(1, 1))
        items = self.items(rect)

        if buttons:
            items_iter = itertools.dropwhile(
                lambda item: not item.acceptedMouseButtons() & buttons,
                items
            )
            items = list(items_iter)[:1]

        if type_or_tuple:
            items = [i for i in items if isinstance(i, type_or_tuple)]

        return items[0] if items else None

    def mousePressEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.mousePressEvent(event):
            return

        # Right (context) click on the node item. If the widget is not
        # in the current selection then select the widget (only the widget).
        # Else simply return and let customContextMenuRequested signal
        # handle it
        shape_item = self.item_at(event.scenePos(), items.NodeItem)
        if shape_item and event.button() == Qt.RightButton and \
                shape_item.flags() & QGraphicsItem.ItemIsSelectable:
            if not shape_item.isSelected():
                self.clearSelection()
                shape_item.setSelected(True)

        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.mouseMoveEvent(event):
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.mouseReleaseEvent(event):
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.mouseDoubleClickEvent(event):
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.keyPressEvent(event):
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.keyReleaseEvent(event):
            return
        super().keyReleaseEvent(event)

    def contextMenuEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.contextMenuEvent(event):
            return
        super().contextMenuEvent(event)

    def set_user_interaction_handler(self, handler):
        # type: (UserInteraction) -> None
        if self.user_interaction_handler and \
                not self.user_interaction_handler.isFinished():
            self.user_interaction_handler.cancel()

        log.debug("Setting interaction '%s' to '%s'" % (handler, self))

        self.user_interaction_handler = handler
        if handler:
            if self.__node_animation_enabled:
                self.__animations_temporarily_disabled = True
                self.set_node_animation_enabled(False)
            handler.start()
        elif self.__animations_temporarily_disabled:
            self.__animations_temporarily_disabled = False
            self.set_node_animation_enabled(True)

    def __str__(self):
        return "%s(objectName=%r, ...)" % \
                (type(self).__name__, str(self.objectName()))


def font_from_dict(font_dict, font=None):
    # type: (dict, Optional[QFont]) -> QFont
    if font is None:
        font = QFont()
    else:
        font = QFont(font)

    if "family" in font_dict:
        font.setFamily(font_dict["family"])

    if "size" in font_dict:
        font.setPixelSize(font_dict["size"])

    return font


if QT_VERSION >= 0x50900 and \
      QSvgGenerator().metric(QSvgGenerator.PdmDevicePixelRatioScaled) == 1:
    # QTBUG-63159
    class _QSvgGenerator(QSvgGenerator):  # type: ignore
        def metric(self, metric):
            if metric == QSvgGenerator.PdmDevicePixelRatioScaled:
                return int(1 * QSvgGenerator.devicePixelRatioFScale())
            else:
                return super().metric(metric)

else:
    _QSvgGenerator = QSvgGenerator  # type: ignore


def grab_svg(scene):
    # type: (QGraphicsScene) -> str
    """
    Return a SVG rendering of the scene contents.

    Parameters
    ----------
    scene : :class:`CanvasScene`

    """
    svg_buffer = QBuffer()
    gen = _QSvgGenerator()
    gen.setOutputDevice(svg_buffer)

    items_rect = scene.itemsBoundingRect().adjusted(-10, -10, 10, 10)

    if items_rect.isNull():
        items_rect = QRectF(0, 0, 10, 10)

    width, height = items_rect.width(), items_rect.height()
    rect_ratio = float(width) / height

    # Keep a fixed aspect ratio.
    aspect_ratio = 1.618
    if rect_ratio > aspect_ratio:
        height = int(height * rect_ratio / aspect_ratio)
    else:
        width = int(width * aspect_ratio / rect_ratio)

    target_rect = QRectF(0, 0, width, height)
    source_rect = QRectF(0, 0, width, height)
    source_rect.moveCenter(items_rect.center())

    gen.setSize(target_rect.size().toSize())
    gen.setViewBox(target_rect)

    painter = QPainter(gen)

    # Draw background.
    painter.setPen(Qt.NoPen)
    painter.setBrush(scene.palette().base())
    painter.drawRect(target_rect)

    # Render the scene
    scene.render(painter, target_rect, source_rect)
    painter.end()

    buffer_str = bytes(svg_buffer.buffer())
    return buffer_str.decode("utf-8")

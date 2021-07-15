"""
=====================
Canvas Graphics Scene
=====================

"""
import typing
import warnings
from typing import Dict, List, Optional, Any, Type, Tuple, Union

import logging
import itertools
from xml.sax.saxutils import escape

from AnyQt.QtWidgets import QGraphicsScene, QGraphicsItem
from AnyQt.QtGui import QColor, QFont
from AnyQt.QtCore import (
    Qt, QPointF, QRectF, QSizeF, QLineF, QObject, QSignalMapper,
)
from AnyQt.QtCore import pyqtSignal as Signal

from ..registry import (
    WidgetRegistry, WidgetDescription, CategoryDescription,
    InputSignal, OutputSignal, NAMED_COLORS
)
from .. import scheme
from ..scheme import Scheme, Node, Link, Annotation, MetaNode, InputNode, OutputNode
from ..gui.scene import GraphicsScene, UserInteraction
from . import items
from .items import NodeItem, LinkItem
from .items.annotationitem import AnnotationItem

from .layout import AnchorLayout
from ..scheme.element import Element
from ..utils.qinvoke import connect_with_context as qconnect

if typing.TYPE_CHECKING:
    T = typing.TypeVar("T", bound=QGraphicsItem)


__all__ = [
    "CanvasScene",
]

log = logging.getLogger(__name__)


def Node_toolTipHelper(node: Node) -> str:
    """
    A helper function for constructing a standard tooltip for the `node`.
    """
    title = f"<b>{escape(node.title)}</b>"
    if node.input_channels():
        inputs = [f"<li>{escape(inp.name)}</li>" for inp in node.input_channels()]
        inputs = f'Inputs:<ul>{"".join(inputs)}</ul>'
    else:
        inputs = "No inputs"

    if node.output_channels():
        outputs = [f"<li>{escape(out.name)}</li>" for out in node.output_channels()]
        outputs = f'Outputs:<ul>{"".join(outputs)}</ul>'
    else:
        outputs = "No outputs"

    tooltip = "<hr/>".join([title, inputs, outputs])
    style = "ul { margin-top: 1px; margin-bottom: 1px; }"
    return f'<span><style type="text/css">\n{style}\n</style>{tooltip}</span>'


class ItemDelegate(QObject):
    def createGraphicsWidget(self, node: Node, scene: QGraphicsScene = None) -> NodeItem:
        item = items.NodeItem()
        item.setIcon(node.icon())
        item.setTitle(node.title)
        item.setPos(QPointF(*node.position))
        item.setProcessingState(node.processing_state)
        item.setProgress(node.progress)

        for message in node.state_messages():
            item.setStateMessage(message)

        item.setStatusMessage(node.status_message())
        c = qconnect(
            node.position_changed, item,
            lambda pos: item.setPos(QPointF(*pos)),
        )
        item.__disconnect = c.disconnect
        node.title_changed.connect(item.setTitle)
        node.progress_changed.connect(item.setProgress)
        node.processing_state_changed.connect(item.setProcessingState)
        node.state_message_changed.connect(item.setStateMessage)
        node.status_message_changed.connect(item.setStatusMessage)

        def update_io_channels():
            item.inputAnchorItem.setSignals(node.input_channels())
            item.inputAnchorItem.setVisible(bool(node.input_channels()))
            item.outputAnchorItem.setSignals(node.output_channels())
            item.outputAnchorItem.setVisible(bool(node.output_channels()))
            item.setToolTip(Node_toolTipHelper(node, ))
            if isinstance(node, InputNode):
                item.inputAnchorItem.setVisible(False)
            elif isinstance(node, OutputNode):
                item.outputAnchorItem.setVisible(False)

        node.input_channel_inserted.connect(update_io_channels)
        node.input_channel_removed.connect(update_io_channels)
        node.output_channel_inserted.connect(update_io_channels)
        node.output_channel_removed.connect(update_io_channels)
        update_io_channels()
        color = self.backgroundColor(node)
        if color.isValid():
            item.setColor(color)
        return item

    def backgroundColor(self, node: Node) -> QColor:
        desc = getattr(node, "description", None)
        if desc is not None:
            if desc.background:
                background = NAMED_COLORS.get(desc.background, desc.background)
                color = QColor(background)
                if color.isValid():
                    return color
        return QColor(152, 158, 160)

    def setGraphicsWidgetData(self, item: NodeItem, node: Node):
        pass

    def commitData(self, item, node: Node):
        pass

    def destroyGraphicsWidget(self, item: NodeItem, node: Node):
        item.__disconnect()
        node.title_changed.disconnect(item.setTitle)
        node.progress_changed.disconnect(item.setProgress)
        node.processing_state_changed.disconnect(item.setProcessingState)
        node.state_message_changed.disconnect(item.setStateMessage)
        node.status_message_changed.connect(item.setStatusMessage)
        item.deleteLater()


class CanvasScene(GraphicsScene):
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

    #: Signal emitted when a :class:`AnnotationItem` item has been added.
    annotation_added = Signal(object)

    #: Signal emitted when a :class:`AnnotationItem` item has been removed.
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
        self.root = None      # type: Optional[MetaNode]
        self.__registry = None  # type: Optional[WidgetRegistry]

        # All node items
        self.__node_items = []  # type: List[NodeItem]
        # Mapping from Nodes to canvas items
        self.__item_for_node = {}  # type: Dict[Node, NodeItem]
        # All link items
        self.__link_items = []  # type: List[LinkItem]
        # Mapping from SchemeLinks to canvas items.
        self.__item_for_link = {}  # type: Dict[Link, LinkItem]

        # All annotation items
        self.__annotation_items = []  # type: List[AnnotationItem]
        # Mapping from SchemeAnnotations to canvas items.
        self.__item_for_annotation = {}  # type: Dict[Annotation, AnnotationItem]

        # Anchor Layout
        self.__anchor_layout = AnchorLayout()
        self.addItem(self.__anchor_layout)

        self.__channel_names_visible = True
        self.__node_animation_enabled = True
        self.__animations_temporarily_disabled = False

        self.user_interaction_handler = None  # type: Optional[UserInteraction]

        self.activated_mapper = QSignalMapper(self)
        self.activated_mapper.mappedObject.connect(
            lambda node: self.node_item_activated.emit(node)
        )
        self.hovered_mapper = QSignalMapper(self)
        self.hovered_mapper.mappedObject.connect(
            lambda node: self.node_item_hovered.emit(node)
        )
        self.position_change_mapper = QSignalMapper(self)
        self.position_change_mapper.mappedObject.connect(
            self._on_position_change
        )
        self.link_activated_mapper = QSignalMapper(self)
        self.link_activated_mapper.mappedObject.connect(
            lambda node: self.link_item_activated.emit(node)
        )
        self.__anchors_opened = False

    def clear_scene(self):  # type: () -> None
        """
        Clear (reset) the scene.
        """
        if self.scheme is not None:
            self.scheme.node_added.disconnect(self.__on_node_added)
            self.scheme.node_removed.disconnect(self.__on_node_removed)

            self.scheme.link_added.disconnect(self.__on_link_added)
            self.scheme.link_removed.disconnect(self.__on_link_removed)

            self.scheme.annotation_added.disconnect(self.__on_annotation_added)
            self.scheme.annotation_removed.disconnect(self.__on_annotation_removed)

            # Remove all items to make sure all signals from scheme items
            # to canvas items are disconnected.

            for annot in self.root.annotations():
                if annot in self.__item_for_annotation:
                    self.remove_annotation(annot)

            for link in self.root.links():
                if link in self.__item_for_link:
                    self.remove_link(link)

            for node in self.root.nodes():
                if node in self.__item_for_node:
                    self.remove_node(node)

        self.scheme = None
        self.root = None
        self.__node_items = []
        self.__item_for_node = {}
        self.__link_items = []
        self.__item_for_link = {}
        self.__annotation_items = []
        self.__item_for_annotation = {}

        self.__anchor_layout.deleteLater()

        self.user_interaction_handler = None

        self.clear()

    def set_scheme(self, scheme: Scheme, root: MetaNode = None):
        """
        Set the scheme to display. Populates the scene with nodes and links
        already in the scheme. Any further change to the scheme will be
        reflected in the scene.

        Parameters
        ----------
        scheme: Scheme
        root: MetaNode
        """
        if self.scheme is not None:
            # Clear the old scheme
            self.clear_scene()
        root = root if root is not None else scheme.root()
        self.root = root
        self.scheme = scheme

        if self.scheme is not None:
            self.scheme.node_added.connect(self.__on_node_added)
            self.scheme.node_removed.connect(self.__on_node_removed)

            self.scheme.link_added.connect(self.__on_link_added)
            self.scheme.link_removed.connect(self.__on_link_removed)

            self.scheme.annotation_added.connect(self.__on_annotation_added)
            self.scheme.annotation_removed.connect(self.__on_annotation_removed)

        for node in root.nodes():
            self.add_node(node)

        for link in root.links():
            self.add_link(link)

        for annot in root.annotations():
            self.add_annotation(annot)

        self.__anchor_layout.activate()

    def set_registry(self, registry):
        # type: (WidgetRegistry) -> None
        """
        Set the widget registry.
        """
        warnings.warn(
            "`set_registry` is deprecated", DeprecationWarning, stacklevel=2
        )
        self.__registry = registry

    @property
    def registry(self):
        warnings.warn(
            '`registry` is deprecated', DeprecationWarning, stacklevel=2
        )
        return self.__registry

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

    def __on_node_added(self, node: Node, parent: MetaNode):
        if parent is self.root:
            self.add_node(node)

    def __on_node_removed(self, node: Node, parent: MetaNode):
        if parent is self.root:
            self.remove_node(node)

    def add_node(self, node: Node) -> NodeItem:
        """
        Add and return a default constructed :class:`.NodeItem` for a
        :class:`Node` instance `node`. If the `node` is already in
        the scene do nothing and just return its item.
        """
        if node in self.__item_for_node:
            # Already added
            return self.__item_for_node[node]

        delegate = ItemDelegate()
        item = delegate.createGraphicsWidget(node, self)
        item.inputAnchorItem.setAnchorOpen(self.__anchors_opened)
        item.outputAnchorItem.setAnchorOpen(self.__anchors_opened)
        self.__item_for_node[node] = item
        return self.add_node_item(item)

    def new_node_item(self, widget_desc, category_desc=None):
        # type: (Union[WidgetDescription, Node], Optional[CategoryDescription]) -> NodeItem
        """
        Construct an new :class:`.NodeItem` from a `WidgetDescription`.
        Optionally also set `CategoryDescription`.
        """
        warnings.warn(
            "new_node_item is deprecated", DeprecationWarning, stacklevel=2
        )
        if isinstance(widget_desc, Node):
            delegate = ItemDelegate()
            item = delegate.createGraphicsWidget(widget_desc, self)
        else:
            item = items.NodeItem.from_node_meta(widget_desc)
        item.setAnimationEnabled(self.__node_animation_enabled)
        return item

    def remove_node_item(self, item):
        # type: (NodeItem) -> None
        """
        Remove `item` (:class:`.NodeItem`) from the scene.
        """
        self.activated_mapper.removeMappings(item)
        self.hovered_mapper.removeMappings(item)
        self.position_change_mapper.removeMappings(item)
        self.link_activated_mapper.removeMappings(item)

        item.hide()
        self.removeItem(item)
        self.__node_items.remove(item)

        self.node_item_removed.emit(item)

    def remove_node(self, node: Node) -> None:
        """
        Remove the :class:`.NodeItem` instance that was previously
        constructed for a :class:`Node` `node` using the `add_node`
        method.
        """
        item = self.__item_for_node.pop(node)
        delegate = ItemDelegate()
        self.remove_node_item(item)
        delegate.destroyGraphicsWidget(item, node)

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

    def __on_link_added(self, link: Link, parent: MetaNode):
        if parent is self.root:
            self.add_link(link)

    def __on_link_removed(self, link: Link, parent: MetaNode):
        if parent is self.root:
            self.remove_link(link)

    def add_link(self, link: Link) -> LinkItem:
        """
        Create and add a :class:`.LinkItem` instance for a
        :class:`Link` instance. If the link is already in the scene
        do nothing and just return its :class:`.LinkItem`.
        """
        if link in self.__item_for_link:
            return self.__item_for_link[link]

        source = self.__item_for_node[link.source_node]
        sink = self.__item_for_node[link.sink_node]

        item = self.new_link_item(source, link.source_channel,
                                  sink, link.sink_channel)

        item.setEnabled(link.is_enabled())
        link.enabled_changed.connect(item.setEnabled)

        if link.is_dynamic():
            item.setDynamic(True)
            item.setDynamicEnabled(link.is_dynamic_enabled())
            link.dynamic_enabled_changed.connect(item.setDynamicEnabled)

        item.setRuntimeState(link.runtime_state())
        link.state_changed.connect(item.setRuntimeState)

        self.add_link_item(item)
        self.__item_for_link[link] = item
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

    def remove_link(self, link: Link) -> None:
        """
        Remove a :class:`.LinkItem` instance that was previously constructed
        for a :class:`Link` instance `link` using the `add_link` method.
        """
        item = self.__item_for_link.pop(link)
        link.enabled_changed.disconnect(item.setEnabled)

        if link.is_dynamic():
            link.dynamic_enabled_changed.disconnect(
                item.setDynamicEnabled
            )
        link.state_changed.disconnect(item.setRuntimeState)
        self.remove_link_item(item)

    def link_items(self):
        # type: () -> List[LinkItem]
        """
        Return all :class:`.LinkItem` s in the scene.
        """
        return list(self.__link_items)

    def add_annotation_item(self, annotation):
        # type: (AnnotationItem) -> AnnotationItem
        """
        Add an :class:`.AnnotationItem` item to the scene.
        """
        self.__annotation_items.append(annotation)
        self.addItem(annotation)
        self.annotation_added.emit(annotation)
        return annotation

    def __on_annotation_added(self, annot: Annotation, parent: MetaNode):
        if parent is self.root:
            self.add_annotation(annot)

    def __on_annotation_removed(self, annot: Annotation, parent: MetaNode):
        if parent is self.root:
            self.remove_annotation(annot)

    def add_annotation(self, scheme_annot):
        # type: (Annotation) -> AnnotationItem
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
        # type: (AnnotationItem) -> None
        """
        Remove an :class:`.AnnotationItem` instance from the scene.

        """
        self.__annotation_items.remove(annotation)
        self.removeItem(annotation)
        self.annotation_removed.emit(annotation)

    def remove_annotation(self, scheme_annotation):
        # type: (Annotation) -> None
        """
        Remove an :class:`.AnnotationItem` instance that was previously added
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
        # type: () -> List[AnnotationItem]
        """
        Return all :class:`.AnnotationItem` items in the scene.
        """
        return self.__annotation_items.copy()

    def item_for_annotation(self, scheme_annotation):
        # type: (Annotation) -> AnnotationItem
        return self.__item_for_annotation[scheme_annotation]

    def annotation_for_item(self, item):
        # type: (AnnotationItem) -> Annotation
        rev = {v: k for k, v in self.__item_for_annotation.items()}
        return rev[item]

    def node_for_item(self, item):
        # type: (NodeItem) -> Node
        """
        Return the `Node` for the `item`.
        """
        rev = dict([(v, k) for k, v in self.__item_for_node.items()])
        return rev[item]

    def item_for_node(self, node):
        # type: (Node) -> NodeItem
        """
        Return the :class:`NodeItem` instance for a :class:`Node`.
        """
        return self.__item_for_node[node]

    def link_for_item(self, item):
        # type: (LinkItem) -> Link
        """
        Return the `Link for `item` (:class:`LinkItem`).
        """
        rev = dict([(v, k) for k, v in self.__item_for_link.items()])
        return rev[item]

    def item_for_link(self, link):
        # type: (Link) -> LinkItem
        """
        Return the :class:`LinkItem` for a :class:`Link`
        """
        return self.__item_for_link[link]

    def item_for_element(self, element: Element) -> QGraphicsItem:
        """Return the associated :class:`QGraphicsItem` for the `element`."""
        if isinstance(element, Node):
            return self.__item_for_node[element]
        elif isinstance(element, Link):
            return self.__item_for_link[element]
        elif isinstance(element, Annotation):
            return self.__item_for_annotation[element]
        else:
            raise TypeError(element)

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
        # type: () -> List[AnnotationItem]
        """
        Return the selected :class:`AnnotationItem`'s
        """
        return [item for item in self.__annotation_items if item.isSelected()]

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

    def set_user_interaction_handler(self, handler):
        super().set_user_interaction_handler(handler)
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

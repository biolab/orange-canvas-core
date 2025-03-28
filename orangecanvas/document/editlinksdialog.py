"""
===========
Link Editor
===========

An Dialog to edit links between two nodes in the scheme.

"""
import typing
from typing import cast, List, Tuple, Optional, Any, Union

from collections import namedtuple
from xml.sax.saxutils import escape

from AnyQt.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QDialogButtonBox, QGraphicsScene,
    QGraphicsView, QGraphicsWidget, QGraphicsRectItem,
    QGraphicsLineItem, QGraphicsTextItem, QGraphicsLayoutItem,
    QGraphicsLinearLayout, QGraphicsGridLayout, QGraphicsPixmapItem,
    QGraphicsDropShadowEffect, QSizePolicy, QGraphicsItem, QWidget,
    QWIDGETSIZE_MAX, QStyle
)
from AnyQt.QtGui import (
    QPalette, QPen, QPainter, QIcon, QPainterPathStroker
)
from AnyQt.QtCore import (
    Qt, QObject, QSize, QSizeF, QPointF, QRectF, QEvent
)

from ..scheme import Node, compatible_channels
from ..registry import InputSignal, OutputSignal
from ..utils import type_str

if typing.TYPE_CHECKING:
    IOPair = Tuple[OutputSignal, InputSignal]


class EditLinksDialog(QDialog):
    """
    A dialog for editing links.

    >>> dlg = EditLinksDialog()
    >>> dlg.setNodes(source_node, sink_node)
    >>> dlg.setLinks([(source_node.output_channel("Data"),
    ...                sink_node.input_channel("Data"))])
    >>> if dlg.exec() == EditLinksDialog.Accepted:
    ...     new_links = dlg.links()
    ...
    """
    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QWidget], Any) -> None
        super().__init__(parent, **kwargs)

        self.setModal(True)

        self.__setupUi()

    def __setupUi(self):
        layout = QVBoxLayout()

        # Scene with the link editor.
        self.scene = LinksEditScene()
        self.view = QGraphicsView(self.scene)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setRenderHint(QPainter.Antialiasing)

        self.scene.editWidget.geometryChanged.connect(self.__onGeometryChanged)

        # Ok/Cancel/Clear All buttons.
        buttons = QDialogButtonBox(QDialogButtonBox.Ok |
                                   QDialogButtonBox.Cancel |
                                   QDialogButtonBox.Reset,
                                   Qt.Horizontal)

        clear_button = buttons.button(QDialogButtonBox.Reset)
        clear_button.setText(self.tr("Clear All"))

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        clear_button.clicked.connect(self.scene.editWidget.clearLinks)

        layout.addWidget(self.view)
        layout.addWidget(buttons)

        self.setLayout(layout)
        layout.setSizeConstraint(QVBoxLayout.SetFixedSize)

        self.setSizeGripEnabled(False)

    def setNodes(self, source_node: Node, sink_node: Node) -> None:
        """
        Set the source/sink nodes (:class:`.Node` instances)
        between which to edit the links.

        .. note:: This should be called before :func:`setLinks`.
        """
        self.scene.editWidget.setNodes(source_node, sink_node)

    def setLinks(self, links):
        # type: (List[IOPair]) -> None
        """
        Set a list of links to display between the source and sink
        nodes. The `links` is a list of (`OutputSignal`, `InputSignal`)
        tuples where the first element is an output signal of the source
        node and the second an input signal of the sink node.

        """
        self.scene.editWidget.setLinks(links)

    def links(self):
        # type: () -> List[IOPair]
        """
        Return the links between the source and sink node.
        """
        return self.scene.editWidget.links()

    def __onGeometryChanged(self):
        size = self.scene.editWidget.size()
        m = self.contentsMargins()
        self.view.setFixedSize(
            size.toSize() + QSize(m.left() + m.right() + 4,
                                  m.top() + m.bottom() + 4)
        )
        self.view.setSceneRect(self.scene.editWidget.geometry())


def find_item_at(
        scene,  # type: QGraphicsScene
        pos,    # type: QPointF
        order=Qt.DescendingOrder,  # type: Qt.SortOrder
        type=None,   # type: Optional[type]
        name=None,   # type: Optional[str]
):  # type: (...) -> Optional[QGraphicsItem]
    """
    Find an object in a :class:`QGraphicsScene` `scene` at `pos`.
    If `type` is not `None` the it must specify  the type of the item.
    I `name` is not `None` it must be a name of the object
    (`QObject.objectName()`).

    """
    items = scene.items(pos, Qt.IntersectsItemShape, order)
    for item in items:
        if type is not None and \
                not isinstance(item, type):
            continue

        if name is not None and isinstance(item, QObject) and \
                item.objectName() != name:
            continue
        return item
    return None


class LinksEditScene(QGraphicsScene):
    """
    A :class:`QGraphicsScene` used by the :class:`LinkEditWidget`.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.editWidget = LinksEditWidget()
        self.addItem(self.editWidget)

    findItemAt = find_item_at


_Link = namedtuple(
    "_Link",
    ["output",    # OutputSignal
     "input",     # InputSignal
     "lineItem",  # QGraphicsLineItem connecting the input to output
     ])


class LinksEditWidget(QGraphicsWidget):
    """
    A Graphics Widget for editing the links between two nodes.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)

        self.source = None
        self.sink = None

        # QGraphicsWidget/Items in the scene.
        self.sourceNodeWidget = None
        self.sourceNodeTitle = None
        self.sinkNodeWidget = None
        self.sinkNodeTitle = None

        self.__links = []  # type: List[IOPair]

        self.__textItems = []
        self.__iconItems = []
        self.__tmpLine = None
        self.__dragStartItem = None

        self.setLayout(QGraphicsLinearLayout(Qt.Vertical))
        self.layout().setContentsMargins(0, 0, 0, 0)

    def removeItems(self, items):
        """
        Remove child items from the widget and scene.
        """
        scene = self.scene()
        for item in items:
            item.setParentItem(None)
            if scene is not None:
                scene.removeItem(item)

    def clear(self):
        """
        Clear the editor state (source and sink nodes, channels ...).
        """
        if self.layout().count():
            widget = self.layout().takeAt(0).graphicsItem()
            self.removeItems([widget])

        self.source = None
        self.sink = None

    def setNodes(self, source, sink):
        """
        Set the source/sink nodes (:class:`SchemeNode` instances) between
        which to edit the links.

        .. note:: Call this before :func:`setLinks`.

        """
        self.clear()

        self.source = source
        self.sink = sink

        self.__updateState()

    def setLinks(self, links):
        """
        Set a list of links to display between the source and sink
        nodes. `links` must be a list of (`OutputSignal`, `InputSignal`)
        tuples where the first element refers to the source node
        and the second to the sink node (as set by `setNodes`).

        """
        self.clearLinks()
        for output, input in links:
            self.addLink(output, input)

    def links(self):
        """
        Return the links between the source and sink node.
        """
        return [(link.output, link.input) for link in self.__links]

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            startItem = find_item_at(self.scene(), event.pos(),
                                     type=ChannelAnchor)
            if startItem is not None and startItem.isEnabled():
                # Start a connection line drag.
                self.__dragStartItem = startItem
                self.__tmpLine = None

                event.accept()
                return

            lineItem = find_item_at(self.scene(), event.scenePos(),
                                    type=QGraphicsLineItem)
            if lineItem is not None:
                # Remove a connection under the mouse
                for link in self.__links:
                    if link.lineItem == lineItem:
                        self.removeLink(link.output, link.input)
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:

            downPos = event.buttonDownPos(Qt.LeftButton)
            if not self.__tmpLine and self.__dragStartItem and \
                    (downPos - event.pos()).manhattanLength() > \
                        QApplication.instance().startDragDistance():
                # Start a line drag
                line = LinkLineItem(self)
                start = self.__dragStartItem.boundingRect().center()
                start = self.mapFromItem(self.__dragStartItem, start)
                eventPos = event.pos()
                line.setLine(start.x(), start.y(), eventPos.x(), eventPos.y())
                self.__tmpLine = line

                if self.__dragStartItem in self.sourceNodeWidget.channelAnchors:
                    for anchor in self.sinkNodeWidget.channelAnchors:
                        self.__updateAnchorState(anchor, [self.__dragStartItem])
                else:
                    for anchor in self.sourceNodeWidget.channelAnchors:
                        self.__updateAnchorState(anchor, [self.__dragStartItem])

            if self.__tmpLine:
                # Update the temp line
                line = self.__tmpLine.line()

                maybe_anchor = find_item_at(self.scene(), event.scenePos(),
                                            type=ChannelAnchor)
                # If hovering over anchor
                if maybe_anchor is not None and maybe_anchor.isEnabled():
                    target_pos = maybe_anchor.boundingRect().center()
                    target_pos = self.mapFromItem(maybe_anchor, target_pos)
                    line.setP2(target_pos)
                else:
                    target_pos = event.pos()
                    line.setP2(target_pos)

                self.__tmpLine.setLine(line)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.__tmpLine:
            self.__resetAnchorStates()
            endItem = find_item_at(self.scene(), event.scenePos(),
                                   type=ChannelAnchor)

            if endItem is not None:
                startItem = self.__dragStartItem
                startChannel = startItem.channel()
                endChannel = endItem.channel()
                possible = False

                # Make sure the drag was from input to output (or reversed) and
                # not between input -> input or output -> output
                # pylint: disable=unidiomatic-typecheck
                if type(startChannel) != type(endChannel):
                    if isinstance(startChannel, InputSignal):
                        startChannel, endChannel = endChannel, startChannel

                    possible = compatible_channels(startChannel, endChannel)

                if possible:
                    self.addLink(startChannel, endChannel)

            self.scene().removeItem(self.__tmpLine)
            self.__tmpLine = None
            self.__dragStartItem = None

        super().mouseReleaseEvent(event)

    def addLink(self, output, input):
        """
        Add a link between `output` (:class:`OutputSignal`) and `input`
        (:class:`InputSignal`).

        """
        if not compatible_channels(output, input):
            return

        if output not in self.source.output_channels():
            raise ValueError("%r is not an output channel of %r" % \
                             (output, self.source))

        if input not in self.sink.input_channels():
            raise ValueError("%r is not an input channel of %r" % \
                             (input, self.sink))

        if input.single:
            # Remove existing link if it exists.
            for s1, s2, _ in self.__links:
                if s2 == input:
                    self.removeLink(s1, s2)

        line = LinkLineItem(self)
        line.setToolTip(self.tr("Click to remove the link."))
        source_anchor = self.sourceNodeWidget.anchor(output)
        sink_anchor = self.sinkNodeWidget.anchor(input)

        source_pos = source_anchor.boundingRect().center()
        source_pos = self.mapFromItem(source_anchor, source_pos)

        sink_pos = sink_anchor.boundingRect().center()
        sink_pos = self.mapFromItem(sink_anchor, sink_pos)
        line.setLine(source_pos.x(), source_pos.y(), sink_pos.x(), sink_pos.y())

        self.__links.append(_Link(output, input, line))

    def removeLink(self, output, input):
        """
        Remove a link between the `output` and `input` channels.
        """
        for link in list(self.__links):
            if link.output == output and link.input == input:
                self.scene().removeItem(link.lineItem)
                self.__links.remove(link)
                break
        else:
            raise ValueError("No such link {0.name!r} -> {1.name!r}." \
                             .format(output, input))

    def clearLinks(self):
        """
        Clear (remove) all the links.
        """
        for output, input, _ in list(self.__links):
            self.removeLink(output, input)

    def __updateState(self):
        """
        Update the widget with the new source/sink node signal descriptions.
        """
        widget = QGraphicsWidget()
        widget.setLayout(QGraphicsGridLayout())

        # Space between left and right anchors
        widget.layout().setHorizontalSpacing(50)

        left_node = EditLinksNode(self, direction=Qt.LeftToRight,
                                  node=self.source)

        left_node.setSizePolicy(QSizePolicy.MinimumExpanding,
                                QSizePolicy.MinimumExpanding)

        right_node = EditLinksNode(self, direction=Qt.RightToLeft,
                                   node=self.sink)

        right_node.setSizePolicy(QSizePolicy.MinimumExpanding,
                                 QSizePolicy.MinimumExpanding)

        left_node.setMinimumWidth(150)
        right_node.setMinimumWidth(150)

        widget.layout().addItem(left_node, 0, 0,)
        widget.layout().addItem(right_node, 0, 1,)

        title_template = "<center><b>{0}<b></center>"

        left_title = GraphicsTextWidget(self)
        left_title.setHtml(title_template.format(escape(self.source.title)))
        left_title.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        right_title = GraphicsTextWidget(self)
        right_title.setHtml(title_template.format(escape(self.sink.title)))
        right_title.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        widget.layout().addItem(left_title, 1, 0,
                                alignment=Qt.AlignHCenter | Qt.AlignTop)
        widget.layout().addItem(right_title, 1, 1,
                                alignment=Qt.AlignHCenter | Qt.AlignTop)

        widget.setParentItem(self)

        max_w = max(left_node.sizeHint(Qt.PreferredSize).width(),
                    right_node.sizeHint(Qt.PreferredSize).width())

        # fix same size
        left_node.setMinimumWidth(max_w)
        right_node.setMinimumWidth(max_w)
        left_title.setMinimumWidth(max_w)
        right_title.setMinimumWidth(max_w)

        self.layout().addItem(widget)
        self.layout().activate()

        self.sourceNodeWidget = left_node
        self.sinkNodeWidget = right_node
        self.sourceNodeTitle = left_title
        self.sinkNodeTitle = right_title

        # AnchorHover hover over anchor before hovering over line
        class AnchorHover(QGraphicsRectItem):
            def __init__(self, anchor, parent=None):
                super().__init__(parent=parent)
                self.setAcceptHoverEvents(True)

                self.anchor = anchor
                self.setRect(anchor.boundingRect())

                self.setPos(self.mapFromScene(anchor.scenePos()))
                self.setFlag(QGraphicsItem.ItemHasNoContents, True)

            def hoverEnterEvent(self, event):
                if self.anchor.isEnabled():
                    self.anchor.hoverEnterEvent(event)
                else:
                    event.ignore()

            def hoverLeaveEvent(self, event):
                if self.anchor.isEnabled():
                    self.anchor.hoverLeaveEvent(event)
                else:
                    event.ignore()

        for anchor in left_node.channelAnchors + right_node.channelAnchors:
            anchor.overlay = AnchorHover(anchor, parent=self)
            anchor.overlay.setZValue(2.0)

        self.__resetAnchorStates()

    def __resetAnchorStates(self):
        source_anchors = self.sourceNodeWidget.channelAnchors
        sink_anchors = self.sinkNodeWidget.channelAnchors
        for anchor in source_anchors:
            self.__updateAnchorState(anchor, sink_anchors)
        for anchor in sink_anchors:
            self.__updateAnchorState(anchor, source_anchors)

    def __updateAnchorState(self, anchor, opposite_anchors):
        first_channel = anchor.channel()
        for opposite_anchor in opposite_anchors:
            second_channel = opposite_anchor.channel()
            if isinstance(first_channel, OutputSignal) and \
               compatible_channels(first_channel, second_channel) or \
               isinstance(first_channel, InputSignal) and \
               compatible_channels(second_channel, first_channel):
                anchor.setEnabled(True)
                anchor.setToolTip("Click and drag to connect widgets!")
                return
        if isinstance(first_channel, OutputSignal):
            anchor.setToolTip("No compatible input channel.")
        else:
            anchor.setToolTip("No compatible output channel.")
        anchor.setEnabled(False)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.PaletteChange:
            palette = self.palette()
            for _, _, link in self.__links:
                link.setPalette(palette)
        super().changeEvent(event)


class EditLinksNode(QGraphicsWidget):
    """
    A Node representation with channel anchors.

    `direction` specifies the layout (default `Qt.LeftToRight` will
    have icon on the left and channels on the right).

    """

    def __init__(self, parent=None, direction=Qt.LeftToRight,
                 node=None, icon=None, iconSize=None, **args):
        super().__init__(parent, **args)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.__direction = direction

        self.setLayout(QGraphicsLinearLayout(Qt.Horizontal))

        # Set the maximum size, otherwise the layout can't grow beyond its
        # sizeHint (and we need it to grow so the widget can grow and keep the
        # contents centered vertically.
        self.layout().setMaximumSize(QSizeF(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX))

        self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           QSizePolicy.MinimumExpanding)

        self.__iconSize = iconSize or QSize(64, 64)
        self.__icon = icon

        self.__iconItem = QGraphicsPixmapItem(self)
        self.__iconLayoutItem = GraphicsItemLayoutItem(item=self.__iconItem)

        self.__channelLayout = QGraphicsGridLayout()
        self.channelAnchors: List[ChannelAnchor] = []

        if self.__direction == Qt.LeftToRight:
            self.layout().addItem(self.__iconLayoutItem)
            self.layout().addItem(self.__channelLayout)
            channel_alignemnt = Qt.AlignRight

        else:
            self.layout().addItem(self.__channelLayout)
            self.layout().addItem(self.__iconLayoutItem)
            channel_alignemnt = Qt.AlignLeft

        self.layout().setAlignment(self.__iconLayoutItem, Qt.AlignCenter)
        self.layout().setAlignment(self.__channelLayout,
                                   Qt.AlignVCenter | channel_alignemnt)

        self.node: Optional[Node] = None
        self.channels: Union[List[InputSignal], List[OutputSignal]] = []
        if node is not None:
            self.setNode(node)

    def setIconSize(self, size):
        """
        Set the icon size for the node.
        """
        if size != self.__iconSize:
            self.__iconSize = QSize(size)
            if self.__icon:
                self.__iconItem.setPixmap(self.__icon.pixmap(size))
                self.__iconLayoutItem.updateGeometry()

    def iconSize(self):
        """
        Return the icon size.
        """
        return QSize(self.__iconSize)

    def setIcon(self, icon):
        """
        Set the icon to display.
        """
        if icon != self.__icon:
            self.__icon = QIcon(icon)
            self.__iconItem.setPixmap(icon.pixmap(self.iconSize()))
            self.__iconLayoutItem.updateGeometry()

    def icon(self):
        """
        Return the icon.
        """
        return QIcon(self.__icon)

    def setSchemeNode(self, node):
        self.setNode(node)

    def setNode(self, node: Node) -> None:
        """
        Set an instance of `Node`. The widget will be initialized with its
        icon and channels.
        """
        self.node = node
        channels: Union[List[InputSignal], List[OutputSignal]]
        if self.__direction == Qt.LeftToRight:
            channels = node.output_channels()
        else:
            channels = node.input_channels()
        self.channels = channels

        self.setIcon(node.icon())

        label_template = ('<div align="{align}">'
                          '<span class="channelname">{name}</span>'
                          '</div>')

        if self.__direction == Qt.LeftToRight:
            align = "right"
            label_alignment = Qt.AlignVCenter | Qt.AlignRight
            anchor_alignment = Qt.AlignVCenter | Qt.AlignLeft
            label_row = 0
            anchor_row = 1
        else:
            align = "left"
            label_alignment = Qt.AlignVCenter | Qt.AlignLeft
            anchor_alignment = Qt.AlignVCenter | Qt.AlignLeft
            label_row = 1
            anchor_row = 0

        self.channelAnchors = []
        grid = self.__channelLayout
        for i, channel in enumerate(channels):
            channel = cast(Union[InputSignal, OutputSignal], channel)
            text = label_template.format(align=align,
                                         name=escape(channel.name))

            text_item = GraphicsTextWidget(self)
            text_item.setHtml(text)
            text_item.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            text_item.setToolTip(
                escape(getattr(channel, 'description', type_str(channel.types)))
            )

            grid.addItem(text_item, i, label_row,
                         alignment=label_alignment)

            anchor = ChannelAnchor(self, channel=channel,
                                   rect=QRectF(0, 0, 20, 20))

            layout_item = GraphicsItemLayoutItem(grid, item=anchor)
            grid.addItem(layout_item, i, anchor_row,
                         alignment=anchor_alignment)

            self.channelAnchors.append(anchor)

    def anchor(self, channel):
        """
        Return the anchor item for the `channel` name.
        """
        for anchor in self.channelAnchors:
            if anchor.channel() == channel:
                return anchor

        raise ValueError(channel.name)

    def paint(self, painter, option, widget=None):
        painter.save()
        palette = self.palette()
        border = palette.brush(QPalette.Mid)
        pen = QPen(border, 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(palette.brush(QPalette.Window))
        brect = self.boundingRect()
        painter.drawRoundedRect(brect, 4, 4)
        painter.restore()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.PaletteChange:
            palette = self.palette()
            for anc in self.channelAnchors:
                anc.setPalette(palette)
        super().changeEvent(event)


class GraphicsItemLayoutItem(QGraphicsLayoutItem):
    """
    A graphics layout that handles the position of a general QGraphicsItem
    in a QGraphicsLayout. The items boundingRect is used as this items fixed
    sizeHint and the item is positioned at the top left corner of the this
    items geometry.

    """

    def __init__(self, parent=None, item=None, ):
        self.__item = None
        super().__init__(parent, isLayout=False)

        self.setOwnedByLayout(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        if item is not None:
            self.setItem(item)

    def setItem(self, item):
        self.__item = item
        self.setGraphicsItem(item)

    def setGeometry(self, rect):
        # TODO: specifiy if the geometry should be set relative to the
        # bounding rect top left corner
        if self.__item:
            self.__item.setPos(rect.topLeft())

        super().setGeometry(rect)

    def sizeHint(self, which, constraint):
        if self.__item:
            return self.__item.boundingRect().size()
        else:
            return super().sizeHint(which, constraint)


class ChannelAnchor(QGraphicsRectItem):
    """
    A rectangular Channel Anchor indicator.
    """
    #: Used/filled by EditLinksWidget to track overlays
    overlay: QGraphicsRectItem = None

    def __init__(self, parent=None, channel=None, rect=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.__channel = None
        if isinstance(parent, QGraphicsWidget):
            palette = parent.palette()
        else:
            palette = QPalette()
        self.__palette = palette

        if rect is None:
            rect = QRectF(0, 0, 20, 20)

        self.setRect(rect)

        if channel:
            self.setChannel(channel)

        self.__default_pen = QPen(palette.color(QPalette.Text), 1)
        self.__hover_pen = QPen(palette.color(QPalette.Text), 2)
        self.setPen(self.__default_pen)

    def setChannel(self, channel):
        """
        Set the channel description.
        """
        if channel != self.__channel:
            self.__channel = channel

    def channel(self):
        """
        Return the channel description.
        """
        return self.__channel

    def setEnabled(self, enabled):
        super().setEnabled(enabled)
        self.update()

    def setToolTip(self, toolTip: str) -> None:
        super().setToolTip(toolTip)
        if self.overlay is not None:
            self.overlay.setToolTip(toolTip)

    def setPalette(self, palette: QPalette) -> None:
        self.__palette = palette
        self.__default_pen.setColor(palette.color(QPalette.Text))
        self.__hover_pen.setColor(palette.color(QPalette.Text))
        pen = self.__hover_pen if self.isUnderMouse() else self.__default_pen
        self.setPen(pen)

    def palette(self) -> QPalette:
        return QPalette(self.__palette)

    def paint(self, painter, option, widget=None):
        rect = self.rect()
        palette = self.palette()
        pen = self.pen()
        if option.state & QStyle.State_Enabled:
            brush = palette.brush(QPalette.Base)
        else:
            brush = palette.brush(QPalette.Disabled, QPalette.Window)
        painter.setPen(pen)
        painter.setBrush(brush)
        painter.drawRect(rect)
        # if disabled, draw X over box
        if not option.state & QStyle.State_Enabled:
            painter.setClipRect(rect, Qt.ReplaceClip)
            painter.drawLine(rect.topLeft(), rect.bottomRight())
            painter.drawLine(rect.topRight(), rect.bottomLeft())

    def hoverEnterEvent(self, event):
        self.setPen(self.__hover_pen)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(self.__default_pen)
        super().hoverLeaveEvent(event)


class GraphicsTextWidget(QGraphicsWidget):
    """
    A QGraphicsWidget subclass that manages a `QGraphicsTextItem`.
    """

    def __init__(self, parent=None, textItem=None):
        super().__init__(parent)
        if textItem is None:
            textItem = QGraphicsTextItem()

        self.__textItem = textItem
        self.__textItem.setParentItem(self)
        self.__textItem.setPos(0, 0)

        doc_layout = self.document().documentLayout()
        doc_layout.documentSizeChanged.connect(self._onDocumentSizeChanged)

    def sizeHint(self, which, constraint=QSizeF()):
        if which == Qt.PreferredSize:
            doc = self.document()
            textwidth = doc.textWidth()
            if textwidth != constraint.width():
                cloned = doc.clone(self)
                cloned.setTextWidth(constraint.width())
                sh = cloned.size()
                cloned.deleteLater()
            else:
                sh = doc.size()
            return sh
        else:
            return super().sizeHint(which, constraint)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.__textItem.setTextWidth(rect.width())

    def setPlainText(self, text):
        self.__textItem.setPlainText(text)
        self.updateGeometry()

    def setHtml(self, text):
        self.__textItem.setHtml(text)

    def adjustSize(self):
        self.__textItem.adjustSize()
        self.updateGeometry()

    def setDefaultTextColor(self, color):
        self.__textItem.setDefaultTextColor(color)

    def document(self):
        return self.__textItem.document()

    def setDocument(self, doc):
        doc_layout = self.document().documentLayout()
        doc_layout.documentSizeChanged.disconnect(self._onDocumentSizeChanged)

        self.__textItem.setDocument(doc)

        doc_layout = self.document().documentLayout()
        doc_layout.documentSizeChanged.connect(self._onDocumentSizeChanged)

        self.updateGeometry()

    def _onDocumentSizeChanged(self, size):
        """The doc size has changed"""
        self.updateGeometry()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.PaletteChange:
            palette = self.palette()
            self.__textItem.setDefaultTextColor(palette.color(QPalette.Text))
        super().changeEvent(event)


class LinkLineItem(QGraphicsLineItem):
    """
    A line connecting two Channel Anchors.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptHoverEvents(True)
        self.__shape = None
        if isinstance(parent, QGraphicsWidget):
            palette = parent.palette()
        else:
            palette = QPalette()
        self.__palette = palette
        self.__default_pen = QPen(palette.color(QPalette.Text), 4)
        self.__default_pen.setCapStyle(Qt.RoundCap)
        self.__hover_pen = QPen(palette.color(QPalette.Text), 4)
        self.__hover_pen.setCapStyle(Qt.RoundCap)
        self.setPen(self.__default_pen)

        self.__shadow = QGraphicsDropShadowEffect(
            blurRadius=10,
            color=palette.color(QPalette.Shadow),
            offset=QPointF(0, 0)
        )

        self.setGraphicsEffect(self.__shadow)
        self.prepareGeometryChange()
        self.__shadow.setEnabled(False)

    def setPalette(self, palette: QPalette) -> None:
        self.__palette = palette
        self.__default_pen.setColor(palette.color(QPalette.Text))
        self.__hover_pen.setColor(palette.color(QPalette.Text))
        self.setPen(
            self.__hover_pen if self.isUnderMouse() else self.__default_pen
        )

    def palette(self) -> QPalette:
        return QPalette(self.__palette)

    def setLine(self, *args, **kwargs):
        super().setLine(*args, **kwargs)

        # extends mouse hit area
        stroke_path = QPainterPathStroker()
        stroke_path.setCapStyle(Qt.RoundCap)

        stroke_path.setWidth(10)
        self.__shape = stroke_path.createStroke(super().shape())

    def shape(self):
        if self.__shape is None:
            return super().shape()
        return self.__shape

    def boundingRect(self) -> QRectF:
        rect = super().boundingRect()
        return rect.adjusted(5, -5, 5, 5)

    def hoverEnterEvent(self, event):
        self.prepareGeometryChange()
        self.__shadow.setEnabled(True)
        self.setPen(self.__hover_pen)
        self.setZValue(1.0)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.prepareGeometryChange()
        self.__shadow.setEnabled(False)
        self.setPen(self.__default_pen)
        self.setZValue(0.0)
        super().hoverLeaveEvent(event)

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        if option.state & QStyle.State_MouseOver:
            line = self.line()
            center = line.center()
            painter.translate(center)
            painter.rotate(-line.angle())
            pen = painter.pen()
            pen.setWidthF(3)
            painter.setPen(pen)
            painter.drawLine(-5, -5, 5, 5)
            painter.drawLine(-5, 5, 5, -5)

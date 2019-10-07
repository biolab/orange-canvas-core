"""
=========
Node Item
=========

"""
import typing
import string

from operator import attrgetter
from itertools import groupby
from xml.sax.saxutils import escape

from typing import Dict, Any, Optional, List, Iterable, Tuple

from AnyQt.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QGraphicsTextItem, QGraphicsWidget,
    QGraphicsDropShadowEffect, QStyle, QApplication, QGraphicsSceneMouseEvent,
    QGraphicsSceneContextMenuEvent, QStyleOptionGraphicsItem, QWidget, QGraphicsEllipseItem)
from AnyQt.QtGui import (
    QPen, QBrush, QColor, QPalette, QIcon, QPainter, QPainterPath,
    QPainterPathStroker, QTextDocument, QTextBlock, QTextLine
)
from AnyQt.QtCore import (
    Qt, QEvent, QPointF, QRectF, QRect, QSize, QTime, QTimer,
    QPropertyAnimation, QEasingCurve, QObject
)
from AnyQt.QtCore import pyqtSignal as Signal, pyqtProperty as Property

from .graphicspathobject import GraphicsPathObject
from .utils import saturated, radial_gradient

from ...scheme.node import UserMessage
from ...registry import NAMED_COLORS, WidgetDescription, CategoryDescription
from ...resources import icon_loader
from .utils import uniform_linear_layout_trunc

if typing.TYPE_CHECKING:
    from ...registry import WidgetDescription
    from . import LinkItem


def create_palette(light_color, color):
    # type: (QColor, QColor) -> QPalette
    """
    Return a new :class:`QPalette` from for the :class:`NodeBodyItem`.
    """
    palette = QPalette()

    palette.setColor(QPalette.Inactive, QPalette.Light,
                     saturated(light_color, 50))
    palette.setColor(QPalette.Inactive, QPalette.Midlight,
                     saturated(light_color, 90))
    palette.setColor(QPalette.Inactive, QPalette.Button,
                     light_color)

    palette.setColor(QPalette.Active, QPalette.Light,
                     saturated(color, 50))
    palette.setColor(QPalette.Active, QPalette.Midlight,
                     saturated(color, 90))
    palette.setColor(QPalette.Active, QPalette.Button,
                     color)
    palette.setColor(QPalette.ButtonText, QColor("#515151"))
    return palette


def default_palette():
    # type: () -> QPalette
    """
    Create and return a default palette for a node.
    """
    return create_palette(QColor(NAMED_COLORS["light-yellow"]),
                          QColor(NAMED_COLORS["yellow"]))


def animation_restart(animation):
    # type: (QPropertyAnimation) -> None
    if animation.state() == QPropertyAnimation.Running:
        animation.pause()
    animation.start()


SHADOW_COLOR = "#9CACB4"
SELECTED_SHADOW_COLOR = "#609ED7"


class NodeBodyItem(GraphicsPathObject):
    """
    The central part (body) of the `NodeItem`.
    """
    def __init__(self, parent=None):
        # type: (NodeItem) -> None
        super().__init__(parent)
        assert isinstance(parent, NodeItem)

        self.__processingState = 0
        self.__progress = -1.
        self.__animationEnabled = False
        self.__isSelected = False
        self.__hover = False
        self.__shapeRect = QRectF(-10, -10, 20, 20)

        self.setAcceptHoverEvents(True)

        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)

        self.setPen(QPen(Qt.NoPen))

        self.setPalette(default_palette())

        self.shadow = QGraphicsDropShadowEffect(
            blurRadius=0,
            color=QColor(SHADOW_COLOR),
            offset=QPointF(0, 0),
        )
        self.shadow.setEnabled(False)

        # An item with the same shape as this object, stacked behind this
        # item as a source for QGraphicsDropShadowEffect. Cannot attach
        # the effect to this item directly as QGraphicsEffect makes the item
        # non devicePixelRatio aware.
        shadowitem = GraphicsPathObject(self, objectName="shadow-shape-item")
        shadowitem.setPen(Qt.NoPen)
        shadowitem.setBrush(QBrush(QColor(SHADOW_COLOR).lighter()))
        shadowitem.setGraphicsEffect(self.shadow)
        shadowitem.setFlag(QGraphicsItem.ItemStacksBehindParent)
        self.__shadow = shadowitem
        self.__blurAnimation = QPropertyAnimation(self.shadow, b"blurRadius",
                                                  self)
        self.__blurAnimation.setDuration(100)
        self.__blurAnimation.finished.connect(self.__on_finished)

        self.__pingAnimation = QPropertyAnimation(self, b"scale", self)
        self.__pingAnimation.setDuration(250)
        self.__pingAnimation.setKeyValues([(0.0, 1.0), (0.5, 1.1), (1.0, 1.0)])

    # TODO: The body item should allow the setting of arbitrary painter
    # paths (for instance rounded rect, ...)
    def setShapeRect(self, rect):
        # type: (QRectF) -> None
        """
        Set the item's shape `rect`. The item should be confined within
        this rect.
        """
        path = QPainterPath()
        path.addEllipse(rect)
        self.setPath(path)
        self.__shadow.setPath(path)
        self.__shapeRect = rect

    def setPalette(self, palette):
        # type: (QPalette) -> None
        """
        Set the body color palette (:class:`QPalette`).
        """
        self.palette = QPalette(palette)
        self.__updateBrush()

    def setAnimationEnabled(self, enabled):
        # type: (bool) -> None
        """
        Set the node animation enabled.
        """
        if self.__animationEnabled != enabled:
            self.__animationEnabled = enabled

    def setProcessingState(self, state):
        # type: (int) -> None
        """
        Set the processing state of the node.
        """
        if self.__processingState != state:
            self.__processingState = state
            if not state and self.__animationEnabled:
                self.ping()

    def setProgress(self, progress):
        # type: (float) -> None
        """
        Set the progress indicator state of the node. `progress` should
        be a number between 0 and 100.

        """
        self.__progress = progress
        self.update()

    def ping(self):
        # type: () -> None
        """
        Trigger a 'ping' animation.
        """
        animation_restart(self.__pingAnimation)

    def hoverEnterEvent(self, event):
        self.__hover = True
        self.__updateShadowState()
        return super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.__hover = False
        self.__updateShadowState()
        return super().hoverLeaveEvent(event)

    def paint(self, painter, option, widget=None):
        # type: (QPainter, QStyleOptionGraphicsItem, Optional[QWidget]) -> None
        """
        Paint the shape and a progress meter.
        """
        # Let the default implementation draw the shape
        if option.state & QStyle.State_Selected:
            # Prevent the default bounding rect selection indicator.
            option.state = QStyle.State(option.state ^ QStyle.State_Selected)
        super().paint(painter, option, widget)
        if self.__progress >= 0:
            # Draw the progress meter over the shape.
            # Set the clip to shape so the meter does not overflow the shape.
            painter.save()
            painter.setClipPath(self.shape(), Qt.ReplaceClip)
            color = self.palette.color(QPalette.ButtonText)
            pen = QPen(color, 5)
            painter.setPen(pen)
            painter.setRenderHints(QPainter.Antialiasing)
            span = max(1, int(self.__progress * 57.60))
            painter.drawArc(self.__shapeRect, 90 * 16, -span)
            painter.restore()

    def __updateShadowState(self):
        # type: () -> None
        if self.__isSelected or self.__hover:
            enabled = True
            radius = 17
        else:
            enabled = False
            radius = 0

        if enabled and not self.shadow.isEnabled():
            self.shadow.setEnabled(enabled)

        if self.__isSelected:
            color = QColor(SELECTED_SHADOW_COLOR)
        else:
            color = QColor(SHADOW_COLOR)

        self.shadow.setColor(color)

        if radius == self.shadow.blurRadius():
            return

        if self.__animationEnabled:
            if self.__blurAnimation.state() == QPropertyAnimation.Running:
                self.__blurAnimation.pause()

            self.__blurAnimation.setStartValue(self.shadow.blurRadius())
            self.__blurAnimation.setEndValue(radius)
            self.__blurAnimation.start()
        else:
            self.shadow.setBlurRadius(radius)

    def __updateBrush(self):
        # type: () -> None
        palette = self.palette
        if self.__isSelected:
            cg = QPalette.Active
        else:
            cg = QPalette.Inactive

        palette.setCurrentColorGroup(cg)
        c1 = palette.color(QPalette.Light)
        c2 = palette.color(QPalette.Button)
        grad = radial_gradient(c2, c1)
        self.setBrush(QBrush(grad))

    # TODO: The selected state should be set using the
    # QStyle flags (State_Selected. State_HasFocus)

    def setSelected(self, selected):
        # type: (bool) -> None
        """
        Set the `selected` state.

        .. note:: The item does not have `QGraphicsItem.ItemIsSelectable` flag.
                  This property is instead controlled by the parent NodeItem.

        """
        self.__isSelected = selected
        self.__updateShadowState()
        self.__updateBrush()

    def __on_finished(self):
        # type: () -> None
        if self.shadow.blurRadius() == 0:
            self.shadow.setEnabled(False)


class LinkAnchorIndicator(QGraphicsEllipseItem):
    """
    A visual indicator of the link anchor point at both ends
    of the :class:`LinkItem`.

    """
    def __init__(self, parent=None):
        # type: (Optional[QGraphicsItem]) -> None
        super().__init__(parent)
        self.setRect(-3.5, -3.5, 7., 7.)
        self.setPen(QPen(Qt.NoPen))
        self.setBrush(QBrush(QColor("#9CACB4")))
        self.hoverBrush = QBrush(QColor("#959595"))

        self.__hover = False

    def setHoverState(self, state):
        # type: (bool) -> None
        """
        The hover state is set by the LinkItem.
        """
        if self.__hover != state:
            self.__hover = state
            self.update()

    def paint(self, painter, option, widget=None):
        # type: (QPainter, QStyleOptionGraphicsItem, Optional[QWidget]) -> None
        brush = self.hoverBrush if self.__hover else self.brush()

        painter.setBrush(brush)
        painter.setPen(self.pen())
        painter.drawEllipse(self.rect())


class AnchorPoint(QGraphicsObject):
    """
    A anchor indicator on the :class:`NodeAnchorItem`.
    """

    #: Signal emitted when the item's scene position changes.
    scenePositionChanged = Signal(QPointF)

    #: Signal emitted when the item's `anchorDirection` changes.
    anchorDirectionChanged = Signal(QPointF)

    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QGraphicsItem], Any) -> None
        super().__init__(parent, **kwargs)
        self.setFlag(QGraphicsItem.ItemIsFocusable)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        self.setFlag(QGraphicsItem.ItemHasNoContents, True)
        self.indicator = LinkAnchorIndicator(self)

        self.__direction = QPointF()

    def anchorScenePos(self):
        # type: () -> QPointF
        """
        Return anchor position in scene coordinates.
        """
        return self.mapToScene(QPointF(0, 0))

    def setAnchorDirection(self, direction):
        # type: (QPointF) -> None
        """
        Set the preferred direction (QPointF) in item coordinates.
        """
        if self.__direction != direction:
            self.__direction = QPointF(direction)
            self.anchorDirectionChanged.emit(direction)

    def anchorDirection(self):
        # type: () -> QPointF
        """
        Return the preferred anchor direction.
        """
        return QPointF(self.__direction)

    def itemChange(self, change, value):
        # type: (QGraphicsItem.GraphicsItemChange, Any) -> Any
        if change == QGraphicsItem.ItemScenePositionHasChanged:
            self.scenePositionChanged.emit(value)
        return super().itemChange(change, value)

    def boundingRect(self,):
        # type: () -> QRectF
        return QRectF()

    def setHoverState(self, enabled):
        self.indicator.setHoverState(enabled)

    def setBrush(self, brush):
        self.indicator.setBrush(brush)


class NodeAnchorItem(GraphicsPathObject):
    """
    The left/right widget input/output anchors.
    """
    def __init__(self, parent, **kwargs):
        # type: (Optional[QGraphicsItem], Any) -> None
        super().__init__(parent, **kwargs)
        self.__parentNodeItem = None  # type: Optional[NodeItem]
        self.setAcceptHoverEvents(True)
        self.setPen(QPen(Qt.NoPen))
        self.normalBrush = QBrush(QColor("#CDD5D9"))
        self.normalHoverBrush = QBrush(QColor("#9CACB4"))
        self.connectedBrush = self.normalHoverBrush
        self.connectedHoverBrush = QBrush(QColor("#959595"))
        self.setBrush(self.normalBrush)

        self.__animationEnabled = False
        self.__hover = False

        # Does this item have any anchored links.
        self.anchored = False

        if isinstance(parent, NodeItem):
            self.__parentNodeItem = parent
        else:
            self.__parentNodeItem = None

        self.__anchorPath = QPainterPath()
        self.__points = []  # type: List[AnchorPoint]
        self.__pointPositions = []  # type: List[float]

        self.__fullStroke = QPainterPath()
        self.__dottedStroke = QPainterPath()
        self.__shape = None  # type: Optional[QPainterPath]

        self.shadow = QGraphicsDropShadowEffect(
            blurRadius=0,
            color=QColor(SHADOW_COLOR),
            offset=QPointF(0, 0),
        )
        # self.setGraphicsEffect(self.shadow)
        self.shadow.setEnabled(False)

        shadowitem = GraphicsPathObject(self, objectName="shadow-shape-item")
        shadowitem.setPen(Qt.NoPen)
        shadowitem.setBrush(QBrush(QColor(SHADOW_COLOR)))
        shadowitem.setGraphicsEffect(self.shadow)
        shadowitem.setFlag(QGraphicsItem.ItemStacksBehindParent)
        self.__shadow = shadowitem
        self.__blurAnimation = QPropertyAnimation(self.shadow, b"blurRadius",
                                                  self)
        self.__blurAnimation.setDuration(50)
        self.__blurAnimation.finished.connect(self.__on_finished)

    def parentNodeItem(self):
        # type: () -> Optional['NodeItem']
        """
        Return a parent :class:`NodeItem` or ``None`` if this anchor's
        parent is not a :class:`NodeItem` instance.
        """
        return self.__parentNodeItem

    def setAnchorPath(self, path):
        # type: (QPainterPath) -> None
        """
        Set the anchor's curve path as a :class:`QPainterPath`.
        """
        self.__anchorPath = QPainterPath(path)
        # Create a stroke of the path.
        stroke_path = QPainterPathStroker()
        stroke_path.setCapStyle(Qt.RoundCap)

        # Shape is wider (bigger mouse hit area - should be settable)
        stroke_path.setWidth(25)
        self.prepareGeometryChange()
        self.__shape = stroke_path.createStroke(path)

        # The full stroke
        stroke_path.setWidth(3)
        self.__fullStroke = stroke_path.createStroke(path)

        # The dotted stroke (when not connected to anything)
        stroke_path.setDashPattern(Qt.DotLine)
        self.__dottedStroke = stroke_path.createStroke(path)

        if self.anchored:
            assert self.__fullStroke is not None
            self.setPath(self.__fullStroke)
            self.__shadow.setPath(self.__fullStroke)
            brush = self.connectedHoverBrush if self.__hover else self.connectedBrush
            self.setBrush(brush)
        else:
            assert self.__dottedStroke is not None
            self.setPath(self.__dottedStroke)
            self.__shadow.setPath(self.__dottedStroke)
            brush = self.normalHoverBrush if self.__hover else self.normalBrush
            self.setBrush(brush)

    def anchorPath(self):
        # type: () -> QPainterPath
        """
        Return the anchor path (:class:`QPainterPath`). This is a curve on
        which the anchor points lie.
        """
        return QPainterPath(self.__anchorPath)

    def setAnchored(self, anchored):
        # type: (bool) -> None
        """
        Set the items anchored state. When ``False`` the item draws it self
        with a dotted stroke.
        """
        self.anchored = anchored
        if anchored:
            self.setPath(self.__fullStroke)
            self.__shadow.setPath(self.__fullStroke)
            hover = self.__hover and len(self.__points) > 1  # a stylistic choice
            brush = self.connectedHoverBrush if hover else self.connectedBrush
            self.setBrush(brush)
        else:
            self.setPath(self.__dottedStroke)
            self.__shadow.setPath(self.__dottedStroke)
            brush = self.normalHoverBrush if self.__hover else self.normalBrush
            self.setBrush(brush)

    def setConnectionHint(self, hint=None):
        """
        Set the connection hint. This can be used to indicate if
        a connection can be made or not.

        """
        raise NotImplementedError

    def count(self):
        # type: () -> int
        """
        Return the number of anchor points.
        """
        return len(self.__points)

    def addAnchor(self, anchor, position=0.5):
        # type: (AnchorPoint, float) -> int
        """
        Add a new :class:`AnchorPoint` to this item and return it's index.

        The `position` specifies where along the `anchorPath` is the new
        point inserted.

        """
        return self.insertAnchor(self.count(), anchor, position)

    def insertAnchor(self, index, anchor, position=0.5):
        # type: (int, AnchorPoint, float) -> int
        """
        Insert a new :class:`AnchorPoint` at `index`.

        See also
        --------
        NodeAnchorItem.addAnchor

        """
        if anchor in self.__points:
            raise ValueError("%s already added." % anchor)

        self.__points.insert(index, anchor)
        self.__pointPositions.insert(index, position)

        anchor.setParentItem(self)
        anchor.setPos(self.__anchorPath.pointAtPercent(position))
        anchor.destroyed.connect(self.__onAnchorDestroyed)

        self.__updatePositions()

        self.setAnchored(bool(self.__points))

        hover = self.__hover and len(self.__points) > 1  # a stylistic choice
        anchor.setHoverState(hover)

        return index

    def removeAnchor(self, anchor):
        # type: (AnchorPoint) -> None
        """
        Remove and delete the anchor point.
        """
        anchor = self.takeAnchor(anchor)

        anchor.hide()
        anchor.setParentItem(None)
        anchor.deleteLater()

    def takeAnchor(self, anchor):
        # type: (AnchorPoint) -> AnchorPoint
        """
        Remove the anchor but don't delete it.
        """
        index = self.__points.index(anchor)

        del self.__points[index]
        del self.__pointPositions[index]

        anchor.destroyed.disconnect(self.__onAnchorDestroyed)

        self.__updatePositions()

        self.setAnchored(bool(self.__points))

        return anchor

    def __onAnchorDestroyed(self, anchor):
        # type: (QObject) -> None
        try:
            index = self.__points.index(anchor)
        except ValueError:
            return

        del self.__points[index]
        del self.__pointPositions[index]

    def anchorPoints(self):
        # type: () -> List[AnchorPoint]
        """
        Return a list of anchor points.
        """
        return list(self.__points)

    def anchorPoint(self, index):
        # type: (int) -> AnchorPoint
        """
        Return the anchor point at `index`.
        """
        return self.__points[index]

    def setAnchorPositions(self, positions):
        # type: (Iterable[float]) -> None
        """
        Set the anchor positions in percentages (0..1) along the path curve.
        """
        if self.__pointPositions != positions:
            self.__pointPositions = list(positions)

            self.__updatePositions()

    def anchorPositions(self):
        # type: () -> List[float]
        """
        Return the positions of anchor points as a list of floats where
        each float is between 0 and 1 and specifies where along the anchor
        path does the point lie (0 is at start 1 is at the end).
        """
        return list(self.__pointPositions)

    def shape(self):
        # type: () -> QPainterPath
        if self.__shape is not None:
            return QPainterPath(self.__shape)
        else:
            return super().shape()

    def boundingRect(self):
        if self.__shape is not None:
            return self.__shape.controlPointRect()
        else:
            return GraphicsPathObject.boundingRect(self)

    def hoverEnterEvent(self, event):
        self.__hover = True
        brush = self.connectedHoverBrush if self.anchored else self.normalHoverBrush
        self.setBrush(brush)
        self.__updateShadowState()
        return super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.__hover = False
        brush = self.connectedBrush if self.anchored else self.normalBrush
        self.setBrush(brush)
        self.__updateShadowState()
        return super().hoverLeaveEvent(event)

    def setAnimationEnabled(self, enabled):
        # type: (bool) -> None
        """
        Set the anchor animation enabled.
        """
        if self.__animationEnabled != enabled:
            self.__animationEnabled = enabled

    def __updateShadowState(self):
        # type: () -> None
        radius = 5 if self.__hover else 0

        if radius != 0 and not self.shadow.isEnabled():
            self.shadow.setEnabled(True)

        if self.__animationEnabled:
            if self.__blurAnimation.state() == QPropertyAnimation.Running:
                self.__blurAnimation.pause()

            self.__blurAnimation.setStartValue(self.shadow.blurRadius())
            self.__blurAnimation.setEndValue(radius)
            self.__blurAnimation.start()
        else:
            self.shadow.setBlurRadius(radius)

        for anchor in self.anchorPoints():
            anchor.setHoverState(self.__hover)

    def __updatePositions(self):
        # type: () -> None
        """Update anchor points positions.
        """
        for point, t in zip(self.__points, self.__pointPositions):
            pos = self.__anchorPath.pointAtPercent(t)
            point.setPos(pos)

    def __on_finished(self):
        # type: () -> None
        if self.shadow.blurRadius() == 0:
            self.shadow.setEnabled(False)


class SourceAnchorItem(NodeAnchorItem):
    """
    A source anchor item
    """
    pass


class SinkAnchorItem(NodeAnchorItem):
    """
    A sink anchor item.
    """
    pass


def standard_icon(standard_pixmap):
    # type: (QStyle.StandardPixmap) -> QIcon
    """
    Return return the application style's standard icon for a
    `QStyle.StandardPixmap`.
    """
    style = QApplication.instance().style()
    return style.standardIcon(standard_pixmap)


class GraphicsIconItem(QGraphicsWidget):
    """
    A graphics item displaying an :class:`QIcon`.
    """
    def __init__(self, parent=None, icon=QIcon(), iconSize=QSize(), **kwargs):
        # type: (Optional[QGraphicsItem], QIcon, QSize, Any) -> None
        super().__init__(parent, **kwargs)
        self.setFlag(QGraphicsItem.ItemUsesExtendedStyleOption, True)

        if icon is None:
            icon = QIcon()

        if iconSize is None or iconSize.isNull():
            style = QApplication.instance().style()
            size = style.pixelMetric(style.PM_LargeIconSize)
            iconSize = QSize(size, size)

        self.__transformationMode = Qt.SmoothTransformation

        self.__iconSize = QSize(iconSize)
        self.__icon = QIcon(icon)

        self.anim = QPropertyAnimation(self, b"opacity")
        self.anim.setDuration(350)
        self.anim.setStartValue(1)
        self.anim.setKeyValueAt(0.5, 0)
        self.anim.setEndValue(1)
        self.anim.setEasingCurve(QEasingCurve.OutQuad)
        self.anim.setLoopCount(5)

    def setIcon(self, icon):
        # type: (QIcon) -> None
        """
        Set the icon (:class:`QIcon`).
        """
        if self.__icon != icon:
            self.__icon = QIcon(icon)
            self.update()

    def icon(self):
        # type: () -> QIcon
        """
        Return the icon (:class:`QIcon`).
        """
        return QIcon(self.__icon)

    def setIconSize(self, size):
        # type: (QSize) -> None
        """
        Set the icon (and this item's) size (:class:`QSize`).
        """
        if self.__iconSize != size:
            self.prepareGeometryChange()
            self.__iconSize = QSize(size)
            self.update()

    def iconSize(self):
        # type: () -> QSize
        """
        Return the icon size (:class:`QSize`).
        """
        return QSize(self.__iconSize)

    def setTransformationMode(self, mode):
        # type: (Qt.TransformationMode) -> None
        """
        Set pixmap transformation mode. (`Qt.SmoothTransformation` or
        `Qt.FastTransformation`).

        """
        if self.__transformationMode != mode:
            self.__transformationMode = mode
            self.update()

    def transformationMode(self):
        # type: () -> Qt.TransformationMode
        """
        Return the pixmap transformation mode.
        """
        return self.__transformationMode

    def boundingRect(self):
        # type: () -> QRectF
        return QRectF(0, 0, self.__iconSize.width(), self.__iconSize.height())

    def paint(self, painter, option, widget=None):
        # type: (QPainter, QStyleOptionGraphicsItem, Optional[QWidget]) -> None
        if not self.__icon.isNull():
            if option.state & QStyle.State_Selected:
                mode = QIcon.Selected
            elif option.state & QStyle.State_Enabled:
                mode = QIcon.Normal
            elif option.state & QStyle.State_Active:
                mode = QIcon.Active
            else:
                mode = QIcon.Disabled

            w, h = self.__iconSize.width(), self.__iconSize.height()
            target = QRect(0, 0, w, h)
            painter.setRenderHint(
                QPainter.SmoothPixmapTransform,
                self.__transformationMode == Qt.SmoothTransformation
            )
            self.__icon.paint(painter, target, Qt.AlignCenter, mode)


class NameTextItem(QGraphicsTextItem):
    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None
        super().__init__(*args, **kwargs)
        self.__selected = False
        self.__palette = None  # type: Optional[QPalette]
        self.__content = ""

    def paint(self, painter, option, widget=None):
        # type: (QPainter, QStyleOptionGraphicsItem, Optional[QWidget]) -> None
        if self.__selected:
            painter.save()
            painter.setPen(QPen(Qt.NoPen))
            painter.setBrush(self.palette().color(QPalette.Highlight))
            doc = self.document()
            margin = doc.documentMargin()
            painter.translate(margin, margin)
            offset = min(margin, 2)
            for line in self._lines(doc):
                rect = line.naturalTextRect()
                painter.drawRoundedRect(
                    rect.adjusted(-offset, -offset, offset, offset),
                    3, 3
                )

            painter.restore()

        super().paint(painter, option, widget)

    def _blocks(self, doc):
        # type: (QTextDocument) -> Iterable[QTextBlock]
        block = doc.begin()
        while block != doc.end():
            yield block
            block = block.next()

    def _lines(self, doc):
        # type: (QTextDocument) -> Iterable[QTextLine]
        for block in self._blocks(doc):
            blocklayout = block.layout()
            for i in range(blocklayout.lineCount()):
                yield blocklayout.lineAt(i)

    def setSelectionState(self, state):
        # type: (bool) -> None
        if self.__selected != state:
            self.__selected = state
            self.__updateDefaultTextColor()
            self.update()

    def setPalette(self, palette):
        # type: (QPalette) -> None
        if self.__palette != palette:
            self.__palette = QPalette(palette)
            self.__updateDefaultTextColor()
            self.update()

    def palette(self):
        # type: () -> QPalette
        if self.__palette is None:
            scene = self.scene()
            if scene is not None:
                return scene.palette()
            else:
                return QPalette()
        else:
            return QPalette(self.__palette)

    def __updateDefaultTextColor(self):
        # type: () -> None
        if self.__selected:
            role = QPalette.HighlightedText
        else:
            role = QPalette.WindowText
        self.setDefaultTextColor(self.palette().color(role))

    def setHtml(self, contents):
        # type: (str) -> None
        if contents != self.__content:
            self.__content = contents
            super().setHtml(contents)


class NodeItem(QGraphicsWidget):
    """
    An widget node item in the canvas.
    """

    #: Signal emitted when the scene position of the node has changed.
    positionChanged = Signal()

    #: Signal emitted when the geometry of the channel anchors changes.
    anchorGeometryChanged = Signal()

    #: Signal emitted when the item has been activated (by a mouse double
    #: click or a keyboard)
    activated = Signal()

    #: The item is under the mouse.
    hovered = Signal()

    #: Span of the anchor in degrees
    ANCHOR_SPAN_ANGLE = 90

    #: Z value of the item
    Z_VALUE = 100

    def __init__(self, widget_description=None, parent=None, **kwargs):
        # type: (WidgetDescription, QGraphicsItem, Any) -> None
        self.__boundingRect = None  # type: Optional[QRectF]
        super().__init__(parent, **kwargs)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsFocusable, True)

        self.mousePressTime = QTime()
        self.mousePressTime.start()

        self.__title = ""
        self.__processingState = 0
        self.__progress = -1.
        self.__statusMessage = ""
        self.__renderedText = ""

        self.__error = None    # type: Optional[str]
        self.__warning = None  # type: Optional[str]
        self.__info = None     # type: Optional[str]
        self.__messages = {}  # type: Dict[Any, UserMessage]
        self.__anchorLayout = None
        self.__animationEnabled = False

        self.setZValue(self.Z_VALUE)

        shape_rect = QRectF(-24, -24, 48, 48)

        self.shapeItem = NodeBodyItem(self)
        self.shapeItem.setShapeRect(shape_rect)
        self.shapeItem.setAnimationEnabled(self.__animationEnabled)

        # Rect for widget's 'ears'.
        anchor_rect = QRectF(-31, -31, 62, 62)
        self.inputAnchorItem = SinkAnchorItem(self)
        input_path = QPainterPath()
        start_angle = 180 - self.ANCHOR_SPAN_ANGLE / 2
        input_path.arcMoveTo(anchor_rect, start_angle)
        input_path.arcTo(anchor_rect, start_angle, self.ANCHOR_SPAN_ANGLE)
        self.inputAnchorItem.setAnchorPath(input_path)
        self.inputAnchorItem.setAnimationEnabled(self.__animationEnabled)

        self.outputAnchorItem = SourceAnchorItem(self)
        output_path = QPainterPath()
        start_angle = self.ANCHOR_SPAN_ANGLE / 2
        output_path.arcMoveTo(anchor_rect, start_angle)
        output_path.arcTo(anchor_rect, start_angle, - self.ANCHOR_SPAN_ANGLE)
        self.outputAnchorItem.setAnchorPath(output_path)
        self.outputAnchorItem.setAnimationEnabled(self.__animationEnabled)

        self.inputAnchorItem.hide()
        self.outputAnchorItem.hide()

        # Title caption item
        self.captionTextItem = NameTextItem(self)

        self.captionTextItem.setPlainText("")
        self.captionTextItem.setPos(0, 33)

        def iconItem(standard_pixmap):
            # type: (QStyle.StandardPixmap) -> GraphicsIconItem
            item = GraphicsIconItem(
                self,
                icon=standard_icon(standard_pixmap),
                iconSize=QSize(16, 16)
            )
            item.hide()
            return item

        self.errorItem = iconItem(QStyle.SP_MessageBoxCritical)
        self.warningItem = iconItem(QStyle.SP_MessageBoxWarning)
        self.infoItem = iconItem(QStyle.SP_MessageBoxInformation)

        self.prepareGeometryChange()
        self.__boundingRect = None

        if widget_description is not None:
            self.setWidgetDescription(widget_description)

    @classmethod
    def from_node(cls, node):
        """
        Create an :class:`NodeItem` instance and initialize it from a
        :class:`SchemeNode` instance.

        """
        self = cls()
        self.setWidgetDescription(node.description)
#        self.setCategoryDescription(node.category)
        return self

    @classmethod
    def from_node_meta(cls, meta_description):
        """
        Create an `NodeItem` instance from a node meta description.
        """
        self = cls()
        self.setWidgetDescription(meta_description)
        return self

    # TODO: Remove the set[Widget|Category]Description. The user should
    # handle setting of icons, title, ...
    def setWidgetDescription(self, desc):
        # type: (WidgetDescription) -> None
        """
        Set widget description.
        """
        self.widget_description = desc
        if desc is None:
            return

        icon = icon_loader.from_description(desc).get(desc.icon)
        if icon:
            self.setIcon(icon)

        if not self.title():
            self.setTitle(desc.name)

        if desc.inputs:
            self.inputAnchorItem.show()
        if desc.outputs:
            self.outputAnchorItem.show()

        tooltip = NodeItem_toolTipHelper(self)
        self.setToolTip(tooltip)

    def setWidgetCategory(self, desc):
        # type: (CategoryDescription) -> None
        """
        Set the widget category.
        """
        self.category_description = desc
        if desc and desc.background:
            background = NAMED_COLORS.get(desc.background, desc.background)
            color = QColor(background)
            if color.isValid():
                self.setColor(color)

    def setIcon(self, icon):
        # type: (QIcon) -> None
        """
        Set the node item's icon (:class:`QIcon`).
        """
        self.icon_item = GraphicsIconItem(
            self.shapeItem, icon=icon, iconSize=QSize(36, 36)
        )
        self.icon_item.setPos(-18, -18)

    def setColor(self, color, selectedColor=None):
        # type: (QColor, Optional[QColor]) -> None
        """
        Set the widget color.
        """
        if selectedColor is None:
            selectedColor = saturated(color, 150)
        palette = create_palette(color, selectedColor)
        self.shapeItem.setPalette(palette)

    def setTitle(self, title):
        # type: (str) -> None
        """
        Set the node title. The title text is displayed at the bottom of the
        node.
        """
        if self.__title != title:
            self.__title = title
            self.__updateTitleText()

    def title(self):
        # type: () -> str
        """
        Return the node title.
        """
        return self.__title

    title_ = Property(str, fget=title, fset=setTitle,
                      doc="Node title text.")

    def setAnimationEnabled(self, enabled):
        # type: (bool) -> None
        """
        Set the node animation enabled state.
        """
        if self.__animationEnabled != enabled:
            self.__animationEnabled = enabled
            self.shapeItem.setAnimationEnabled(enabled)
            self.outputAnchorItem.setAnimationEnabled(self.__animationEnabled)
            self.inputAnchorItem.setAnimationEnabled(self.__animationEnabled)

    def animationEnabled(self):
        # type: () -> bool
        """
        Are node animations enabled.
        """
        return self.__animationEnabled

    def setProcessingState(self, state):
        # type: (int) -> None
        """
        Set the node processing state i.e. the node is processing
        (is busy) or is idle.
        """
        if self.__processingState != state:
            self.__processingState = state
            self.shapeItem.setProcessingState(state)
            if not state:
                # Clear the progress meter.
                self.setProgress(-1)
                if self.__animationEnabled:
                    self.shapeItem.ping()

    def processingState(self):
        # type: () -> int
        """
        The node processing state.
        """
        return self.__processingState

    processingState_ = Property(int, fget=processingState,
                                fset=setProcessingState)

    def setProgress(self, progress):
        # type: (float) -> None
        """
        Set the node work progress state (number between 0 and 100).
        """
        if progress is None or progress < 0 or not self.__processingState:
            progress = -1.

        progress = max(min(progress, 100.), -1.)
        if self.__progress != progress:
            self.__progress = progress
            self.shapeItem.setProgress(progress)
            self.__updateTitleText()

    def progress(self):
        # type: () -> float
        """
        Return the node work progress state.
        """
        return self.__progress

    progress_ = Property(float, fget=progress, fset=setProgress,
                         doc="Node progress state.")

    def setStatusMessage(self, message):
        # type: (str) -> None
        """
        Set the node status message text.

        This text is displayed below the node's title.
        """
        if self.__statusMessage != message:
            self.__statusMessage = message
            self.__updateTitleText()

    def statusMessage(self):
        # type: () -> str
        return self.__statusMessage

    def setStateMessage(self, message):
        # type: (UserMessage) -> None
        """
        Set a state message to display over the item.

        Parameters
        ----------
        message : UserMessage
            Message to display. `message.severity` is used to determine
            the icon and `message.contents` is used as a tool tip.

        """
        self.__messages[message.message_id] = message
        self.__updateMessages()

    def setErrorMessage(self, message):
        if self.__error != message:
            self.__error = message
            self.__updateMessages()

    def setWarningMessage(self, message):
        if self.__warning != message:
            self.__warning = message
            self.__updateMessages()

    def setInfoMessage(self, message):
        if self.__info != message:
            self.__info = message
            self.__updateMessages()

    def newInputAnchor(self):
        # type: () -> AnchorPoint
        """
        Create and return a new input :class:`AnchorPoint`.
        """
        if not (self.widget_description and self.widget_description.inputs):
            raise ValueError("Widget has no inputs.")

        anchor = AnchorPoint()
        self.inputAnchorItem.addAnchor(anchor, position=1.0)

        positions = self.inputAnchorItem.anchorPositions()
        positions = uniform_linear_layout_trunc(positions)
        self.inputAnchorItem.setAnchorPositions(positions)

        return anchor

    def removeInputAnchor(self, anchor):
        # type: (AnchorPoint) -> None
        """
        Remove input anchor.
        """
        self.inputAnchorItem.removeAnchor(anchor)

        positions = self.inputAnchorItem.anchorPositions()
        positions = uniform_linear_layout_trunc(positions)
        self.inputAnchorItem.setAnchorPositions(positions)

    def newOutputAnchor(self):
        # type: () -> AnchorPoint
        """
        Create and return a new output :class:`AnchorPoint`.
        """
        if not (self.widget_description and self.widget_description.outputs):
            raise ValueError("Widget has no outputs.")

        anchor = AnchorPoint(self)
        self.outputAnchorItem.addAnchor(anchor, position=1.0)

        positions = self.outputAnchorItem.anchorPositions()
        positions = uniform_linear_layout_trunc(positions)
        self.outputAnchorItem.setAnchorPositions(positions)

        return anchor

    def removeOutputAnchor(self, anchor):
        # type: (AnchorPoint) -> None
        """
        Remove output anchor.
        """
        self.outputAnchorItem.removeAnchor(anchor)

        positions = self.outputAnchorItem.anchorPositions()
        positions = uniform_linear_layout_trunc(positions)
        self.outputAnchorItem.setAnchorPositions(positions)

    def inputAnchors(self):
        # type: () -> List[AnchorPoint]
        """
        Return a list of all input anchor points.
        """
        return self.inputAnchorItem.anchorPoints()

    def outputAnchors(self):
        # type: () -> List[AnchorPoint]
        """
        Return a list of all output anchor points.
        """
        return self.outputAnchorItem.anchorPoints()

    def setAnchorRotation(self, angle):
        # type: (float) -> None
        """
        Set the anchor rotation.
        """
        self.inputAnchorItem.setRotation(angle)
        self.outputAnchorItem.setRotation(angle)
        self.anchorGeometryChanged.emit()

    def anchorRotation(self):
        # type: () -> float
        """
        Return the anchor rotation.
        """
        return self.inputAnchorItem.rotation()

    def boundingRect(self):
        # type: () -> QRectF
        # TODO: Important because of this any time the child
        # items change geometry the self.prepareGeometryChange()
        # needs to be called.
        if self.__boundingRect is None:
            self.__boundingRect = self.childrenBoundingRect()
        return QRectF(self.__boundingRect)

    def shape(self):
        # type: () -> QPainterPath
        # Shape for mouse hit detection.
        # TODO: Should this return the union of all child items?
        return self.shapeItem.shape()

    def __updateTitleText(self):
        # type: () -> None
        """
        Update the title text item.
        """
        text = ['<div align="center">%s' % escape(self.title())]

        status_text = []

        progress_included = False
        if self.__statusMessage:
            msg = escape(self.__statusMessage)
            format_fields = dict(parse_format_fields(msg))
            if "progress" in format_fields and len(format_fields) == 1:
                # Insert progress into the status text format string.
                spec, _ = format_fields["progress"]
                if spec is not None:
                    progress_included = True
                    progress_str = "{0:.0f}%".format(self.progress())
                    status_text.append(msg.format(progress=progress_str))
            else:
                status_text.append(msg)

        if self.progress() >= 0 and not progress_included:
            status_text.append("%i%%" % int(self.progress()))

        if status_text:
            text += ["<br/>",
                     '<span style="font-style: italic">',
                     "<br/>".join(status_text),
                     "</span>"]
        text += ["</div>"]
        text = "".join(text)
        if self.__renderedText != text:
            self.__renderedText = text
            # The NodeItems boundingRect could change.
            self.prepareGeometryChange()
            self.__boundingRect = None
            self.captionTextItem.setHtml(text)
            self.__layoutCaptionTextItem()

    def __layoutCaptionTextItem(self):
        self.prepareGeometryChange()
        self.__boundingRect = None
        self.captionTextItem.document().adjustSize()
        width = self.captionTextItem.textWidth()
        self.captionTextItem.setPos(-width / 2.0, 33)

    def __updateMessages(self):
        # type: () -> None
        """
        Update message items (position, visibility and tool tips).
        """
        items = [self.errorItem, self.warningItem, self.infoItem]

        messages = list(self.__messages.values()) + [
            UserMessage(self.__error or "", UserMessage.Error,
                        message_id="_error"),
            UserMessage(self.__warning or "", UserMessage.Warning,
                        message_id="_warn"),
            UserMessage(self.__info or "", UserMessage.Info,
                        message_id="_info"),
        ]
        key = attrgetter("severity")
        messages = groupby(sorted(messages, key=key, reverse=True), key=key)

        for (_, message_g), item in zip(messages, items):
            message = "<br/>".join(m.contents for m in message_g if m.contents)
            item.setVisible(bool(message))
            if bool(message):
                item.anim.start(QPropertyAnimation.KeepWhenStopped)
            item.setToolTip(message or "")

        shown = [item for item in items if item.isVisible()]
        count = len(shown)
        if count:
            spacing = 3
            rects = [item.boundingRect() for item in shown]
            width = sum(rect.width() for rect in rects)
            width += spacing * max(0, count - 1)
            height = max(rect.height() for rect in rects)
            origin = self.shapeItem.boundingRect().top() - spacing - height
            origin = QPointF(-width / 2, origin)
            for item, rect in zip(shown, rects):
                item.setPos(origin)
                origin = origin + QPointF(rect.width() + spacing, 0)

    def mousePressEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> None
        if self.mousePressTime.elapsed() < QApplication.doubleClickInterval():
            # Double-click triggers two mouse press events and a double-click event.
            # Ignore the second mouse press event (causes widget's node relocation with
            # Logitech's Smart Move).
            event.ignore()
        else:
            self.mousePressTime.restart()
            if self.shapeItem.path().contains(event.pos()):
                super().mousePressEvent(event)
            else:
                event.ignore()

    def mouseDoubleClickEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> None
        if self.shapeItem.path().contains(event.pos()):
            super().mouseDoubleClickEvent(event)
            QTimer.singleShot(0, self.activated.emit)
        else:
            event.ignore()

    def contextMenuEvent(self, event):
        # type: (QGraphicsSceneContextMenuEvent) -> None
        if self.shapeItem.path().contains(event.pos()):
            super().contextMenuEvent(event)
        else:
            event.ignore()

    def changeEvent(self, event):
        if event.type() == QEvent.PaletteChange:
            self.__updatePalette()
        elif event.type() == QEvent.FontChange:
            self.__updateFont()
        super().changeEvent(event)

    def itemChange(self, change, value):
        # type: (QGraphicsItem.GraphicsItemChange, Any) -> Any
        if change == QGraphicsItem.ItemSelectedChange:
            self.shapeItem.setSelected(value)
            self.captionTextItem.setSelectionState(value)
        elif change == QGraphicsItem.ItemPositionHasChanged:
            self.positionChanged.emit()

        return super().itemChange(change, value)

    def __updatePalette(self):
        # type: () -> None
        palette = self.palette()
        self.captionTextItem.setPalette(palette)

    def __updateFont(self):
        # type: () -> None
        self.prepareGeometryChange()
        self.captionTextItem.setFont(self.font())
        self.__layoutCaptionTextItem()


TOOLTIP_TEMPLATE = """\
<html>
<head>
<style type="text/css">
{style}
</style>
</head>
<body>
{tooltip}
</body>
</html>
"""


def NodeItem_toolTipHelper(node, links_in=[], links_out=[]):
    # type: (NodeItem, List[LinkItem], List[LinkItem]) -> str
    """
    A helper function for constructing a standard tooltip for the node
    in on the canvas.

    Parameters:
    ===========
    node : NodeItem
        The node item instance.
    links_in : list of LinkItem instances
        A list of input links for the node.
    links_out : list of LinkItem instances
        A list of output links for the node.

    """
    desc = node.widget_description
    channel_fmt = "<li>{0}</li>"

    title_fmt = "<b>{title}</b><hr/>"
    title = title_fmt.format(title=escape(node.title()))
    inputs_list_fmt = "Inputs:<ul>{inputs}</ul><hr/>"
    outputs_list_fmt = "Outputs:<ul>{outputs}</ul>"
    if desc.inputs:
        inputs = [channel_fmt.format(inp.name) for inp in desc.inputs]
        inputs = inputs_list_fmt.format(inputs="".join(inputs))
    else:
        inputs = "No inputs<hr/>"

    if desc.outputs:
        outputs = [channel_fmt.format(out.name) for out in desc.outputs]
        outputs = outputs_list_fmt.format(outputs="".join(outputs))
    else:
        outputs = "No outputs"

    tooltip = title + inputs + outputs
    style = "ul { margin-top: 1px; margin-bottom: 1px; }"
    return TOOLTIP_TEMPLATE.format(style=style, tooltip=tooltip)


def parse_format_fields(format_str):
    # type: (str) -> List[Tuple[str, Tuple[Optional[str], Optional[str]]]]
    formatter = string.Formatter()
    format_fields = [(field, (spec, conv))
                     for _, field, spec, conv in formatter.parse(format_str)
                     if field is not None]
    return format_fields

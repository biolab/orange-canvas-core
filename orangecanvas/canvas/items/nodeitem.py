"""
=========
Node Item
=========

"""
import math
import typing
import string

from operator import attrgetter
from itertools import groupby
from xml.sax.saxutils import escape

from typing import Dict, Any, Optional, List, Iterable, Tuple, Union

from AnyQt.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QGraphicsWidget,
    QGraphicsDropShadowEffect, QStyle, QApplication, QGraphicsSceneMouseEvent,
    QGraphicsSceneContextMenuEvent, QStyleOptionGraphicsItem, QWidget,
    QGraphicsEllipseItem
)
from AnyQt.QtGui import (
    QPen, QBrush, QColor, QPalette, QIcon, QPainter, QPainterPath,
    QPainterPathStroker, QConicalGradient,
    QTransform)
from AnyQt.QtCore import (
    Qt, QEvent, QPointF, QRectF, QRect, QSize, QTime, QTimer,
    QPropertyAnimation, QEasingCurve, QObject, QVariantAnimation,
    QParallelAnimationGroup)
from AnyQt.QtCore import pyqtSignal as Signal, pyqtProperty as Property
from PyQt5.QtCore import pyqtProperty

from .graphicspathobject import GraphicsPathObject
from .graphicstextitem import GraphicsTextItem
from .utils import saturated, radial_gradient

from ...scheme.node import UserMessage
from ...registry import NAMED_COLORS, WidgetDescription, CategoryDescription, \
    InputSignal, OutputSignal
from ...resources import icon_loader
from .utils import uniform_linear_layout_trunc
from ...utils import set_flag
from ...utils.mathutils import interp1d

if typing.TYPE_CHECKING:
    from ...registry import WidgetDescription
    # from . import LinkItem


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
        self.__spinnerValue = 0
        self.__animationEnabled = False
        self.__isSelected = False
        self.__hover = False
        self.__shapeRect = QRectF(-10, -10, 20, 20)
        self.palette = QPalette()
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
        self.__blurAnimation = QPropertyAnimation(
            self.shadow, b"blurRadius", self, duration=100
        )
        self.__blurAnimation.finished.connect(self.__on_finished)

        self.__pingAnimation = QPropertyAnimation(
            self, b"scale", self, duration=250
        )
        self.__pingAnimation.setKeyValues([(0.0, 1.0), (0.5, 1.1), (1.0, 1.0)])

        self.__spinnerAnimation = QVariantAnimation(
            self, startValue=0, endValue=360, duration=2000, loopCount=-1,
        )
        self.__spinnerAnimation.valueChanged.connect(self.update)
        self.__spinnerStartTimer = QTimer(
            self, interval=3000, singleShot=True,
            timeout=self.__progressTimeout
        )

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
            self.stopSpinner()
            if not state and self.__animationEnabled:
                self.ping()
            if state:
                self.__spinnerStartTimer.start()
            else:
                self.__spinnerStartTimer.stop()

    def setProgress(self, progress):
        # type: (float) -> None
        """
        Set the progress indicator state of the node. `progress` should
        be a number between 0 and 100.
        """
        if self.__progress != progress:
            self.__progress = progress
            if self.__progress >= 0:
                self.stopSpinner()
            self.update()
            self.__spinnerStartTimer.start()

    def ping(self):
        # type: () -> None
        """
        Trigger a 'ping' animation.
        """
        animation_restart(self.__pingAnimation)

    def startSpinner(self):
        self.__spinnerAnimation.start()
        self.__spinnerStartTimer.stop()
        self.update()

    def stopSpinner(self):
        self.__spinnerAnimation.stop()
        self.__spinnerStartTimer.stop()
        self.update()

    def __progressTimeout(self):
        if self.__processingState:
            self.startSpinner()

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
        if self.__progress >= 0 or self.__processingState \
                or self.__spinnerAnimation.state() == QVariantAnimation.Running:
            # Draw the progress meter over the shape.
            # Set the clip to shape so the meter does not overflow the shape.
            rect = self.__shapeRect
            painter.save()
            painter.setClipPath(self.shape(), Qt.ReplaceClip)
            color = self.palette.color(QPalette.ButtonText)
            pen = QPen(color, 5)
            painter.setPen(pen)
            spinner = self.__spinnerAnimation
            indeterminate = spinner.state() != QVariantAnimation.Stopped
            if indeterminate:
                draw_spinner(painter, rect, 5, color,
                             self.__spinnerAnimation.currentValue())
            else:
                span = max(1, int(360 * self.__progress / 100))
                draw_progress(painter, rect, 5, color, span)
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

        if self.__animationEnabled:
            if self.__blurAnimation.state() == QPropertyAnimation.Running:
                self.__blurAnimation.stop()

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
        self.__styleState = QStyle.State(0)
        self.__linkState = LinkItem.NoState
        super().__init__(parent)
        self.setAcceptedMouseButtons(Qt.NoButton)
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
        state = set_flag(self.__styleState, QStyle.State_MouseOver, state)
        self.setStyleState(state)

    def setStyleState(self, state: QStyle.State):
        if self.__styleState != state:
            self.__styleState = state
            self.update()

    def setLinkState(self, state: 'LinkItem.State'):
        if self.__linkState != state:
            self.__linkState = state
            self.update()

    def paint(self, painter, option, widget=None):
        # type: (QPainter, QStyleOptionGraphicsItem, Optional[QWidget]) -> None
        hover = self.__styleState & (QStyle.State_Selected | QStyle.State_MouseOver)
        brush = self.hoverBrush if hover else self.brush()
        if self.__linkState & (LinkItem.Pending | LinkItem.Invalidated):
            brush = QBrush(Qt.red)

        painter.setBrush(brush)
        painter.setPen(self.pen())
        painter.drawEllipse(self.rect())


def draw_spinner(painter, rect, penwidth, color, angle):
    # type: (QPainter, QRectF, int, QColor, int) -> None
    gradient = QConicalGradient()
    color2 = QColor(color)
    color2.setAlpha(0)

    stops = [
        (0.0, color),
        (1.0, color2),
    ]
    gradient.setStops(stops)
    gradient.setCoordinateMode(QConicalGradient.ObjectBoundingMode)
    gradient.setCenter(0.5, 0.5)
    gradient.setAngle(-angle)
    pen = QPen()
    pen.setCapStyle(Qt.RoundCap)
    pen.setWidthF(penwidth)
    pen.setBrush(gradient)
    painter.setPen(pen)
    painter.drawEllipse(rect)


def draw_progress(painter, rect, penwidth, color, angle):
    # type: (QPainter, QRectF, int, QColor, int) -> None
    painter.setPen(QPen(color, penwidth))
    painter.drawArc(rect, 90 * 16, -angle * 16)


class AnchorPoint(QGraphicsObject):
    """
    A anchor indicator on the :class:`NodeAnchorItem`.
    """

    #: Signal emitted when the item's scene position changes.
    scenePositionChanged = Signal(QPointF)

    #: Signal emitted when the item's `anchorDirection` changes.
    anchorDirectionChanged = Signal(QPointF)

    #: Signal emitted when anchor's Input/Output channel changes.
    signalChanged = Signal(QGraphicsObject)

    def __init__(
            self,
            parent: Optional[QGraphicsItem] = None,
            signal: Union[InputSignal, OutputSignal, None] = None,
            **kwargs
    ) -> None:
        super().__init__(parent, **kwargs)
        self.setFlag(QGraphicsItem.ItemIsFocusable)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        self.setFlag(QGraphicsItem.ItemHasNoContents, True)
        self.indicator = LinkAnchorIndicator(self)

        self.signal = signal
        self.__direction = QPointF()

        self.anim = QPropertyAnimation(self, b'pos', self)
        self.anim.setDuration(50)

    def setSignal(self, signal):
        if self.signal != signal:
            self.signal = signal
            self.signalChanged.emit(self)

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

    def setLinkState(self, state: 'LinkItem.State'):
        self.indicator.setLinkState(state)


def drawDashPattern(dashNum, spaceLen=2, lineLen=16):
    dashLen = (lineLen - spaceLen * (dashNum - 1)) / dashNum
    line = []
    for _ in range(dashNum - 1):
        line += [dashLen, spaceLen]
    line += [dashLen]
    return line


def matchDashPattern(l1, l2, spaceLen=2):
    if not l1 or not l2 or len(l1) == len(l2):
        return l1, l2

    if len(l2) < len(l1):
        l1, l2 = l2, l1
        reverse = True
    else:
        reverse = False

    l1d = len(l1) // 2 + 1
    l2d = len(l2) // 2 + 1

    if l1d == 1:  # base case
        dLen = l1[0]
        l1 = drawDashPattern(l2d, spaceLen=0, lineLen=dLen)
        return (l2, l1) if reverse else (l1, l2)

    d = math.gcd(l1d, l2d)
    if d > 1:  # split
        l1step = (l1d // d) * 2
        l2step = (l2d // d) * 2
        l1range = l1step - 1
        l2range = l2step - 1
        l1splits, l2splits = [], []
        for l1i, l2i in zip(range(0, len(l1), l1step), range(0, len(l2), l2step)):
            l1s = l1[l1i:(l1i+l1range)]
            l2s = l2[l2i:(l2i+l2range)]
            l1splits += [l1s]
            l2splits += [l2s]

    elif l1d % 2 == 0 and l2d % 2 != 0:  # split middle 2 lines into 3
        l11 = l1[:l1d-2]
        l1l = l1[l1d]
        l12 = l1[l1d+1:]

        l21 = l2[:l2d-3]
        l2l = l2[l2d-1]
        l22 = l2[l2d+2:]

        new_l11, new_l21 = matchDashPattern(l11, l21)
        new_l12, new_l22 = matchDashPattern(l12, l22)
        for new_l in (new_l11, new_l21):
            if new_l:
                new_l += [spaceLen]
        for new_l in (new_l12, new_l22):
            if new_l:
                new_l.insert(0, spaceLen)

        l1 = new_l11 + [l1l*2/3, 0, l1l/3, spaceLen, l1l/3, 0, l1l*2/3] + new_l12
        l2 = new_l21 + [l2l, spaceLen, l2l/2, 0, l2l/2, spaceLen, l2l] + new_l22
        return (l2, l1) if reverse else (l1, l2)

    elif l1d % 2 != 0 and l2d % 2 == 0:  # split line
        l11 = l1[:l1d - 2]
        mid = l1[l1d-1]
        l1m = [mid/2, 0, mid/2]
        l12 = l1[l1d+1:]

        l21 = l2[:l2d-3]
        l2m = l2[l2d-2:l2d+1]
        l22 = l2[l2d+2:]

        l1splits = [l11, l1m, l12]
        l2splits = [l21, l2m, l22]
    else:  # if l1d % 2 != 0 and l2d % 2 != 0
        l11 = l1[:l1d - 1]
        l1m = l1[l1d]
        l12 = l1[l1d + 2:]

        l21 = l2[:l2d - 1]
        l2m = l2[l2d]
        l22 = l2[l2d + 2:]

        l1splits = [l11, l1m, l12]
        l2splits = [l21, l2m, l22]

    l1 = []
    l2 = []
    for l1s, l2s in zip(l1splits, l2splits):
        new_l1, new_l2 = matchDashPattern(l1s, l2s)
        l1 += new_l1 + [spaceLen]
        l2 += new_l2 + [spaceLen]
    # drop trailing space
    l1 = l1[:-1]
    l2 = l2[:-1]
    return (l2, l1) if reverse else (l1, l2)


ANCHOR_TEXT_MARGIN = 4


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
        self.__anchorOpen = False
        self.__compatibleSignals = None
        self.__keepSignalsOpen = []

        # Does this item have any anchored links.
        self.anchored = False

        if isinstance(parent, NodeItem):
            self.__parentNodeItem = parent
        else:
            self.__parentNodeItem = None

        self.__anchorPath = QPainterPath()
        self.__points = []  # type: List[AnchorPoint]
        self.__uniformPointPositions = []  # type: List[float]
        self.__channelPointPositions = []  # type: List[float]
        self.__incompatible = False  # type: bool
        self.__signals = []  # type: List[Union[InputSignal, OutputSignal]]
        self.__signalLabels = []  # type: List[GraphicsTextItem]
        self.__signalLabelAnims = []  # type: List[QPropertyAnimation]

        self.__fullStroke = QPainterPath()
        self.__dottedStroke = QPainterPath()
        self.__channelStroke = QPainterPath()
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

        stroke_path = QPainterPathStroker()
        stroke_path.setCapStyle(Qt.RoundCap)
        stroke_path.setWidth(3)
        self.__pathStroker = stroke_path
        self.__interpDash = None
        self.__dashInterpFactor = 0
        self.__anchorPathAnim = QPropertyAnimation(self,
                                                   b"anchorDashInterpFactor",
                                                   self)
        self.__anchorPathAnim.setDuration(50)

        self.animGroup = QParallelAnimationGroup()
        self.animGroup.addAnimation(self.__anchorPathAnim)

    def setSignals(self, signals):
        self.__signals = signals
        self.setAnchorPath(self.__anchorPath)  # (re)instantiate anchor paths

        # TODO this is ugly
        alignLeft = isinstance(self, SourceAnchorItem)

        for s in signals:
            lbl = GraphicsTextItem(self)
            lbl.setAcceptedMouseButtons(Qt.NoButton)
            lbl.setAcceptHoverEvents(False)

            text = s.name
            lbl.setHtml('<div align="' + ('left' if alignLeft else 'right') +
                        '" style="font-size: small; background-color: palette(base);" >{0}</div>'
                        .format(text))

            cperc = self.__getChannelPercent(s)
            sigPos = self.__anchorPath.pointAtPercent(cperc)
            lblrect = lbl.boundingRect()

            transform = QTransform()
            transform.translate(sigPos.x(), sigPos.y())
            transform.translate(0, -lblrect.height() / 2)
            if not alignLeft:
                transform.translate(-lblrect.width() - ANCHOR_TEXT_MARGIN, 0)
            else:
                transform.translate(ANCHOR_TEXT_MARGIN, 0)

            lbl.setTransform(transform)
            lbl.setOpacity(0)
            self.__signalLabels.append(lbl)

            lblAnim = QPropertyAnimation(lbl, b'opacity', self)
            lblAnim.setDuration(50)
            self.animGroup.addAnimation(lblAnim)
            self.__signalLabelAnims.append(lblAnim)

    def setIncompatible(self, enabled):
        if self.__incompatible != enabled:
            self.__incompatible = enabled
            self.__updatePositions()

    def setKeepAnchorOpen(self, signal):
        if signal is None:
            self.__keepSignalsOpen = []
        elif not isinstance(signal, list):
            self.__keepSignalsOpen = [signal]
        else:
            self.__keepSignalsOpen = signal
        self.__updateLabels(self.__keepSignalsOpen)

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
        stroke_path.setWidth(3)

        # Match up dash patterns for animations
        dash6 = drawDashPattern(6)
        channelAnchor = drawDashPattern(len(self.__signals) or 1)
        fullAnchor = drawDashPattern(1)
        dash6, channelAnchor = matchDashPattern(dash6, channelAnchor)
        channelAnchor, fullAnchor = matchDashPattern(channelAnchor, fullAnchor)
        self.__unanchoredDash = dash6
        self.__channelDash = channelAnchor
        self.__anchoredDash = fullAnchor

        # The full stroke
        stroke_path.setDashPattern(fullAnchor)
        self.__fullStroke = stroke_path.createStroke(path)

        # The dotted stroke (when not connected to anything)
        stroke_path.setDashPattern(dash6)
        self.__dottedStroke = stroke_path.createStroke(path)

        # The channel stroke (when channels are open)
        stroke_path.setDashPattern(channelAnchor)
        self.__channelStroke = stroke_path.createStroke(path)

        if self.anchored:
            self.setPath(self.__fullStroke)
            self.__pathStroker.setDashPattern(self.__anchoredDash)
            self.__shadow.setPath(self.__fullStroke)
            brush = self.connectedHoverBrush if self.__hover else self.connectedBrush
            self.setBrush(brush)
        else:
            self.setPath(self.__dottedStroke)
            self.__pathStroker.setDashPattern(self.__unanchoredDash)
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

    def anchorOpen(self):
        return self.__anchorOpen

    @pyqtProperty(float)
    def anchorDashInterpFactor(self):
        return self.__dashInterpFactor

    @anchorDashInterpFactor.setter
    def anchorDashInterpFactor(self, value):
        self.__dashInterpFactor = value
        stroke_path = self.__pathStroker
        path = self.__anchorPath

        pattern = self.__interpDash(value)
        stroke_path.setDashPattern(pattern)
        stroke = stroke_path.createStroke(path)
        self.setPath(stroke)
        self.__shadow.setPath(stroke)

    def setAnchored(self, anchored):
        # type: (bool) -> None
        """
        Set the items anchored state. When ``False`` the item draws it self
        with a dotted stroke.
        """
        self.anchored = anchored
        if anchored:
            self.shadow.setEnabled(False)
            self.setBrush(self.connectedBrush)
        else:
            brush = self.normalHoverBrush if self.__hover else self.normalBrush
            self.setBrush(brush)
        self.__updatePositions()

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

    def addAnchor(self, anchor):
        # type: (AnchorPoint) -> int
        """
        Add a new :class:`AnchorPoint` to this item and return it's index.

        The `position` specifies where along the `anchorPath` is the new
        point inserted.

        """
        return self.insertAnchor(self.count(), anchor)

    def __updateAnchorSignalPosition(self, anchor):
        cperc = self.__getChannelPercent(anchor.signal)
        i = self.__points.index(anchor)
        self.__channelPointPositions[i] = cperc
        self.__updatePositions()

    def insertAnchor(self, index, anchor):
        # type: (int, AnchorPoint) -> int
        """
        Insert a new :class:`AnchorPoint` at `index`.

        See also
        --------
        NodeAnchorItem.addAnchor

        """
        if anchor in self.__points:
            raise ValueError("%s already added." % anchor)

        self.__points.insert(index, anchor)
        self.__uniformPointPositions.insert(index, 0)
        cperc = self.__getChannelPercent(anchor.signal)
        self.__channelPointPositions.insert(index, cperc)
        self.animGroup.addAnimation(anchor.anim)

        anchor.setParentItem(self)
        anchor.destroyed.connect(self.__onAnchorDestroyed)
        anchor.signalChanged.connect(self.__updateAnchorSignalPosition)

        positions = self.anchorPositions()
        positions = uniform_linear_layout_trunc(positions)

        if anchor.signal in self.__keepSignalsOpen or \
                self.__anchorOpen and self.__hover:
            perc = cperc
        else:
            perc = positions[index]
        pos = self.__anchorPath.pointAtPercent(perc)
        anchor.setPos(pos)

        self.setAnchorPositions(positions)

        self.setAnchored(bool(self.__points))

        hover_for_color = self.__hover and len(self.__points) > 1  # a stylistic choice
        anchor.setHoverState(hover_for_color)
        return index

    def removeAnchor(self, anchor):
        # type: (AnchorPoint) -> None
        """
        Remove and delete the anchor point.
        """
        anchor = self.takeAnchor(anchor)
        self.animGroup.removeAnimation(anchor.anim)

        anchor.hide()
        anchor.setParentItem(None)
        anchor.deleteLater()

        positions = self.anchorPositions()
        positions = uniform_linear_layout_trunc(positions)
        self.setAnchorPositions(positions)

    def takeAnchor(self, anchor):
        # type: (AnchorPoint) -> AnchorPoint
        """
        Remove the anchor but don't delete it.
        """
        index = self.__points.index(anchor)

        del self.__points[index]
        del self.__uniformPointPositions[index]
        del self.__channelPointPositions[index]

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
        del self.__uniformPointPositions[index]
        del self.__channelPointPositions[index]

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
        if self.__uniformPointPositions != positions:
            self.__uniformPointPositions = list(positions)
            self.__updatePositions()

    def anchorPositions(self):
        # type: () -> List[float]
        """
        Return the positions of anchor points as a list of floats where
        each float is between 0 and 1 and specifies where along the anchor
        path does the point lie (0 is at start 1 is at the end).
        """
        return list(self.__uniformPointPositions)

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

    def setHovered(self, enabled):
        self.__hover = enabled
        if enabled:
            brush = self.connectedHoverBrush if self.anchored else self.normalHoverBrush
        else:
            brush = self.connectedBrush if self.anchored else self.normalBrush
        self.setBrush(brush)
        self.__updateHoverState()

    def hoverEnterEvent(self, event):
        self.setHovered(True)
        return super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setHovered(False)
        return super().hoverLeaveEvent(event)

    def setAnimationEnabled(self, enabled):
        # type: (bool) -> None
        """
        Set the anchor animation enabled.
        """
        if self.__animationEnabled != enabled:
            self.__animationEnabled = enabled

    def signalAtPos(self, scenePos, signalsToFind=None):
        if signalsToFind is None:
            signalsToFind = self.__signals
        pos = self.mapFromScene(scenePos)

        def signalLengthToPos(s):
            perc = self.__getChannelPercent(s)
            p = self.__anchorPath.pointAtPercent(perc)
            return (p - pos).manhattanLength()

        return min(signalsToFind, key=signalLengthToPos)

    def __updateHoverState(self):
        self.__updateShadowState()
        self.__updatePositions()

        for indicator in self.anchorPoints():
            indicator.setHoverState(self.__hover)

    def __getChannelPercent(self, signal):
        if signal is None:
            return 0.5
        signals = self.__signals

        ci = signals.index(signal)
        gap_perc = 1 / 8
        seg_perc = (1 - (gap_perc * (len(signals) - 1))) / len(signals)
        return (ci * (gap_perc + seg_perc)) + seg_perc / 2

    def __updateShadowState(self):
        # type: () -> None
        radius = 5 if self.__hover else 0

        if radius != 0 and not self.shadow.isEnabled():
            self.shadow.setEnabled(True)

        if self.__animationEnabled:
            if self.__blurAnimation.state() == QPropertyAnimation.Running:
                self.__blurAnimation.stop()

            self.__blurAnimation.setStartValue(self.shadow.blurRadius())
            self.__blurAnimation.setEndValue(radius)
            self.__blurAnimation.start()
        else:
            self.shadow.setBlurRadius(radius)

    def setAnchorOpen(self, anchorOpen):
        self.__anchorOpen = anchorOpen
        self.__updatePositions()

    def setCompatibleSignals(self, compatibleSignals):
        self.__compatibleSignals = compatibleSignals
        self.__updatePositions()

    def __updateLabels(self, showSignals):
        for signal, label in zip(self.__signals, self.__signalLabels):
            if signal not in showSignals:
                opacity = 0
            elif self.__compatibleSignals is not None \
                    and signal not in self.__compatibleSignals:
                opacity = 0.65
            else:
                opacity = 1
            label.setOpacity(opacity)

    def __initializeAnimation(self, targetPoss, endDash, showSignals):
        anchorOpen = self.__anchorOpen
        # TODO if animation currently running, set start value/time accordingly
        for a, t in zip(self.__points, targetPoss):
            currPos = a.pos()
            a.anim.setStartValue(currPos)
            pos = self.__anchorPath.pointAtPercent(t)
            a.anim.setEndValue(pos)

        for sig, lbl, lblAnim in zip(self.__signals, self.__signalLabels, self.__signalLabelAnims):
            lblAnim.setStartValue(lbl.opacity())
            lblAnim.setEndValue(1 if sig in showSignals else 0)

        startDash = self.__pathStroker.dashPattern()
        self.__interpDash = interp1d(startDash, endDash)
        self.__anchorPathAnim.setStartValue(0)
        self.__anchorPathAnim.setEndValue(1)

    def __updatePositions(self):
        # type: () -> None
        """Update anchor points positions.
        """
        if self.__keepSignalsOpen or self.__anchorOpen and self.__hover:
            dashPattern = self.__channelDash
            stroke = self.__channelStroke
            targetPoss = self.__channelPointPositions
            showSignals = self.__keepSignalsOpen or self.__signals
        elif self.anchored:
            dashPattern = self.__anchoredDash
            stroke = self.__fullStroke
            targetPoss = self.__uniformPointPositions
            showSignals = self.__signals if self.__incompatible else []
        else:
            dashPattern = self.__unanchoredDash
            stroke = self.__dottedStroke
            targetPoss = self.__uniformPointPositions
            showSignals = self.__signals if self.__incompatible else []

        if self.animGroup.state() == QPropertyAnimation.Running:
            self.animGroup.stop()
        if self.__animationEnabled:
            self.__initializeAnimation(targetPoss, dashPattern, showSignals)
            self.animGroup.start()
        else:
            for point, t in zip(self.__points, targetPoss):
                pos = self.__anchorPath.pointAtPercent(t)
                point.setPos(pos)
            self.__updateLabels(showSignals)
            self.__pathStroker.setDashPattern(dashPattern)
            self.setPath(stroke)
            self.__shadow.setPath(stroke)

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

    #: Signal emitted the the item's selection state changes.
    selectedChanged = Signal(bool)

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
        self.captionTextItem = GraphicsTextItem(self)
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
            self.inputAnchorItem.setSignals(desc.inputs)
            self.inputAnchorItem.show()
        if desc.outputs:
            self.outputAnchorItem.setSignals(desc.outputs)
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

    def newInputAnchor(self, signal=None):
        # type: (Optional[InputSignal]) -> AnchorPoint
        """
        Create and return a new input :class:`AnchorPoint`.
        """
        if not (self.widget_description and self.widget_description.inputs):
            raise ValueError("Widget has no inputs.")

        anchor = AnchorPoint(self, signal=signal)
        self.inputAnchorItem.addAnchor(anchor)

        return anchor

    def removeInputAnchor(self, anchor):
        # type: (AnchorPoint) -> None
        """
        Remove input anchor.
        """
        self.inputAnchorItem.removeAnchor(anchor)

    def newOutputAnchor(self, signal=None):
        # type: (Optional[OutputSignal]) -> AnchorPoint
        """
        Create and return a new output :class:`AnchorPoint`.
        """
        if not (self.widget_description and self.widget_description.outputs):
            raise ValueError("Widget has no outputs.")

        anchor = AnchorPoint(self, signal=signal)
        self.outputAnchorItem.addAnchor(anchor)

        return anchor

    def removeOutputAnchor(self, anchor):
        # type: (AnchorPoint) -> None
        """
        Remove output anchor.
        """
        self.outputAnchorItem.removeAnchor(anchor)

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
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.shapeItem.setSelected(value)
            self.captionTextItem.setSelectionState(value)
            self.selectedChanged.emit(value)
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


from .linkitem import LinkItem

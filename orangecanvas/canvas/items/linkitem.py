"""
=========
Link Item
=========

"""
import math
from xml.sax.saxutils import escape

import typing
from typing import Optional, Any

from AnyQt.QtWidgets import (
    QGraphicsItem, QGraphicsPathItem, QGraphicsWidget,
    QGraphicsDropShadowEffect, QGraphicsSceneHoverEvent, QStyle,
    QGraphicsSceneMouseEvent
)
from AnyQt.QtGui import (
    QPen, QBrush, QColor, QPainterPath, QTransform, QPalette, QFont,
)
from AnyQt.QtCore import Qt, QPointF, QRectF, QLineF, QEvent, QPropertyAnimation, Signal, QTimer

from .nodeitem import AnchorPoint, SHADOW_COLOR
from .graphicstextitem import GraphicsTextItem
from .utils import stroke_path, qpainterpath_sub_path
from ...registry import InputSignal, OutputSignal

from ...scheme import SchemeLink

if typing.TYPE_CHECKING:
    from . import NodeItem, AnchorPoint


class LinkCurveItem(QGraphicsPathItem):
    """
    Link curve item. The main component of a :class:`LinkItem`.
    """
    def __init__(self, parent):
        # type: (QGraphicsItem) -> None
        super().__init__(parent)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setAcceptHoverEvents(True)

        self.__animationEnabled = False
        self.__hover = False
        self.__enabled = True
        self.__selected = False
        self.__shape = None  # type: Optional[QPainterPath]
        self.__curvepath = QPainterPath()
        self.__curvepath_disabled = None  # type: Optional[QPainterPath]
        self.__pen = self.pen()
        self.setPen(QPen(QBrush(QColor("#9CACB4")), 2.0))

        self.shadow = QGraphicsDropShadowEffect(
            blurRadius=5, color=QColor(SHADOW_COLOR),
            offset=QPointF(0, 0)
        )
        self.setGraphicsEffect(self.shadow)
        self.shadow.setEnabled(False)

        self.__blurAnimation = QPropertyAnimation(self.shadow, b"blurRadius")
        self.__blurAnimation.setDuration(50)
        self.__blurAnimation.finished.connect(self.__on_finished)

    def setCurvePath(self, path):
        # type: (QPainterPath) -> None
        if path != self.__curvepath:
            self.prepareGeometryChange()
            self.__curvepath = QPainterPath(path)
            self.__curvepath_disabled = None
            self.__shape = None
            self.__update()

    def curvePath(self):
        # type: () -> QPainterPath
        return QPainterPath(self.__curvepath)

    def setHoverState(self, state):
        # type: (bool) -> None
        if self.__hover != state:
            self.prepareGeometryChange()
            self.__hover = state
            self.__update()

    def setSelectionState(self, state):
        # type: (bool) -> None
        if self.__selected != state:
            self.prepareGeometryChange()
            self.__selected = state
            self.__update()

    def setLinkEnabled(self, state):
        # type: (bool) -> None
        self.prepareGeometryChange()
        self.__enabled = state
        self.__update()

    def isLinkEnabled(self):
        # type: () -> bool
        return self.__enabled

    def setPen(self, pen):
        # type: (QPen) -> None
        if self.__pen != pen:
            self.prepareGeometryChange()
            self.__pen = QPen(pen)
            self.__shape = None
            super().setPen(self.__pen)

    def shape(self):
        # type: () -> QPainterPath
        if self.__shape is None:
            path = self.curvePath()
            pen = QPen(self.pen())
            pen.setWidthF(max(pen.widthF(), 25.0))
            pen.setStyle(Qt.SolidLine)
            self.__shape = stroke_path(path, pen)
        return self.__shape

    def setPath(self, path):
        # type: (QPainterPath) -> None
        self.__shape = None
        super().setPath(path)

    def setAnimationEnabled(self, enabled):
        # type: (bool) -> None
        """
        Set the link item animation enabled.
        """
        if self.__animationEnabled != enabled:
            self.__animationEnabled = enabled

    def __update(self):
        # type: () -> None
        radius = 5 if self.__hover or self.__selected else 0
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

        basecurve = self.__curvepath
        link_enabled = self.__enabled
        if link_enabled:
            path = basecurve
        else:
            if self.__curvepath_disabled is None:
                self.__curvepath_disabled = path_link_disabled(basecurve)
            path = self.__curvepath_disabled

        self.setPath(path)

    def __on_finished(self):
        if self.shadow.blurRadius() == 0:
            self.shadow.setEnabled(False)


def path_link_disabled(basepath):
    # type: (QPainterPath) -> QPainterPath
    """
    Return a QPainterPath 'styled' to indicate a 'disabled' link.

    A disabled link is displayed with a single disconnection symbol in the
    middle (--||--)

    Parameters
    ----------
    basepath : QPainterPath
        The base path (a simple curve spine).

    Returns
    -------
    path : QPainterPath
        A 'styled' link path
    """
    segmentlen = basepath.length()
    px = 5

    if segmentlen < 10:
        return QPainterPath(basepath)

    t = (px / 2) / segmentlen
    p1 = qpainterpath_sub_path(basepath, 0.0, 0.50 - t)
    p2 = qpainterpath_sub_path(basepath, 0.50 + t, 1.0)

    angle = -basepath.angleAtPercent(0.5) + 90
    angler = math.radians(angle)
    normal = QPointF(math.cos(angler), math.sin(angler))

    end1 = p1.currentPosition()
    start2 = QPointF(p2.elementAt(0).x, p2.elementAt(0).y)
    p1.moveTo(start2.x(), start2.y())
    p1.addPath(p2)

    def QPainterPath_addLine(path, line):
        # type: (QPainterPath, QLineF) -> None
        path.moveTo(line.p1())
        path.lineTo(line.p2())

    QPainterPath_addLine(p1, QLineF(end1 - normal * 3, end1 + normal * 3))
    QPainterPath_addLine(p1, QLineF(start2 - normal * 3, start2 + normal * 3))
    return p1


_State = SchemeLink.State


class LinkItem(QGraphicsWidget):
    """
    A Link item in the canvas that connects two :class:`.NodeItem`\\s in the
    canvas.

    The link curve connects two `Anchor` items (see :func:`setSourceItem`
    and :func:`setSinkItem`). Once the anchors are set the curve
    automatically adjusts its end points whenever the anchors move.

    An optional source/sink text item can be displayed above the curve's
    central point (:func:`setSourceName`, :func:`setSinkName`)

    """
    #: Signal emitted when the item has been activated (double-click)
    activated = Signal()

    #: Signal emitted the the item's selection state changes.
    selectedChanged = Signal(bool)

    #: Z value of the item
    Z_VALUE = 0

    #: Runtime link state value
    #: These are pulled from SchemeLink.State for ease of binding to it's
    #: state
    State = SchemeLink.State
    #: The link has no associated state.
    NoState = SchemeLink.NoState
    #: Link is empty; the source node does not have any value on output
    Empty = SchemeLink.Empty
    #: Link is active; the source node has a valid value on output
    Active = SchemeLink.Active
    #: The link is pending; the sink node is scheduled for update
    Pending = SchemeLink.Pending
    #: The link's input is marked as invalidated (not yet available).
    Invalidated = SchemeLink.Invalidated

    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QGraphicsItem], Any) -> None
        self.__boundingRect = None  # type: Optional[QRectF]
        super().__init__(parent, **kwargs)
        self.setAcceptedMouseButtons(Qt.RightButton | Qt.LeftButton)
        self.setAcceptHoverEvents(True)
        self.__animationEnabled = False

        self.setZValue(self.Z_VALUE)

        self.sourceItem = None    # type: Optional[NodeItem]
        self.sourceAnchor = None  # type: Optional[AnchorPoint]
        self.sinkItem = None      # type: Optional[NodeItem]
        self.sinkAnchor = None    # type: Optional[AnchorPoint]

        self.curveItem = LinkCurveItem(self)

        self.linkTextItem = GraphicsTextItem(self)
        self.linkTextItem.setAcceptedMouseButtons(Qt.NoButton)
        self.linkTextItem.setAcceptHoverEvents(False)
        self.__sourceName = ""
        self.__sinkName = ""

        self.__dynamic = False
        self.__dynamicEnabled = False
        self.__state = LinkItem.NoState
        self.__channelNamesVisible = True
        self.hover = False

        self.channelNameAnim = QPropertyAnimation(self.linkTextItem, b'opacity', self)
        self.channelNameAnim.setDuration(50)

        self.prepareGeometryChange()
        self.__updatePen()
        self.__updatePalette()
        self.__updateFont()

    def setSourceItem(self, item, signal=None, anchor=None):
        # type: (Optional[NodeItem], Optional[OutputSignal], Optional[AnchorPoint]) -> None
        """
        Set the source `item` (:class:`.NodeItem`). Use `anchor`
        (:class:`.AnchorPoint`) as the curve start point (if ``None`` a new
        output anchor will be created using ``item.newOutputAnchor()``).

        Setting item to ``None`` and a valid anchor is a valid operation
        (for instance while mouse dragging one end of the link).
        """
        if item is not None and anchor is not None:
            if anchor not in item.outputAnchors():
                raise ValueError("Anchor must be belong to the item")

        if self.sourceItem != item:
            if self.sourceAnchor:
                # Remove a previous source item and the corresponding anchor
                self.sourceAnchor.scenePositionChanged.disconnect(
                    self._sourcePosChanged
                )

                if self.sourceItem is not None:
                    self.sourceItem.removeOutputAnchor(self.sourceAnchor)
                    self.sourceItem.selectedChanged.disconnect(
                        self.__updateSelectedState)
                    self.sourceItem.titleEditingFinished.disconnect(
                        self.__update_tooltip)
                self.sourceItem = self.sourceAnchor = None

            self.sourceItem = item

            if item is not None and anchor is None:
                # Create a new output anchor for the item if none is provided.
                anchor = item.newOutputAnchor(signal)
            if item is not None:
                item.selectedChanged.connect(self.__updateSelectedState)
                item.titleEditingFinished.connect(self.__update_tooltip)

        if anchor != self.sourceAnchor:
            if self.sourceAnchor is not None:
                self.sourceAnchor.scenePositionChanged.disconnect(
                    self._sourcePosChanged
                )

            self.sourceAnchor = anchor

            if self.sourceAnchor is not None:
                self.sourceAnchor.scenePositionChanged.connect(
                    self._sourcePosChanged
                )

        self.__updateCurve()

    def setSinkItem(self, item, signal=None, anchor=None):
        # type: (Optional[NodeItem], Optional[InputSignal], Optional[AnchorPoint]) -> None
        """
        Set the sink `item` (:class:`.NodeItem`). Use `anchor`
        (:class:`.AnchorPoint`) as the curve end point (if ``None`` a new
        input anchor will be created using ``item.newInputAnchor()``).

        Setting item to ``None`` and a valid anchor is a valid operation
        (for instance while mouse dragging one and of the link).
        """
        if item is not None and anchor is not None:
            if anchor not in item.inputAnchors():
                raise ValueError("Anchor must be belong to the item")

        if self.sinkItem != item:
            if self.sinkAnchor:
                # Remove a previous source item and the corresponding anchor
                self.sinkAnchor.scenePositionChanged.disconnect(
                    self._sinkPosChanged
                )
                if self.sinkItem is not None:
                    self.sinkItem.removeInputAnchor(self.sinkAnchor)
                    self.sinkItem.selectedChanged.disconnect(
                        self.__updateSelectedState)
                    self.sinkItem.titleEditingFinished.disconnect(
                        self.__update_tooltip
                    )
                self.sinkItem = self.sinkAnchor = None

            self.sinkItem = item

            if item is not None and anchor is None:
                # Create a new input anchor for the item if none is provided.
                anchor = item.newInputAnchor(signal)
            if item is not None:
                item.selectedChanged.connect(self.__updateSelectedState)
                item.titleEditingFinished.connect(self.__update_tooltip)

        if self.sinkAnchor != anchor:
            if self.sinkAnchor is not None:
                self.sinkAnchor.scenePositionChanged.disconnect(
                    self._sinkPosChanged
                )

            self.sinkAnchor = anchor

            if self.sinkAnchor is not None:
                self.sinkAnchor.scenePositionChanged.connect(
                    self._sinkPosChanged
                )

        self.__updateCurve()

    def setChannelNamesVisible(self, visible):
        # type: (bool) -> None
        """
        Set the visibility of the channel name text.
        """
        if self.__channelNamesVisible != visible:
            self.__channelNamesVisible = visible
        self.__initChannelNameOpacity()

    def setSourceName(self, name):
        # type: (str) -> None
        """
        Set the name of the source (used in channel name text).
        """
        if self.__sourceName != name:
            self.__sourceName = name
            self.__updateText()

    def sourceName(self):
        # type: () -> str
        """
        Return the source name.
        """
        return self.__sourceName

    def setSinkName(self, name):
        # type: (str) -> None
        """
        Set the name of the sink (used in channel name text).
        """
        if self.__sinkName != name:
            self.__sinkName = name
            self.__updateText()

    def sinkName(self):
        # type: () -> str
        """
        Return the sink name.
        """
        return self.__sinkName

    def setAnimationEnabled(self, enabled):
        # type: (bool) -> None
        """
        Set the link item animation enabled state.
        """
        if self.__animationEnabled != enabled:
            self.__animationEnabled = enabled
        self.curveItem.setAnimationEnabled(enabled)

    def _sinkPosChanged(self, *arg):
        self.__updateCurve()

    def _sourcePosChanged(self, *arg):
        self.__updateCurve()

    def __updateCurve(self):
        # type: () -> None
        self.prepareGeometryChange()
        self.__boundingRect = None
        if self.sourceAnchor and self.sinkAnchor:
            source_pos = self.sourceAnchor.anchorScenePos()
            sink_pos = self.sinkAnchor.anchorScenePos()
            source_pos = self.curveItem.mapFromScene(source_pos)
            sink_pos = self.curveItem.mapFromScene(sink_pos)

            # Adaptive offset for the curve control points to avoid a
            # cusp when the two points have the same y coordinate
            # and are close together
            delta = source_pos - sink_pos
            dist = math.sqrt(delta.x() ** 2 + delta.y() ** 2)
            cp_offset = min(dist / 2.0, 60.0)

            # TODO: make the curve tangent orthogonal to the anchors path.
            path = QPainterPath()
            path.moveTo(source_pos)
            path.cubicTo(source_pos + QPointF(cp_offset, 0),
                         sink_pos - QPointF(cp_offset, 0),
                         sink_pos)

            self.curveItem.setCurvePath(path)
            self.__updateText()
        else:
            self.setHoverState(False)
            self.curveItem.setPath(QPainterPath())

    def __updateText(self):
        # type: () -> None
        self.prepareGeometryChange()
        self.__boundingRect = None

        if self.__sourceName or self.__sinkName:
            if self.__sourceName != self.__sinkName:
                text = ("<nobr>{0}</nobr> \u2192 <nobr>{1}</nobr>"
                        .format(escape(self.__sourceName),
                                escape(self.__sinkName)))
            else:
                # If the names are the same show only one.
                # Is this right? If the sink has two input channels of the
                # same type having the name on the link help elucidate
                # the scheme.
                text = escape(self.__sourceName)
        else:
            text = ""

        self.linkTextItem.setHtml(
            '<div align="center" style="font-size: small" >{0}</div>'
            .format(text))
        path = self.curveItem.curvePath()

        # Constrain the text width if it is too long to fit on a single line
        # between the two ends
        if not path.isEmpty():
            # Use the distance between the start/end points as a measure of
            # available space
            diff = path.pointAtPercent(0.0) - path.pointAtPercent(1.0)
            available_width = math.sqrt(diff.x() ** 2 + diff.y() ** 2)
            # Get the ideal text width if it was unconstrained
            doc = self.linkTextItem.document().clone(self)
            doc.setTextWidth(-1)
            idealwidth = doc.idealWidth()
            doc.deleteLater()

            # Constrain the text width but not below a certain min width
            minwidth = 100
            textwidth = max(minwidth, min(available_width, idealwidth))
            self.linkTextItem.setTextWidth(textwidth)
        else:
            # Reset the fixed width
            self.linkTextItem.setTextWidth(-1)

        if not path.isEmpty():
            center = path.pointAtPercent(0.5)
            angle = path.angleAtPercent(0.5)

            brect = self.linkTextItem.boundingRect()

            transform = QTransform()
            transform.translate(center.x(), center.y())

            # Rotate text to be on top of link
            if 90 <= angle < 270:
                transform.rotate(180 - angle)
            else:
                transform.rotate(-angle)

            # Center and move above the curve path.
            transform.translate(-brect.width() / 2, -brect.height())

            self.linkTextItem.setTransform(transform)

    def removeLink(self):
        # type: () -> None
        self.setSinkItem(None)
        self.setSourceItem(None)
        self.__updateCurve()

    def setHoverState(self, state):
        # type: (bool) -> None
        if self.hover != state:
            self.prepareGeometryChange()
            self.__boundingRect = None
            self.hover = state
            if self.sinkAnchor:
                self.sinkAnchor.setHoverState(state)
            if self.sourceAnchor:
                self.sourceAnchor.setHoverState(state)
            self.curveItem.setHoverState(state)
            self.__updatePen()
            self.__updateChannelNameVisibility()
            self.__updateZValue()

    def __updateZValue(self):
        text_ss = self.linkTextItem.styleState()
        if self.hover:
            text_ss |= QStyle.State_HasFocus
            z = 9999
            self.linkTextItem.setParentItem(None)
        else:
            text_ss &= ~QStyle.State_HasFocus
            z = self.Z_VALUE
            self.linkTextItem.setParentItem(self)
        self.linkTextItem.setZValue(z)
        self.linkTextItem.setStyleState(text_ss)

    def mouseDoubleClickEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> None
        super().mouseDoubleClickEvent(event)
        QTimer.singleShot(0, self.activated.emit)

    def hoverEnterEvent(self, event):
        # type: (QGraphicsSceneHoverEvent) -> None
        # Hover enter event happens when the mouse enters any child object
        # but we only want to show the 'hovered' shadow when the mouse
        # is over the 'curveItem', so we install self as an event filter
        # on the LinkCurveItem and listen to its hover events.
        self.curveItem.installSceneEventFilter(self)
        return super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        # type: (QGraphicsSceneHoverEvent) -> None
        # Remove the event filter to prevent unnecessary work in
        # scene event filter when not needed
        self.curveItem.removeSceneEventFilter(self)
        return super().hoverLeaveEvent(event)

    def __initChannelNameOpacity(self):
        if self.__channelNamesVisible:
            self.linkTextItem.setOpacity(1)
        else:
            self.linkTextItem.setOpacity(0)

    def __updateChannelNameVisibility(self):
        if self.__channelNamesVisible:
            return
        enabled = self.hover or self.isSelected() or self.__isSelectedImplicit()
        targetOpacity = 1 if enabled else 0
        if not self.__animationEnabled:
            self.linkTextItem.setOpacity(targetOpacity)
        else:
            if self.channelNameAnim.state() == QPropertyAnimation.Running:
                self.channelNameAnim.stop()
            self.channelNameAnim.setStartValue(self.linkTextItem.opacity())
            self.channelNameAnim.setEndValue(targetOpacity)
            self.channelNameAnim.start()

    def changeEvent(self, event):
        # type: (QEvent) -> None
        if event.type() == QEvent.PaletteChange:
            self.__updatePalette()
        elif event.type() == QEvent.FontChange:
            self.__updateFont()
        super().changeEvent(event)

    def sceneEventFilter(self, obj, event):
        # type: (QGraphicsItem, QEvent) -> bool
        if obj is self.curveItem:
            if event.type() == QEvent.GraphicsSceneHoverEnter:
                self.setHoverState(True)
            elif event.type() == QEvent.GraphicsSceneHoverLeave:
                self.setHoverState(False)

        return super().sceneEventFilter(obj, event)

    def boundingRect(self):
        # type: () -> QRectF
        if self.__boundingRect is None:
            self.__boundingRect = self.childrenBoundingRect()
        return self.__boundingRect

    def shape(self):
        # type: () -> QPainterPath
        return self.curveItem.shape()

    def setEnabled(self, enabled):
        # type: (bool) -> None
        """
        Reimplemented from :class:`QGraphicWidget`

        Set link enabled state. When disabled the link is rendered with a
        dashed line.

        """
        # This getter/setter pair override a property from the base class.
        # They should be renamed to e.g. setLinkEnabled/linkEnabled
        self.curveItem.setLinkEnabled(enabled)

    def isEnabled(self):
        # type: () -> bool
        return self.curveItem.isLinkEnabled()

    def setDynamicEnabled(self, enabled):
        # type: (bool) -> None
        """
        Set the link's dynamic enabled state.

        If the link is `dynamic` it will be rendered in red/green color
        respectively depending on the state of the dynamic enabled state.

        """
        if self.__dynamicEnabled != enabled:
            self.__dynamicEnabled = enabled
            if self.__dynamic:
                self.__updatePen()
        self.__update_tooltip()

    def __update_tooltip(self):
        if self.__dynamicEnabled:
            self.curveItem.setToolTip(None)
        else:
            self.curveItem.setToolTip(f"{self.sourceItem.title()} is not providing the proper data type required by {self.sinkItem.title()}")

    def isDynamicEnabled(self):
        # type: () -> bool
        """
        Is the link dynamic enabled.
        """
        return self.__dynamicEnabled

    def setDynamic(self, dynamic):
        # type: (bool) -> None
        """
        Mark the link as dynamic (i.e. it responds to
        :func:`setDynamicEnabled`).

        """
        if self.__dynamic != dynamic:
            self.__dynamic = dynamic
            self.__updatePen()

    def isDynamic(self):
        # type: () -> bool
        """
        Is the link dynamic.
        """
        return self.__dynamic

    def setRuntimeState(self, state):
        # type: (_State) -> None
        """
        Style the link appropriate to the LinkItem.State

        Parameters
        ----------
        state : LinkItem.State
        """
        if self.__state != state:
            self.__state = state
            self.__updateAnchors()
            self.__updatePen()

    def runtimeState(self):
        # type: () -> _State
        return self.__state

    def __updatePen(self):
        # type: () -> None
        self.prepareGeometryChange()
        self.__boundingRect = None
        if self.__dynamic:
            if self.__dynamicEnabled:
                color = QColor(0, 150, 0, 150)
            else:
                color = QColor(150, 0, 0, 150)

            normal = QPen(QBrush(color), 2.0)
            hover = QPen(QBrush(color.darker(120)), 2.0)
        else:
            normal = QPen(QBrush(QColor("#9CACB4")), 2.0)
            hover = QPen(QBrush(QColor("#959595")), 2.0)

        if self.__state & LinkItem.Empty:
            pen_style = Qt.DashLine
        else:
            pen_style = Qt.SolidLine

        normal.setStyle(pen_style)
        hover.setStyle(pen_style)

        if self.hover or self.isSelected():
            pen = hover
        else:
            pen = normal

        self.curveItem.setPen(pen)

    def __updatePalette(self):
        # type: () -> None
        self.linkTextItem.setDefaultTextColor(
            self.palette().color(QPalette.Text))

    def __updateFont(self):
        # type: () -> None
        font = self.font()
        # linkTextItem will be rotated. Hinting causes bad positioning under
        # rotation so we prefer to disable it. This is only a hint, on windows
        # (DirectWrite engine) vertical hinting is still performed.
        font.setHintingPreference(QFont.PreferNoHinting)
        self.linkTextItem.setFont(font)

    def __updateAnchors(self):
        state = QStyle.State(0)
        if self.hover:
            state |= QStyle.State_MouseOver
        if self.isSelected() or self.__isSelectedImplicit():
            state |= QStyle.State_Selected
        if self.sinkAnchor is not None:
            self.sinkAnchor.indicator.setStyleState(state)
            self.sinkAnchor.indicator.setLinkState(self.__state)
        if self.sourceAnchor is not None:
            self.sourceAnchor.indicator.setStyleState(state)
            self.sourceAnchor.indicator.setLinkState(self.__state)

    def __updateSelectedState(self):
        selected = self.isSelected() or self.__isSelectedImplicit()
        self.linkTextItem.setSelectionState(selected)
        self.__updatePen()
        self.__updateAnchors()
        self.__updateChannelNameVisibility()
        self.curveItem.setSelectionState(selected)

    def __isSelectedImplicit(self):
        source, sink = self.sourceItem, self.sinkItem
        return (source is not None and source.isSelected()
                and sink is not None and sink.isSelected())

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.__updateSelectedState()
            self.selectedChanged.emit(value)
        return super().itemChange(change, value)

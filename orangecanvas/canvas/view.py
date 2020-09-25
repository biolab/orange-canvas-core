"""
Canvas Graphics View
"""
import logging
import sys
from typing import cast, Optional

from AnyQt.QtWidgets import QGraphicsView, QAction, QGestureEvent, QPinchGesture
from AnyQt.QtGui import QCursor, QIcon, QKeySequence, QTransform, QWheelEvent
from AnyQt.QtCore import (
    Qt, QRect, QSize, QRectF, QPoint, QTimer, QEvent, QPointF
)
from AnyQt.QtCore import Property, pyqtSignal as Signal

log = logging.getLogger(__name__)


class CanvasView(QGraphicsView):
    """Canvas View handles the zooming.
    """

    def __init__(self, *args):
        super().__init__(*args)
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.grabGesture(Qt.PinchGesture)
        self.__backgroundIcon = QIcon()

        self.__autoScroll = False
        self.__autoScrollMargin = 16
        self.__autoScrollTimer = QTimer(self)
        self.__autoScrollTimer.timeout.connect(self.__autoScrollAdvance)

        # scale factor accumulating partial increments from wheel events
        self.__zoomLevel = 100
        # effective scale level(rounded to whole integers)
        self.__effectiveZoomLevel = 100

        self.__zoomInAction = QAction(
            self.tr("Zoom in"), self, objectName="action-zoom-in",
            shortcut=QKeySequence.ZoomIn,
            triggered=self.zoomIn,
        )

        self.__zoomOutAction = QAction(
            self.tr("Zoom out"), self, objectName="action-zoom-out",
            shortcut=QKeySequence.ZoomOut,
            triggered=self.zoomOut
        )
        self.__zoomResetAction = QAction(
            self.tr("Reset Zoom"), self, objectName="action-zoom-reset",
            triggered=self.zoomReset,
            shortcut=QKeySequence(Qt.ControlModifier | Qt.Key_0)
        )

    def setScene(self, scene):
        super().setScene(scene)
        self._ensureSceneRect(scene)

    def _ensureSceneRect(self, scene):
        r = scene.addRect(QRectF(0, 0, 400, 400))
        scene.sceneRect()
        scene.removeItem(r)

    def setAutoScrollMargin(self, margin):
        self.__autoScrollMargin = margin

    def autoScrollMargin(self):
        return self.__autoScrollMargin

    def setAutoScroll(self, enable):
        self.__autoScroll = enable

    def autoScroll(self):
        return self.__autoScroll

    def mousePressEvent(self, event):
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            if not self.__autoScrollTimer.isActive() and \
                    self.__shouldAutoScroll(event.pos()):
                self.__startAutoScroll()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() & Qt.LeftButton:
            self.__stopAutoScroll()
        return super().mouseReleaseEvent(event)

    def __should_scroll_horizontally(self, event: QWheelEvent):
        if event.source() != Qt.MouseEventNotSynthesized:
            return False
        if (event.modifiers() & Qt.ShiftModifier and sys.platform == 'darwin' or
            event.modifiers() & Qt.AltModifier and sys.platform != 'darwin'):
            return True
        if event.angleDelta().x() == 0:
            vBar = self.verticalScrollBar()
            yDelta = event.angleDelta().y()
            direction = yDelta >= 0
            edgeVBarValue = vBar.minimum() if direction else vBar.maximum()
            return vBar.value() == edgeVBarValue
        return False

    def wheelEvent(self, event: QWheelEvent):
        # Zoom
        if event.modifiers() & Qt.ControlModifier \
                and event.buttons() == Qt.NoButton:
            delta = event.angleDelta().y()
            # use mouse position as anchor while zooming
            anchor = self.transformationAnchor()
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
            self.__setZoomLevel(self.__zoomLevel + 10 * delta / 120)
            self.setTransformationAnchor(anchor)
            event.accept()
        # Scroll horizontally
        elif self.__should_scroll_horizontally(event):
            x, y = event.angleDelta().x(), event.angleDelta().y()
            sign_value = x if x != 0 else y
            sign = 1 if sign_value >= 0 else -1
            new_angle_delta = QPoint(sign * max(abs(x), abs(y), sign_value), 0)
            new_pixel_delta = QPoint(0, 0)
            new_modifiers = event.modifiers() & ~(Qt.ShiftModifier | Qt.AltModifier)
            new_event = QWheelEvent(
                event.pos(), event.globalPos(), new_pixel_delta,
                new_angle_delta, event.buttons(), new_modifiers,
                event.phase(), event.inverted(), event.source()
            )
            event.accept()
            super().wheelEvent(new_event)
        else:
            super().wheelEvent(event)

    def gestureEvent(self, event: QGestureEvent):
        gesture = event.gesture(Qt.PinchGesture)
        if gesture is None:
            return
        if gesture.state() == Qt.GestureStarted:
            event.accept(gesture)
        elif gesture.changeFlags() & QPinchGesture.ScaleFactorChanged:
            anchor = gesture.centerPoint().toPoint()
            anchor = self.mapToScene(anchor)
            self.__setZoomLevel(self.__zoomLevel * gesture.scaleFactor(),
                                anchor=anchor)
            event.accept()
        elif gesture.state() == Qt.GestureFinished:
            event.accept()

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Gesture:
            self.gestureEvent(cast(QGestureEvent, event))
        return super().event(event)

    def zoomIn(self):
        self.__setZoomLevel(self.__zoomLevel + 10)

    def zoomOut(self):
        self.__setZoomLevel(self.__zoomLevel - 10)

    def zoomReset(self):
        """
        Reset the zoom level.
        """
        self.__setZoomLevel(100)

    def zoomLevel(self):
        # type: () -> float
        """
        Return the current zoom level.

        Level is expressed in percentages; 100 is unscaled, 50 is half size, ...
        """
        return self.__effectiveZoomLevel

    def setZoomLevel(self, level):
        self.__setZoomLevel(level)

    def __setZoomLevel(self, scale, anchor=None):
        # type: (float, Optional[QPointF]) -> None
        self.__zoomLevel = max(30, min(scale, 300))
        scale = round(self.__zoomLevel)
        self.__zoomOutAction.setEnabled(scale != 30)
        self.__zoomInAction.setEnabled(scale != 300)
        if self.__effectiveZoomLevel != scale:
            self.__effectiveZoomLevel = scale
            transform = QTransform()
            transform.scale(scale / 100, scale / 100)
            if anchor is not None:
                anchor = self.mapFromScene(anchor)
            self.setTransform(transform)
            if anchor is not None:
                center = self.viewport().rect().center()
                diff = self.mapToScene(center) - self.mapToScene(anchor)
                self.centerOn(anchor + diff)
            self.zoomLevelChanged.emit(scale)

    zoomLevelChanged = Signal(float)
    zoomLevel_ = Property(
        float, zoomLevel, setZoomLevel, notify=zoomLevelChanged
    )

    def __shouldAutoScroll(self, pos):
        if self.__autoScroll:
            margin = self.__autoScrollMargin
            viewrect = self.contentsRect()
            rect = viewrect.adjusted(margin, margin, -margin, -margin)
            # only do auto scroll when on the viewport's margins
            return not rect.contains(pos) and viewrect.contains(pos)
        else:
            return False

    def __startAutoScroll(self):
        self.__autoScrollTimer.start(10)
        log.debug("Auto scroll timer started")

    def __stopAutoScroll(self):
        if self.__autoScrollTimer.isActive():
            self.__autoScrollTimer.stop()
            log.debug("Auto scroll timer stopped")

    def __autoScrollAdvance(self):
        """Advance the auto scroll
        """
        pos = QCursor.pos()
        pos = self.mapFromGlobal(pos)
        margin = self.__autoScrollMargin

        vvalue = self.verticalScrollBar().value()
        hvalue = self.horizontalScrollBar().value()

        vrect = QRect(0, 0, self.width(), self.height())

        # What should be the speed
        advance = 10

        # We only do auto scroll if the mouse is inside the view.
        if vrect.contains(pos):
            if pos.x() < vrect.left() + margin:
                self.horizontalScrollBar().setValue(hvalue - advance)
            if pos.y() < vrect.top() + margin:
                self.verticalScrollBar().setValue(vvalue - advance)
            if pos.x() > vrect.right() - margin:
                self.horizontalScrollBar().setValue(hvalue + advance)
            if pos.y() > vrect.bottom() - margin:
                self.verticalScrollBar().setValue(vvalue + advance)

            if self.verticalScrollBar().value() == vvalue and \
                    self.horizontalScrollBar().value() == hvalue:
                self.__stopAutoScroll()
        else:
            self.__stopAutoScroll()

        log.debug("Auto scroll advance")

    def setBackgroundIcon(self, icon):
        if not isinstance(icon, QIcon):
            raise TypeError("A QIcon expected.")

        if self.__backgroundIcon != icon:
            self.__backgroundIcon = icon
            self.viewport().update()

    def backgroundIcon(self):
        return QIcon(self.__backgroundIcon)

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)

        if not self.__backgroundIcon.isNull():
            painter.setClipRect(rect)
            vrect = QRect(QPoint(0, 0), self.viewport().size())
            vrect = self.mapToScene(vrect).boundingRect()

            pm = self.__backgroundIcon.pixmap(
                vrect.size().toSize().boundedTo(QSize(200, 200))
            )
            pmrect = QRect(QPoint(0, 0), pm.size())
            pmrect.moveCenter(vrect.center().toPoint())
            if rect.toRect().intersects(pmrect):
                painter.drawPixmap(pmrect, pm)

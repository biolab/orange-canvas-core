import enum
import typing

from typing import Optional, Any, Union, Tuple

from AnyQt.QtWidgets import QGraphicsItem, QGraphicsObject
from AnyQt.QtGui import QBrush, QPainterPath
from AnyQt.QtCore import Qt, QPointF, QLineF, QRectF, QMargins, QEvent

from AnyQt.QtCore import pyqtSignal as Signal, pyqtProperty as Property


from .graphicspathobject import GraphicsPathObject
from .utils import toGraphicsObjectIfPossible


if typing.TYPE_CHECKING:
    ConstraintFunc = typing.Callable[[QPointF], QPointF]


class ControlPoint(GraphicsPathObject):
    """A control point for annotations in the canvas.
    """
    class Anchor(enum.IntEnum):
        Free = 0
        Left, Top, Right, Bottom, Center = 1, 2, 4, 8, 16
        TopLeft = Top | Left
        TopRight = Top | Right
        BottomRight = Bottom | Right
        BottomLeft = Bottom | Left

    Free = Anchor.Free
    Left = Anchor.Left
    Right = Anchor.Right
    Top = Anchor.Top
    Bottom = Anchor.Bottom
    TopLeft = Anchor.TopLeft
    TopRight = Anchor.TopRight
    BottomRight = Anchor.BottomRight
    BottomLeft = Anchor.BottomLeft

    def __init__(self, parent=None, anchor=Free, constraint=Qt.Orientation(0),
                 **kwargs):
        # type: (Optional[QGraphicsItem], Anchor, Qt.Orientation, Any) -> None
        super().__init__(parent, **kwargs)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
        self.setAcceptedMouseButtons(Qt.LeftButton)

        self.__constraint = constraint  # type: Qt.Orientation

        self.__constraintFunc = None  # type: Optional[ConstraintFunc]
        self.__anchor = ControlPoint.Free
        self.__initialPosition = None  # type: Optional[QPointF]
        self.setAnchor(anchor)

        path = QPainterPath()
        path.addEllipse(QRectF(-4, -4, 8, 8))
        self.setPath(path)

        self.setBrush(QBrush(Qt.lightGray, Qt.SolidPattern))

    def setAnchor(self, anchor):
        # type: (Anchor) -> None
        """Set anchor position
        """
        self.__anchor = anchor

    def anchor(self):
        # type: () -> Anchor
        return self.__anchor

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Enable ItemPositionChange (and pos constraint) only when
            # this is the mouse grabber item
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.__initialPosition = None
            self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            if self.__initialPosition is None:
                self.__initialPosition = self.pos()

            current = self.mapToParent(self.mapFromScene(event.scenePos()))
            down = self.mapToParent(
                self.mapFromScene(event.buttonDownScenePos(Qt.LeftButton)))

            self.setPos(self.__initialPosition + current - down)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange:
            return self.constrain(value)
        return super().itemChange(change, value)

    def hasConstraint(self):
        # type: () -> bool
        return self.__constraintFunc is not None or self.__constraint != 0

    def setConstraint(self, constraint):
        # type: (Qt.Orientation) -> None
        """Set the constraint for the point (Qt.Vertical Qt.Horizontal or 0)

        .. note:: Clears the constraintFunc if it was previously set

        """
        if self.__constraint != constraint:
            self.__constraint = constraint

        self.__constraintFunc = None

    def constrain(self, pos):
        # type: (QPointF) -> QPointF
        """Constrain the pos.
        """
        if self.__constraintFunc:
            return self.__constraintFunc(pos)
        elif self.__constraint == Qt.Vertical:
            return QPointF(self.pos().x(), pos.y())
        elif self.__constraint == Qt.Horizontal:
            return QPointF(pos.x(), self.pos().y())
        else:
            return QPointF(pos)

    def setConstraintFunc(self, func):
        # type: (Optional[ConstraintFunc]) -> None
        if self.__constraintFunc != func:
            self.__constraintFunc = func


class ControlPointRect(QGraphicsObject):
    class Constraint(enum.IntEnum):
        Free = 0
        KeepAspectRatio = 1
        KeepCenter = 2
    Free = Constraint.Free
    KeepAspectRatio = Constraint.KeepAspectRatio
    KeepCenter = Constraint.KeepCenter

    rectChanged = Signal(QRectF)
    rectEdited = Signal(QRectF)

    def __init__(self, parent=None, rect=QRectF(), constraints=Free, **kwargs):
        # type: (Optional[QGraphicsItem], QRectF, Constraint, Any) -> None
        super().__init__(parent, **kwargs)
        self.setFlag(QGraphicsItem.ItemHasNoContents)
        self.setFlag(QGraphicsItem.ItemIsFocusable)

        self.__rect = QRectF(rect) if rect is not None else QRectF()
        self.__margins = QMargins()
        points = \
            [ControlPoint(self, ControlPoint.Left, constraint=Qt.Horizontal),
             ControlPoint(self, ControlPoint.Top, constraint=Qt.Vertical),
             ControlPoint(self, ControlPoint.TopLeft),
             ControlPoint(self, ControlPoint.Right, constraint=Qt.Horizontal),
             ControlPoint(self, ControlPoint.TopRight),
             ControlPoint(self, ControlPoint.Bottom, constraint=Qt.Vertical),
             ControlPoint(self, ControlPoint.BottomLeft),
             ControlPoint(self, ControlPoint.BottomRight)
             ]
        assert(points == sorted(points, key=lambda p: p.anchor()))

        self.__points = dict((p.anchor(), p) for p in points)

        if self.scene():
            self.__installFilter()

        for p in points:
            p.setFlag(QGraphicsItem.ItemIsFocusable)
            p.setFocusProxy(self)

        self.__constraints = constraints
        self.__activeControl = None  # type: Optional[ControlPoint]

        self.__pointsLayout()

    def controlPoint(self, anchor):
        # type: (ControlPoint.Anchor) -> ControlPoint
        """
        Return the anchor point (:class:`ControlPoint`) for anchor position.
        """
        return self.__points[anchor]

    def setRect(self, rect):
        # type: (QRectF) -> None
        """
        Set the control point rectangle (:class:`QRectF`)
        """
        if self.__rect != rect:
            self.__rect = QRectF(rect)
            self.__pointsLayout()
            self.prepareGeometryChange()
            self.rectChanged.emit(rect.normalized())

    def rect(self):
        # type: () -> QRectF
        """
        Return the control point rectangle.
        """
        # Return the rect normalized. During the control point move the
        # rect can change to an invalid size, but the layout must still
        # know to which point does an unnormalized rect side belong,
        # so __rect is left unnormalized.
        # NOTE: This means all signal emits (rectChanged/Edited) must
        #       also emit normalized rects
        return self.__rect.normalized()

    rect_ = Property(QRectF, fget=rect, fset=setRect, user=True)

    def setControlMargins(self, *margins):
        # type: (int) -> None
        """Set the controls points on the margins around `rect`
        """
        if len(margins) > 1:
            margins = QMargins(*margins)
        elif len(margins) == 1:
            margin = margins[0]
            margins = QMargins(margin, margin, margin, margin)
        else:
            raise TypeError

        if self.__margins != margins:
            self.__margins = margins
            self.__pointsLayout()

    def controlMargins(self):
        # type: () -> QMargins
        return QMargins(self.__margins)

    def setConstraints(self, constraints):
        raise NotImplementedError

    def isControlActive(self):
        # type: () -> bool
        """Return the state of the control. True if the control is
        active (user is dragging one of the points) False otherwise.
        """
        return self.__activeControl is not None

    def itemChange(self, change, value):
        # type: (QGraphicsItem.GraphicsItemChange, Any) -> Any
        if change == QGraphicsItem.ItemSceneHasChanged and self.scene():
            self.__installFilter()
        return super().itemChange(change, value)

    def sceneEventFilter(self, obj, event):
        # type: (QGraphicsItem, QEvent) -> bool
        obj = toGraphicsObjectIfPossible(obj)
        if isinstance(obj, ControlPoint):
            etype = event.type()
            if etype in (QEvent.GraphicsSceneMousePress,
                         QEvent.GraphicsSceneMouseDoubleClick) and \
                    event.button() == Qt.LeftButton:
                self.__setActiveControl(obj)

            elif etype == QEvent.GraphicsSceneMouseRelease and \
                    event.button() == Qt.LeftButton:
                self.__setActiveControl(None)
        return super().sceneEventFilter(obj, event)

    def __installFilter(self):
        # type: () -> None
        # Install filters on the control points.
        for p in self.__points.values():
            p.installSceneEventFilter(self)

    def __pointsLayout(self):
        # type: () -> None
        """Layout the control points
        """
        rect = self.__rect
        margins = self.__margins
        rect = rect.adjusted(-margins.left(), -margins.top(),
                             margins.right(), margins.bottom())
        center = rect.center()
        cx, cy = center.x(), center.y()
        left, top, right, bottom = \
                rect.left(), rect.top(), rect.right(), rect.bottom()

        self.controlPoint(ControlPoint.Left).setPos(left, cy)
        self.controlPoint(ControlPoint.Right).setPos(right, cy)
        self.controlPoint(ControlPoint.Top).setPos(cx, top)
        self.controlPoint(ControlPoint.Bottom).setPos(cx, bottom)

        self.controlPoint(ControlPoint.TopLeft).setPos(left, top)
        self.controlPoint(ControlPoint.TopRight).setPos(right, top)
        self.controlPoint(ControlPoint.BottomLeft).setPos(left, bottom)
        self.controlPoint(ControlPoint.BottomRight).setPos(right, bottom)

    def __setActiveControl(self, control):
        # type: (Optional[ControlPoint]) -> None
        if self.__activeControl != control:
            if self.__activeControl is not None:
                self.__activeControl.positionChanged[QPointF].disconnect(
                    self.__activeControlMoved
                )

            self.__activeControl = control

            if control is not None:
                control.positionChanged[QPointF].connect(
                    self.__activeControlMoved
                )

    def __activeControlMoved(self, pos):
        # type: (QPointF) -> None
        # The active control point has moved, update the control
        # rectangle
        control = self.__activeControl
        assert control is not None
        pos = control.pos()
        rect = QRectF(self.__rect)
        margins = self.__margins

        # TODO: keyboard modifiers and constraints.

        anchor = control.anchor()
        if anchor & ControlPoint.Top:
            rect.setTop(pos.y() + margins.top())
        elif anchor & ControlPoint.Bottom:
            rect.setBottom(pos.y() - margins.bottom())

        if anchor & ControlPoint.Left:
            rect.setLeft(pos.x() + margins.left())
        elif anchor & ControlPoint.Right:
            rect.setRight(pos.x() - margins.right())

        changed = self.__rect != rect

        self.blockSignals(True)
        self.setRect(rect)
        self.blockSignals(False)

        if changed:
            self.rectEdited.emit(rect.normalized())

    def boundingRect(self):
        # type: () -> QRectF
        return QRectF()


class ControlPointLine(QGraphicsObject):

    lineChanged = Signal(QLineF)
    lineEdited = Signal(QLineF)

    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QGraphicsItem], Any) -> None
        super().__init__(parent, **kwargs)
        self.setFlag(QGraphicsItem.ItemHasNoContents)
        self.setFlag(QGraphicsItem.ItemIsFocusable)

        self.__line = QLineF()
        self.__points = \
            [ControlPoint(self, ControlPoint.TopLeft),  # TopLeft is line start
             ControlPoint(self, ControlPoint.BottomRight)  # line end
             ]

        self.__activeControl = None  # type: Optional[ControlPoint]

        if self.scene():
            self.__installFilter()

        for p in self.__points:
            p.setFlag(QGraphicsItem.ItemIsFocusable)
            p.setFocusProxy(self)

    def setLine(self, line):
        # type: (QLineF) -> None
        if not isinstance(line, QLineF):
            raise TypeError()

        if line != self.__line:
            self.__line = QLineF(line)
            self.__pointsLayout()
            self.lineChanged.emit(line)

    def line(self):
        # type: () -> QLineF
        return QLineF(self.__line)

    def isControlActive(self):
        # type: () -> bool
        """Return the state of the control. True if the control is
        active (user is dragging one of the points) False otherwise.
        """
        return self.__activeControl is not None

    def __installFilter(self):
        # type: () -> None
        for p in self.__points:
            p.installSceneEventFilter(self)

    def itemChange(self, change, value):
        # type: (QGraphicsItem.GraphicsItemChange, Any) -> Any
        if change == QGraphicsItem.ItemSceneHasChanged:
            if self.scene():
                self.__installFilter()
        return super().itemChange(change, value)

    def sceneEventFilter(self, obj, event):
        # type: (QGraphicsItem, QEvent) -> bool
        obj = toGraphicsObjectIfPossible(obj)
        if isinstance(obj, ControlPoint):
            etype = event.type()
            if etype in (QEvent.GraphicsSceneMousePress,
                         QEvent.GraphicsSceneMouseDoubleClick):
                self.__setActiveControl(obj)
            elif etype == QEvent.GraphicsSceneMouseRelease:
                self.__setActiveControl(None)
        return super().sceneEventFilter(obj, event)

    def __pointsLayout(self):
        # type: () -> None
        self.__points[0].setPos(self.__line.p1())
        self.__points[1].setPos(self.__line.p2())

    def __setActiveControl(self, control):
        # type: (Optional[ControlPoint]) -> None
        if self.__activeControl != control:
            if self.__activeControl is not None:
                self.__activeControl.positionChanged[QPointF].disconnect(
                    self.__activeControlMoved
                )

            self.__activeControl = control

            if control is not None:
                control.positionChanged[QPointF].connect(
                    self.__activeControlMoved
                )

    def __activeControlMoved(self, pos):
        # type: (QPointF) -> None
        line = QLineF(self.__line)
        control = self.__activeControl
        assert control is not None
        if control.anchor() == ControlPoint.TopLeft:
            line.setP1(pos)
        elif control.anchor() == ControlPoint.BottomRight:
            line.setP2(pos)

        if self.__line != line:
            self.blockSignals(True)
            self.setLine(line)
            self.blockSignals(False)
            self.lineEdited.emit(line)

    def boundingRect(self):
        # type: () -> QRectF
        return QRectF()

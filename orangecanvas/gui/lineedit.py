"""
A LineEdit class with a button on left/right side.
"""

from collections import namedtuple

from typing import Any, Optional, List, NamedTuple

from AnyQt.QtWidgets import (
    QLineEdit, QToolButton, QStyleOptionToolButton, QStylePainter,
    QStyle, QAction, QWidget,
)
from AnyQt.QtGui import QPaintEvent, QPainter, QColor
from AnyQt.QtCore import Qt, QSize, QRect
from AnyQt.QtCore import pyqtSignal as Signal, pyqtProperty as Property

from orangecanvas.gui.utils import innerShadowPixmap

_ActionSlot = NamedTuple(
    "_ActionSlot", [
        ("position", 'int'),  # Left/Right position
        ("action", 'QAction'),  # QAction
        ("button", 'LineEditButton'),   # LineEditButton instance
        ("autoHide", 'Any'),  # Auto hide when line edit is empty (unused??)
    ]
)


class LineEditButton(QToolButton):
    """
    A button in the :class:`LineEdit`.
    """
    def __init__(self, parent=None, flat=True, **kwargs):
        # type: (Optional[QWidget], bool, Any) -> None
        super().__init__(parent, **kwargs)
        self.__flat = flat
        self.__shadowLength = 5
        self.__shadowPosition = 0
        self.__shadowColor = QColor("#000000")

    def setFlat(self, flat):
        # type: (bool) -> None
        if self.__flat != flat:
            self.__flat = flat
            self.update()

    def flat(self):
        # type: () -> bool
        return self.__flat

    flat_ = Property(bool, fget=flat, fset=setFlat,
                     designable=True)

    def setShadowLength(self, shadowSize):
        if self.__shadowLength != shadowSize:
            self.__shadowLength = shadowSize
            self.update()

    def shadowLength(self):
        return self.__shadowLength

    shadowLength_ = Property(int, fget=shadowLength, fset=setShadowLength, designable=True)

    def setShadowPosition(self, shadowPosition):
        if self.__shadowPosition != shadowPosition:
            self.__shadowPosition = shadowPosition
            self.update()

    def shadowPosition(self):
        return self.__shadowPosition

    shadowPosition_ = Property(int, fget=shadowPosition, fset=setShadowPosition, designable=True)

    def setShadowColor(self, shadowColor):
        if self.__shadowColor != shadowColor:
            self.__shadowColor = shadowColor
            self.update()

    def shadowColor(self):
        return self.__shadowColor

    shadowColor_ = Property(QColor, fget=shadowColor, fset=setShadowColor, designable=True)

    def paintEvent(self, event):
        # type: (QPaintEvent) -> None
        if self.__flat:
            opt = QStyleOptionToolButton()
            self.initStyleOption(opt)
            p = QStylePainter(self)
            p.drawControl(QStyle.CE_ToolButtonLabel, opt)
            p.end()
        else:
            super().paintEvent(event)

        # paint shadow
        shadow = innerShadowPixmap(self.__shadowColor,
                                   self.size(),
                                   self.__shadowPosition,
                                   length=self.__shadowLength)

        p = QPainter(self)

        rect = self.rect()
        targetRect = QRect(rect.left() + 1,
                           rect.top() + 1,
                           rect.width() - 2,
                           rect.height() - 2)

        p.drawPixmap(targetRect, shadow, shadow.rect())
        p.end()


class LineEdit(QLineEdit):
    """
    A line edit widget with support for adding actions (buttons) to
    the left/right of the edited text

    """
    #: Position flags
    LeftPosition, RightPosition = 1, 2

    #: Emitted when the action is triggered.
    triggered = Signal(QAction)

    #: The left action was triggered.
    leftTriggered = Signal()

    #: The right action was triggered.
    rightTriggered = Signal()

    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None
        super().__init__(*args, **kwargs)
        self.__actions = [None, None]  # type: List[Optional[_ActionSlot]]

    def setAction(self, action, position=LeftPosition):
        # type: (QAction, int) -> None
        """
        Set `action` to be displayed at `position`. Existing action
        (if present) will be removed.

        Parameters
        ----------
        action : :class:`QAction`
        position : int
            Position where to set the action (default: ``LeftPosition``).
        """
        curr = self.actionAt(position)
        if curr is not None:
            self.removeActionAt(position)

        # Add the action using QWidget.addAction (for shortcuts)
        self.addAction(action)

        button = LineEditButton(self)
        button.setToolButtonStyle(Qt.ToolButtonIconOnly)
        button.setDefaultAction(action)
        button.setVisible(self.isVisible())
        button.show()
        button.setCursor(Qt.ArrowCursor)

        button.triggered.connect(self.triggered)
        button.triggered.connect(self.__onTriggered)

        slot = _ActionSlot(position, action, button, False)
        self.__actions[position - 1] = slot

        if not self.testAttribute(Qt.WA_Resized):
            # Need some sensible height to do the layout.
            self.adjustSize()

        self.__layoutActions()

    def actionAt(self, position):
        # type: (int) -> Optional[QAction]
        """
        Return :class:`QAction` at `position`.
        """
        self._checkPosition(position)
        slot = self.__actions[position - 1]
        if slot:
            return slot.action
        else:
            return None

    def removeActionAt(self, position):
        # type: (int) -> None
        """
        Remove the action at position.
        """
        self._checkPosition(position)

        slot = self.__actions[position - 1]
        self.__actions[position - 1] = None
        if slot is not None:
            slot.button.hide()
            slot.button.deleteLater()
            self.removeAction(slot.action)
            self.__layoutActions()

    def button(self, position):
        # type: (int) -> Optional[LineEditButton]
        """
        Return the button (:class:`LineEditButton`) for the action
        at `position`.

        """
        self._checkPosition(position)
        slot = self.__actions[position - 1]
        if slot is not None:
            return slot.button
        else:
            return None

    def _checkPosition(self, position):
        # type: (int) -> None
        if position not in [self.LeftPosition, self.RightPosition]:
            raise ValueError("Invalid position")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.__layoutActions()

    def __layoutActions(self):  # type: () -> None
        left, right = self.__actions

        contents = self.contentsRect()
        buttonSize = QSize(contents.height(), contents.height())

        margins = self.textMargins()

        if left:
            geom = QRect(contents.topLeft(), buttonSize)
            left.button.setGeometry(geom)
            margins.setLeft(buttonSize.width())

        if right:
            geom = QRect(contents.topRight(), buttonSize)
            right.button.setGeometry(geom.translated(-buttonSize.width(), 0))
            margins.setLeft(buttonSize.width())

        self.setTextMargins(margins)

    def __onTriggered(self, action):
        # type: (QAction) -> None
        left, right = self.__actions
        if left and action == left.action:
            self.leftTriggered.emit()
        elif right and action == right.action:
            self.rightTriggered.emit()

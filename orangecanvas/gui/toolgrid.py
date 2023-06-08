"""
A widget containing a grid of clickable actions/buttons.
"""
import sys
from collections import deque

from typing import NamedTuple, List, Iterable, Optional, Any, Union, cast

from AnyQt.QtWidgets import (
    QFrame, QAction, QToolButton, QGridLayout, QSizePolicy,
    QStyleOptionToolButton, QStylePainter, QStyle, QApplication,
    QWidget
)
from AnyQt.QtGui import (
    QFont, QFontMetrics, QActionEvent, QPaintEvent, QResizeEvent,
)
from AnyQt.QtCore import Qt, QObject, QSize, QEvent, QSignalMapper
from AnyQt.QtCore import Signal, Slot

from orangecanvas.registry import WidgetDescription

__all__ = [
    "ToolGrid"
]

_ToolGridSlot = NamedTuple(
    "_ToolGridSlot", (
        ("button", QToolButton),
        ("action", QAction),
        ("row", int),
        ("column", int),
    )
)


def qfont_scaled(font, factor):
    # type: (QFont, float) -> QFont
    scaled = QFont(font)
    if font.pointSizeF() != -1:
        scaled.setPointSizeF(font.pointSizeF() * factor)
    elif font.pixelSize() != -1:
        scaled.setPixelSize(int(font.pixelSize() * factor))
    return scaled


class ToolGridButton(QToolButton):
    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QWidget], Any) -> None
        super().__init__(parent, **kwargs)
        self.__text = ""
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        if sys.platform != "darwin":
            font = QApplication.font("QWidget")
            self.setFont(qfont_scaled(font, 0.85))
            self.setAttribute(Qt.WA_SetFont, False)

    def actionEvent(self, event):
        # type: (QActionEvent) -> None
        super().actionEvent(event)
        if event.type() == QEvent.ActionChanged or \
                event.type() == QEvent.ActionAdded:
            self.__textLayout()

    def resizeEvent(self, event):
        # type: (QResizeEvent) -> None
        super().resizeEvent(event)
        self.__textLayout()

    def __textLayout(self):
        # type:  () -> None
        fm = self.fontMetrics()
        desc = self.defaultAction().data()
        if isinstance(desc, WidgetDescription) and desc.short_name:
            self.__text = desc.short_name
            return
        text = self.defaultAction().text()
        words = text.split()

        option = QStyleOptionToolButton()
        option.initFrom(self)

        margin = self.style().pixelMetric(QStyle.PM_ButtonMargin, option, self)
        min_width = self.width() - 2 * margin

        lines = []

        if fm.boundingRect(" ".join(words)).width() <= min_width or len(words) <= 1:
            lines = [" ".join(words)]
        else:
            best_w, best_l = sys.maxsize, ['', '']
            for i in range(1, len(words)):
                l1 = " ".join(words[:i])
                l2 = " ".join(words[i:])
                width = max(
                    fm.boundingRect(l1).width(),
                    fm.boundingRect(l2).width()
                )
                if width < best_w:
                    best_w = width
                    best_l = [l1, l2]
            lines = best_l

        # elide the end of each line if too long
        lines = [
            fm.elidedText(l, Qt.ElideRight, self.width() - margin)
            for l in lines
        ]

        text = "\n".join(lines)
        text = text.replace('&', '&&')  # Need escaped ampersand to show

        self.__text = text

    def paintEvent(self, event):
        # type: (QPaintEvent) -> None
        p = QStylePainter(self)
        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)
        p.drawComplexControl(QStyle.CC_ToolButton, opt)
        p.end()

    def initStyleOption(self, option):
        # type: (QStyleOptionToolButton) -> None
        super().initStyleOption(option)
        if self.__text:
            option.text = self.__text

    def sizeHint(self):
        # type: () -> QSize
        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)
        style = self.style()
        csize = opt.iconSize  # type: QSize
        fm = opt.fontMetrics  # type: QFontMetrics
        margin = style.pixelMetric(QStyle.PM_ButtonMargin)
        # content size is:
        #   * vertical: icon + margin + 2 * font ascent
        #   * horizontal: icon * 3 / 2

        csize.setHeight(csize.height() + margin + 2 * fm.lineSpacing())
        csize.setWidth(csize.width() * 3 // 2)
        size = style.sizeFromContents(
            QStyle.CT_ToolButton, opt, csize, self)
        return size


class ToolGrid(QFrame):
    """
    A widget containing a grid of actions/buttons.

    Actions can be added using standard :func:`QWidget.addAction(QAction)`
    and :func:`QWidget.insertAction(int, QAction)` methods.

    Parameters
    ----------
    parent : :class:`QWidget`
        Parent widget.
    columns : int
        Number of columns in the grid layout.
    buttonSize : QSize
        Size of tool buttons in the grid.
    iconSize : QSize
        Size of icons in the buttons.
    toolButtonStyle : :class:`Qt.ToolButtonStyle`
        Tool button style.
    """
    #: Signal emitted when an action is triggered
    actionTriggered = Signal(QAction)
    #: Signal emitted when an action is hovered
    actionHovered = Signal(QAction)

    def __init__(self,
                 parent=None, columns=4, buttonSize=QSize(),
                 iconSize=QSize(), toolButtonStyle=Qt.ToolButtonTextUnderIcon,
                 **kwargs):
        # type: (Optional[QWidget], int, QSize, QSize, Qt.ToolButtonStyle, Any) -> None
        sizePolicy = kwargs.pop("sizePolicy", None)  # type: Optional[QSizePolicy]
        super().__init__(parent, **kwargs)

        if buttonSize is None:
            buttonSize = QSize()
        if iconSize is None:
            iconSize = QSize()

        self.__columns = columns
        self.__buttonSize = QSize(buttonSize)
        self.__iconSize = QSize(iconSize)
        self.__toolButtonStyle = toolButtonStyle

        self.__gridSlots = []  # type: List[_ToolGridSlot]
        self.__mapper = QSignalMapper()
        self.__mapper.mappedObject.connect(self.__onClicked)

        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setColumnStretch(columns - 1, 1000)
        self.setLayout(layout)
        if sizePolicy is None:
            self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.MinimumExpanding)
            self.setAttribute(Qt.WA_WState_OwnSizePolicy, True)
        else:
            self.setSizePolicy(sizePolicy)

    def setButtonSize(self, size):
        # type: (QSize) -> None
        """
        Set the button size.
        """
        if self.__buttonSize != size:
            self.__buttonSize = QSize(size)
            for slot in self.__gridSlots:
                slot.button.setFixedSize(size)

    def buttonSize(self):
        # type: () -> QSize
        """
        Return the button size.
        """
        return QSize(self.__buttonSize)

    def setIconSize(self, size):
        # type: (QSize) -> None
        """
        Set the button icon size.

        The default icon size is style defined.
        """
        if self.__iconSize != size:
            self.__iconSize = QSize(size)
            size = self.__effectiveIconSize()
            for slot in self.__gridSlots:
                slot.button.setIconSize(size)

    def iconSize(self):
        # type: () -> QSize
        """
        Return the icon size. If no size is set a default style defined size
        is returned.
        """
        return self.__effectiveIconSize()

    def __effectiveIconSize(self):
        # type: () -> QSize
        if not self.__iconSize.isValid():
            opt = QStyleOptionToolButton()
            opt.initFrom(self)
            s = self.style().pixelMetric(QStyle.PM_LargeIconSize, opt, None)
            return QSize(s, s)
        else:
            return QSize(self.__iconSize)

    def changeEvent(self, event):
        # type: (QEvent) -> None
        if event.type() == QEvent.StyleChange:
            size = self.__effectiveIconSize()
            for item in self.__gridSlots:
                item.button.setIconSize(size)
        super().changeEvent(event)

    def setToolButtonStyle(self, style):
        # type: (Qt.ToolButtonStyle) -> None
        """
        Set the tool button style.
        """
        if self.__toolButtonStyle != style:
            self.__toolButtonStyle = style
            for slot in self.__gridSlots:
                slot.button.setToolButtonStyle(style)

    def toolButtonStyle(self):
        # type: () -> Qt.ToolButtonStyle
        """
        Return the tool button style.
        """
        return self.__toolButtonStyle

    def setColumnCount(self, columns):
        # type: (int) -> None
        """
        Set the number of button/action columns.
        """
        if self.__columns != columns:
            layout = cast(QGridLayout, self.layout())
            layout.setColumnStretch(self.__columns - 1, 0)
            layout.setColumnStretch(columns - 1, 1000)
            self.__columns = columns
            self.__relayout()

    def columns(self):
        # type: () -> int
        """
        Return the number of columns in the grid.
        """
        return self.__columns

    def clear(self):
        # type: () -> None
        """
        Clear all actions/buttons.
        """
        for slot in reversed(list(self.__gridSlots)):
            self.removeAction(slot.action)
        self.__gridSlots = []

    def insertAction(self, before, action):
        # type: (Union[QAction, int], QAction) -> None
        """
        Insert a new action at the position currently occupied
        by `before` (can also be an index).

        Parameters
        ----------
        before : :class:`QAction` or int
            Position where the `action` should be inserted.
        action : :class:`QAction`
            Action to insert
        """
        if isinstance(before, int):
            actions = list(self.actions())
            if len(actions) == 0 or before >= len(actions):
                # Insert as the first action or the last action.
                return self.addAction(action)

            before = actions[before]

        return super().insertAction(before, action)

    def setActions(self, actions):
        # type: (Iterable[QAction]) -> None
        """
        Clear the grid and add `actions`.
        """
        self.clear()

        for action in actions:
            self.addAction(action)

    def buttonForAction(self, action):
        # type: (QAction) -> QToolButton
        """
        Return the :class:`QToolButton` instance button for `action`.
        """
        actions = [slot.action for slot in self.__gridSlots]
        index = actions.index(action)
        return self.__gridSlots[index].button

    def createButtonForAction(self, action):
        # type: (QAction) -> QToolButton
        """
        Create and return a :class:`QToolButton` for action.
        """
        button = ToolGridButton(self)
        button.setDefaultAction(action)

        if self.__buttonSize.isValid():
            button.setFixedSize(self.__buttonSize)
        button.setIconSize(self.__effectiveIconSize())
        button.setToolButtonStyle(self.__toolButtonStyle)
        button.setProperty("tool-grid-button", True)
        return button

    def count(self):
        # type: () -> int
        """
        Return the number of buttons/actions in the grid.
        """
        return len(self.__gridSlots)

    def actionEvent(self, event):
        # type: (QActionEvent) -> None
        super().actionEvent(event)

        if event.type() == QEvent.ActionAdded:
            # Note: the action is already in the self.actions() list.
            actions = list(self.actions())
            index = actions.index(event.action())
            self.__insertActionButton(index, event.action())

        elif event.type() == QEvent.ActionRemoved:
            self.__removeActionButton(event.action())

    def __insertActionButton(self, index, action):
        # type: (int, QAction) -> None
        """Create a button for the action and add it to the layout at index.
        """
        self.__shiftGrid(index, 1)
        button = self.createButtonForAction(action)

        row = index // self.__columns
        column = index % self.__columns

        layout = cast(QGridLayout, self.layout())
        layout.addWidget(button, row, column, alignment=Qt.AlignTop | Qt.AlignLeft)

        self.__gridSlots.insert(
            index, _ToolGridSlot(button, action, row, column)
        )

        self.__mapper.setMapping(button, action)
        button.clicked.connect(self.__mapper.map)
        button.installEventFilter(self)

    def __removeActionButton(self, action):
        # type: (QAction) -> None
        """Remove the button for the action from the layout and delete it.
        """
        actions = [slot.action for slot in self.__gridSlots]
        index = actions.index(action)
        slot = self.__gridSlots.pop(index)

        slot.button.removeEventFilter(self)
        self.__mapper.removeMappings(slot.button)

        self.layout().removeWidget(slot.button)
        self.__shiftGrid(index + 1, -1)

        slot.button.deleteLater()

    def __shiftGrid(self, start, count=1):
        # type: (int, int) -> None
        """Shift all buttons starting at index `start` by `count` cells.
        """
        layout = cast(QGridLayout, self.layout())
        cell_count = layout.rowCount() * layout.columnCount()
        columns = self.__columns

        direction = 1 if count >= 0 else -1
        if direction == 1:
            start, end = cell_count - 1, start - 1
        else:
            start, end = start, cell_count

        for index in range(start, end, -direction):
            item = layout.itemAtPosition(
                index // columns, index % columns
            )
            if item:
                button = item.widget()
                new_index = index + count
                layout.addWidget(
                    button, new_index // columns, new_index % columns, Qt.AlignLeft | Qt.AlignTop
                )

    def __relayout(self):
        # type: () -> None
        """Relayout the buttons.
        """
        layout = cast(QGridLayout, self.layout())
        for i in reversed(range(layout.count())):
            layout.takeAt(i)

        self.__gridSlots = [
            _ToolGridSlot(slot.button, slot.action,
                          i // self.__columns, i % self.__columns)
            for i, slot in enumerate(self.__gridSlots)
        ]
        for slot in self.__gridSlots:
            layout.addWidget(slot.button, slot.row, slot.column)

    def __indexOf(self, button):
        # type: (QWidget) -> int
        """Return the index of button widget.
        """
        buttons = [slot.button for slot in self.__gridSlots]
        return buttons.index(button)

    def __onButtonEnter(self, button):
        # type: (QToolButton) -> None
        action = button.defaultAction()
        self.actionHovered.emit(action)

    @Slot(QObject)
    def __onClicked(self, action):
        # type: (QAction) -> None
        assert isinstance(action, QAction)
        self.actionTriggered.emit(action)

    def eventFilter(self, obj, event):
        # type: (QObject, QEvent) -> bool
        etype = event.type()
        if etype == QEvent.KeyPress and obj.hasFocus():
            key = event.key()
            if key in [Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right]:
                if self.__focusMove(obj, key):
                    event.accept()
                    return True
        elif etype == QEvent.HoverEnter and obj.parent() is self:
            self.__onButtonEnter(obj)
        return super().eventFilter(obj, event)

    def focusNextPrevChild(self, next: bool) -> bool:
        return self.__focusMove(
            self.focusWidget(), Qt.Key_Right if next else Qt.Key_Left
        )

    def __focusMove(self, focus, key):
        # type: (QWidget, Qt.Key) -> bool
        assert focus is self.focusWidget()
        try:
            index = self.__indexOf(focus)
        except IndexError:
            return False

        if key == Qt.Key_Down:
            index += self.__columns
        elif key == Qt.Key_Up:
            index -= self.__columns
        elif key == Qt.Key_Left:
            index -= 1
        elif key == Qt.Key_Right:
            index += 1

        if 0 <= index < self.count():
            button = self.__gridSlots[index].button
            button.setFocus(Qt.TabFocusReason)
            return True
        else:
            return False

    def sizeHint(self) -> QSize:
        sh = super().sizeHint()
        if self.__buttonSize.isValid():
            width = self.__buttonSize.width()
        else:
            option = QStyleOptionToolButton()
            option.initFrom(self)
            option.iconSize = self.iconSize()
            option.toolButtonStyle = self.toolButtonStyle()
            csize = QSize(option.iconSize)
            csize.setWidth(csize.width() * 3 // 2)  # see ToolGridButton
            size = self.style().sizeFromContents(QStyle.CT_ToolButton, option, csize, None)
            width = size.width()
        layout = self.layout()
        spacing = layout.horizontalSpacing()
        columns = self.__columns
        width = width * columns + (max(columns - 1, 0) * spacing)
        sh.setWidth(max(sh.width(), width))
        return sh

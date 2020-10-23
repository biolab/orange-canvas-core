"""
===============
Tool Box Widget
===============

A reimplementation of the :class:`QToolBox` widget that keeps all the tabs
in a single :class:`QScrollArea` instance and can keep multiple open tabs.
"""
from operator import eq, attrgetter

import typing
from typing import NamedTuple, List, Iterable, Optional, Any, Callable

from AnyQt.QtWidgets import (
    QWidget, QFrame, QSizePolicy, QStyle, QStyleOptionToolButton,
    QStyleOptionToolBox, QScrollArea, QVBoxLayout, QToolButton,
    QAction, QActionGroup, QApplication, QAbstractButton, QWIDGETSIZE_MAX,
)
from AnyQt.QtGui import (
    QIcon, QFontMetrics, QPainter, QPalette, QBrush, QPen, QColor, QFont
)
from AnyQt.QtCore import (
    Qt, QObject, QSize, QRect, QPoint, QSignalMapper
)
from AnyQt.QtCore import Signal, Property

from ..utils import set_flag
from .utils import brush_darker, ScrollBar

__all__ = [
    "ToolBox"
]

_ToolBoxPage = NamedTuple(
    "_ToolBoxPage", [
        ("index", int),
        ("widget", QWidget),
        ("action", QAction),
        ("button", QAbstractButton),
    ]
)


class ToolBoxTabButton(QToolButton):
    """
    A tab button for an item in a :class:`ToolBox`.
    """

    def setNativeStyling(self, state):
        # type: (bool) -> None
        """
        Render tab buttons as native (or css styled) :class:`QToolButtons`.
        If set to `False` (default) the button is pained using a custom
        paint routine.
        """
        self.__nativeStyling = state
        self.update()

    def nativeStyling(self):
        # type: () -> bool
        """
        Use :class:`QStyle`'s to paint the class:`QToolButton` look.
        """
        return self.__nativeStyling

    nativeStyling_ = Property(bool,
                              fget=nativeStyling,
                              fset=setNativeStyling,
                              designable=True)

    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QWidget], Any) -> None
        self.__nativeStyling = False
        self.position = QStyleOptionToolBox.OnlyOneTab
        self.selected = QStyleOptionToolBox.NotAdjacent
        font = kwargs.pop("font", None)  # type: Optional[QFont]
        super().__init__(parent, **kwargs)

        if font is None:
            self.setFont(QApplication.font("QAbstractButton"))
            self.setAttribute(Qt.WA_SetFont, False)
        else:
            self.setFont(font)

    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event):
        if self.__nativeStyling:
            super().paintEvent(event)
        else:
            self.__paintEventNoStyle()

    def __paintEventNoStyle(self):
        p = QPainter(self)
        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)

        fm = QFontMetrics(opt.font)
        palette = opt.palette

        # highlight brush is used as the background for the icon and background
        # when the tab is expanded and as mouse hover color (lighter).
        brush_highlight = palette.highlight()
        foregroundrole = QPalette.ButtonText
        if opt.state & QStyle.State_Sunken:
            # State 'down' pressed during a mouse press (slightly darker).
            background_brush = brush_darker(brush_highlight, 110)
            foregroundrole = QPalette.HighlightedText
        elif opt.state & QStyle.State_MouseOver:
            background_brush = brush_darker(brush_highlight, 95)
            foregroundrole = QPalette.HighlightedText
        elif opt.state & QStyle.State_On:
            background_brush = brush_highlight
            foregroundrole = QPalette.HighlightedText
        else:
            # The default button brush.
            background_brush = palette.button()

        rect = opt.rect

        icon_area_rect = QRect(rect)
        icon_area_rect.setWidth(int(icon_area_rect.height() * 1.26))

        text_rect = QRect(rect)
        text_rect.setLeft(icon_area_rect.x() + icon_area_rect.width() + 10)

        # Background

        # TODO: Should the tab button have native toolbutton shape, drawn
        #       using PE_PanelButtonTool or even QToolBox tab shape
        # Default outline pen
        pen = QPen(palette.color(QPalette.Mid))

        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(background_brush))
        p.drawRect(rect)

        # Draw the background behind the icon if the background_brush
        # is different.
        if not opt.state & QStyle.State_On:
            p.setBrush(brush_highlight)
            p.drawRect(icon_area_rect)
            # Line between the icon and text
            p.setPen(pen)
            p.drawLine(
                icon_area_rect.x() + icon_area_rect.width(), icon_area_rect.y(),
                icon_area_rect.x() + icon_area_rect.width(),
                icon_area_rect.y() + icon_area_rect.height())

        if opt.state & QStyle.State_HasFocus:
            # Set the focus frame pen and draw the border
            pen = QPen(QColor(brush_highlight))
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            # Adjust for pen
            rect = rect.adjusted(0, 0, -1, -1)
            p.drawRect(rect)

        else:
            p.setPen(pen)
            # Draw the top/bottom border
            if self.position == QStyleOptionToolBox.OnlyOneTab or \
                    self.position == QStyleOptionToolBox.Beginning or \
                    self.selected & QStyleOptionToolBox.PreviousIsSelected:
                p.drawLine(rect.x(), rect.y(),
                           rect.x() + rect.width(), rect.y())
            p.drawLine(rect.x(), rect.y() + rect.height(),
                       rect.x() + rect.width(), rect.y() + rect.height())

        p.restore()

        p.save()
        text = fm.elidedText(opt.text, Qt.ElideRight, text_rect.width())
        p.setPen(QPen(palette.color(foregroundrole)))
        p.setFont(opt.font)

        p.drawText(text_rect,
                   int(Qt.AlignVCenter | Qt.AlignLeft) |
                   int(Qt.TextSingleLine),
                   text)

        if not opt.icon.isNull():
            if opt.state & QStyle.State_Enabled:
                mode = QIcon.Normal
            else:
                mode = QIcon.Disabled
            if opt.state & QStyle.State_On:
                state = QIcon.On
            else:
                state = QIcon.Off
            icon_area_rect = icon_area_rect
            icon_rect = QRect(QPoint(0, 0), opt.iconSize)
            icon_rect.moveCenter(icon_area_rect.center())
            opt.icon.paint(p, icon_rect, Qt.AlignCenter, mode, state)
        p.restore()


class _ToolBoxLayout(QVBoxLayout):
    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None
        self.__minimumSize = None  # type: Optional[QSize]
        self.__maximumSize = None  # type: Optional[QSize]
        super().__init__(*args, **kwargs)

    def minimumSize(self):  # type: () -> QSize
        """Reimplemented from `QBoxLayout.minimumSize`."""
        if self.__minimumSize is None:
            msize = super().minimumSize()
            # Extend the minimum size by including the minimum width of
            # hidden widgets (which QBoxLayout ignores), so the minimum
            # width does not depend on the tab open/close state.
            for i in range(self.count()):
                item = self.itemAt(i)
                if item.isEmpty() and item.widget() is not None:
                    msize.setWidth(max(item.widget().minimumWidth(),
                                       msize.width()))
            self.__minimumSize = msize

        return self.__minimumSize

    def maximumSize(self):  # type: () -> QSize
        """Reimplemented from `QBoxLayout.maximumSize`."""
        msize = super().maximumSize()
        # Allow the contents to grow horizontally (expand within the
        # containing scroll area - joining the tab buttons to the
        # right edge), but have a suitable maximum height (displaying an
        # empty area on the bottom if the contents are smaller then the
        # viewport).
        msize.setWidth(QWIDGETSIZE_MAX)
        return msize

    def invalidate(self):  # type: () -> None
        """Reimplemented from `QVBoxLayout.invalidate`."""
        self.__minimumSize = None
        self.__maximumSize = None
        super().invalidate()


class ToolBox(QFrame):
    """
    A tool box widget.
    """
    # Signal emitted when a tab is toggled.
    tabToggled = Signal(int, bool)

    __exclusive = False  # type: bool

    def setExclusive(self, exclusive):  # type: (bool) -> None
        """
        Set exclusive tabs (only one tab can be open at a time).
        """
        if self.__exclusive != exclusive:
            self.__exclusive = exclusive
            self.__tabActionGroup.setExclusive(exclusive)
            checked = self.__tabActionGroup.checkedAction()
            if checked is None:
                # The action group can be out of sync with the actions state
                # when switching between exclusive states.
                actions_checked = [page.action for page in self.__pages
                                   if page.action.isChecked()]
                if actions_checked:
                    checked = actions_checked[0]

            # Trigger/toggle remaining open pages
            if exclusive and checked is not None:
                for page in self.__pages:
                    if checked != page.action and page.action.isChecked():
                        page.action.trigger()

    def exclusive(self):  # type: () -> bool
        """
        Are the tabs in the toolbox exclusive.
        """
        return self.__exclusive

    exclusive_ = Property(bool,
                          fget=exclusive,
                          fset=setExclusive,
                          designable=True,
                          doc="Exclusive tabs")

    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QWidget], Any)-> None
        super().__init__(parent, **kwargs)
        self.__pages = []  # type: List[_ToolBoxPage]
        self.__tabButtonHeight = -1
        self.__tabIconSize = QSize()
        self.__exclusive = False
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area for the contents.
        self.__scrollArea = QScrollArea(
            self, objectName="toolbox-scroll-area",
            sizePolicy=QSizePolicy(QSizePolicy.MinimumExpanding,
                                   QSizePolicy.MinimumExpanding),
            horizontalScrollBarPolicy=Qt.ScrollBarAlwaysOff,
            widgetResizable=True,
        )
        sb = ScrollBar()
        sb.styleChange.connect(self.updateGeometry)
        self.__scrollArea.setVerticalScrollBar(sb)
        self.__scrollArea.setFrameStyle(QScrollArea.NoFrame)

        # A widget with all of the contents.
        # The tabs/contents are placed in the layout inside this widget
        self.__contents = QWidget(self.__scrollArea,
                                  objectName="toolbox-contents")
        self.__contentsLayout = _ToolBoxLayout(
            sizeConstraint=_ToolBoxLayout.SetMinAndMaxSize,
            spacing=0
        )
        self.__contentsLayout.setContentsMargins(0, 0, 0, 0)
        self.__contents.setLayout(self.__contentsLayout)

        self.__scrollArea.setWidget(self.__contents)

        layout.addWidget(self.__scrollArea)

        self.setLayout(layout)
        self.setSizePolicy(QSizePolicy.Fixed,
                           QSizePolicy.MinimumExpanding)

        self.__tabActionGroup = QActionGroup(
            self, objectName="toolbox-tab-action-group",
        )
        self.__tabActionGroup.setExclusive(self.__exclusive)
        self.__actionMapper = QSignalMapper(self)
        self.__actionMapper.mapped[QObject].connect(self.__onTabActionToggled)

    def setTabButtonHeight(self, height):
        # type: (int) -> None
        """
        Set the tab button height.
        """
        if self.__tabButtonHeight != height:
            self.__tabButtonHeight = height
            for page in self.__pages:
                page.button.setFixedHeight(height)

    def tabButtonHeight(self):
        # type: () -> int
        """
        Return the tab button height.
        """
        return self.__tabButtonHeight

    def setTabIconSize(self, size):
        # type: (QSize) -> None
        """
        Set the tab button icon size.
        """
        if self.__tabIconSize != size:
            self.__tabIconSize = QSize(size)
            for page in self.__pages:
                page.button.setIconSize(size)

    def tabIconSize(self):
        # type: () -> QSize
        """
        Return the tab icon size.
        """
        return QSize(self.__tabIconSize)

    def tabButton(self, index):
        # type: (int) -> QAbstractButton
        """
        Return the tab button at `index`
        """
        return self.__pages[index].button

    def tabAction(self, index):
        # type: (int) -> QAction
        """
        Return open/close action for the tab at `index`.
        """
        return self.__pages[index].action

    def addItem(self, widget, text, icon=QIcon(), toolTip=""):
        # type: (QWidget, str, QIcon, str) -> int
        """
        Append the `widget` in a new tab and return its index.

        Parameters
        ----------
        widget : QWidget
            A widget to be inserted. The toolbox takes ownership
            of the widget.
        text : str
            Name/title of the new tab.
        icon : QIcon
            An icon for the tab button.
        toolTip : str
            Tool tip for the tab button.

        Returns
        -------
        index : int
            Index of the inserted tab
        """
        return self.insertItem(self.count(), widget, text, icon, toolTip)

    def insertItem(self, index, widget, text, icon=QIcon(), toolTip=""):
        # type: (int, QWidget, str, QIcon, str) -> int
        """
        Insert the `widget` in a new tab at position `index`.

        See also
        --------
        ToolBox.addItem
        """
        button = self.createTabButton(widget, text, icon, toolTip)

        self.__contentsLayout.insertWidget(index * 2, button)
        self.__contentsLayout.insertWidget(index * 2 + 1, widget)

        widget.hide()

        page = _ToolBoxPage(index, widget, button.defaultAction(), button)
        self.__pages.insert(index, page)

        # update the indices __pages list
        for i in range(index + 1, self.count()):
            self.__pages[i] = self.__pages[i]._replace(index=i)

        self.__updatePositions()

        # Show (open) the first tab.
        if self.count() == 1 and index == 0:
            page.action.trigger()

        self.__updateSelected()

        self.updateGeometry()
        return index

    def removeItem(self, index):
        # type: (int) -> None
        """
        Remove the widget at `index`.

        Note
        ----
        The widget is hidden but is is not deleted. It is up to the caller to
        delete it.
        """
        self.__contentsLayout.takeAt(2 * index + 1)
        self.__contentsLayout.takeAt(2 * index)
        page = self.__pages.pop(index)

        # Update the page indexes
        for i in range(index, self.count()):
            self.__pages[i] = self.__pages[i]._replace(index=i)

        page.button.deleteLater()

        # Hide the widget and reparent to self
        # This follows QToolBox.removeItem
        page.widget.hide()
        page.widget.setParent(self)

        self.__updatePositions()
        self.__updateSelected()

        self.updateGeometry()

    def count(self):
        # type: () -> int
        """
        Return the number of widgets inserted in the toolbox.
        """
        return len(self.__pages)

    def widget(self, index):
        # type: (int) -> QWidget
        """
        Return the widget at `index`.
        """
        return self.__pages[index].widget

    def createTabButton(self, widget, text, icon=QIcon(), toolTip=""):
        # type: (QWidget, str, QIcon, str) -> QAbstractButton
        """
        Create the tab button for `widget`.
        """
        action = QAction(text, self)
        action.setCheckable(True)

        if icon:
            action.setIcon(icon)

        if toolTip:
            action.setToolTip(toolTip)
        self.__tabActionGroup.addAction(action)
        self.__actionMapper.setMapping(action, action)
        action.toggled.connect(self.__actionMapper.map)

        button = ToolBoxTabButton(self, objectName="toolbox-tab-button")
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        button.setSizePolicy(QSizePolicy.Ignored,
                             QSizePolicy.Fixed)

        if self.__tabIconSize.isValid():
            button.setIconSize(self.__tabIconSize)

        if self.__tabButtonHeight > 0:
            button.setFixedHeight(self.__tabButtonHeight)

        return button

    def ensureWidgetVisible(self, child, xmargin=50, ymargin=50):
        # type: (QWidget, int, int) -> None
        """
        Scroll the contents so child widget instance is visible inside
        the viewport.
        """
        self.__scrollArea.ensureWidgetVisible(child, xmargin, ymargin)

    def sizeHint(self):
        # type: () -> QSize
        """
        Reimplemented.
        """
        hint = self.__contentsLayout.sizeHint()

        if self.count():
            # Compute max width of hidden widgets also.
            scroll = self.__scrollArea

            # check if scrollbar is transient
            scrollBar = self.__scrollArea.verticalScrollBar()
            transient = scrollBar.style().styleHint(QStyle.SH_ScrollBar_Transient,
                                                    widget=scrollBar)

            scroll_w = scroll.verticalScrollBar().sizeHint().width() if not transient else 0

            frame_w = self.frameWidth() * 2 + scroll.frameWidth() * 2
            max_w = max([p.widget.sizeHint().width() for p in self.__pages])
            hint = QSize(max(max_w, hint.width()) + scroll_w + frame_w,
                         hint.height())

        return QSize(200, 200).expandedTo(hint)

    def __onTabActionToggled(self, action):
        # type: (QAction) -> None
        page = find(self.__pages, action, key=attrgetter("action"))
        on = action.isChecked()
        page.widget.setVisible(on)
        index = page.index

        if index > 0:
            # Update the `previous` tab buttons style hints
            previous = self.__pages[index - 1].button
            previous.selected = set_flag(
                previous.selected, QStyleOptionToolBox.NextIsSelected, on
            )
            previous.update()
        if index < self.count() - 1:
            next = self.__pages[index + 1].button
            next.selected = set_flag(
                next.selected, QStyleOptionToolBox.PreviousIsSelected, on
            )
            next.update()

        self.tabToggled.emit(index, on)

        self.__contentsLayout.invalidate()

    def __updateSelected(self):
        # type: () -> None
        """Update the tab buttons selected style flags.
        """
        if self.count() == 0:
            return

        def update(button, next_sel, prev_sel):
            # type: (ToolBoxTabButton, bool, bool) -> None
            button.selected = set_flag(
                button.selected,
                QStyleOptionToolBox.NextIsSelected,
                next_sel
            )
            button.selected = set_flag(
                button.selected,
                QStyleOptionToolBox.PreviousIsSelected,
                prev_sel
            )
            button.update()

        if self.count() == 1:
            update(self.__pages[0].button, False, False)
        elif self.count() >= 2:
            pages = self.__pages
            for i in range(1, self.count() - 1):
                update(pages[i].button,
                       pages[i + 1].action.isChecked(),
                       pages[i - 1].action.isChecked())

    def __updatePositions(self):
        # type: () -> None
        """Update the tab buttons position style flags.
        """
        if self.count() == 0:
            return
        elif self.count() == 1:
            self.__pages[0].button.position = QStyleOptionToolBox.OnlyOneTab
        else:
            self.__pages[0].button.position = QStyleOptionToolBox.Beginning
            self.__pages[-1].button.position = QStyleOptionToolBox.End
            for p in self.__pages[1:-1]:
                p.button.position = QStyleOptionToolBox.Middle

        for p in self.__pages:
            p.button.update()


if typing.TYPE_CHECKING:
    A = typing.TypeVar("A")
    B = typing.TypeVar("B")
    C = typing.TypeVar("C")


def identity(arg):
    return arg


def find(iterable, what, key=identity, predicate=eq):
    # type: (Iterable[A], B, Callable[[A], C], Callable[[C, B], bool]) -> A
    """
    find(iterable, what, [key=None, [predicate=operator.eq]])
    """
    for item in iterable:
        item_key = key(item)
        if predicate(item_key, what):
            return item
    else:
        raise ValueError(what)

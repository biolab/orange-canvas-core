"""
Orange Canvas Tool Dock widget

"""
import sys
import warnings
from typing import Optional, Any

from AnyQt.QtWidgets import (
    QWidget, QSplitter, QVBoxLayout, QAction, QSizePolicy, QApplication,
    QToolButton, QTreeView)
from AnyQt.QtGui import QPalette, QBrush, QDrag, QResizeEvent, QHideEvent

from AnyQt.QtCore import (
    Qt, QSize, QObject, QPropertyAnimation, QEvent, QRect, QPoint,
    QAbstractItemModel, QModelIndex, QPersistentModelIndex, QEventLoop,
    QMimeData
)
from AnyQt.QtCore import pyqtProperty as Property, pyqtSignal as Signal

from ..gui.toolgrid import ToolGrid
from ..gui.toolbar import DynamicResizeToolBar
from ..gui.quickhelp import QuickHelp
from ..gui.framelesswindow import FramelessWindow
from ..gui.utils import create_css_gradient
from ..document.quickmenu import MenuPage
from .widgettoolbox import WidgetToolBox, iter_index, item_text, item_icon, item_tooltip
from ..registry.qt import QtWidgetRegistry


class SplitterResizer(QObject):
    """
    An object able to control the size of a widget in a QSplitter instance.
    """
    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QObject], Any) -> None
        super().__init__(parent, **kwargs)
        self.__splitter = None  # type: Optional[QSplitter]
        self.__widget = None    # type: Optional[QWidget]
        self.__updateOnShow = True  # Need __update on next show event
        self.__animationEnabled = True
        self.__size = -1
        self.__expanded = False
        self.__animation = QPropertyAnimation(
            self, b"size_", self, duration=200
        )
        self.__action = QAction("toggle-expanded", self, checkable=True)
        self.__action.triggered[bool].connect(self.setExpanded)

    def setSize(self, size):
        # type: (int) -> None
        """
        Set the size of the controlled widget (either width or height
        depending on the orientation).

        .. note::
            The controlled widget's size is only updated when it it is shown.
        """
        if self.__size != size:
            self.__size = size
            self.__update()

    def size(self):
        # type: () -> int
        """
        Return the size of the widget in the splitter (either height of
        width) depending on the splitter orientation.
        """
        if self.__splitter and self.__widget:
            index = self.__splitter.indexOf(self.__widget)
            sizes = self.__splitter.sizes()
            return sizes[index]
        else:
            return -1

    size_ = Property(int, fget=size, fset=setSize)

    def setAnimationEnabled(self, enable):
        # type: (bool) -> None
        """Enable/disable animation."""
        self.__animation.setDuration(0 if enable else 200)

    def animationEnabled(self):
        # type: () -> bool
        return self.__animation.duration() == 0

    def setSplitterAndWidget(self, splitter, widget):
        # type: (QSplitter, QWidget) -> None
        """Set the QSplitter and QWidget instance the resizer should control.

        .. note:: the widget must be in the splitter.
        """
        if splitter and widget and not splitter.indexOf(widget) > 0:
            raise ValueError("Widget must be in a splitter.")

        if self.__widget is not None:
            self.__widget.removeEventFilter(self)
        if self.__splitter is not None:
            self.__splitter.removeEventFilter(self)

        self.__splitter = splitter
        self.__widget = widget

        if widget is not None:
            widget.installEventFilter(self)
        if splitter is not None:
            splitter.installEventFilter(self)

        self.__update()

        size = self.size()
        if self.__expanded and size == 0:
            self.open()
        elif not self.__expanded and size > 0:
            self.close()

    def toggleExpandedAction(self):
        # type: () -> QAction
        """Return a QAction that can be used to toggle expanded state.
        """
        return self.__action

    def toogleExpandedAction(self):
        warnings.warn(
            "'toogleExpandedAction is deprecated, use 'toggleExpandedAction' "
            "instead.", DeprecationWarning, stacklevel=2
        )
        return self.toggleExpandedAction()

    def open(self):
        # type: () -> None
        """Open the controlled widget (expand it to sizeHint).
        """
        self.__expanded = True
        self.__action.setChecked(True)

        if self.__splitter is None or self.__widget is None:
            return

        hint = self.__widget.sizeHint()

        if self.__splitter.orientation() == Qt.Vertical:
            end = hint.height()
        else:
            end = hint.width()

        self.__animation.setStartValue(0)
        self.__animation.setEndValue(end)
        self.__animation.start()

    def close(self):
        # type: () -> None
        """Close the controlled widget (shrink to size 0).
        """
        self.__expanded = False
        self.__action.setChecked(False)

        if self.__splitter is None or self.__widget is None:
            return

        self.__animation.setStartValue(self.size())
        self.__animation.setEndValue(0)
        self.__animation.start()

    def setExpanded(self, expanded):
        # type: (bool) -> None
        """Set the expanded state."""
        if self.__expanded != expanded:
            if expanded:
                self.open()
            else:
                self.close()

    def expanded(self):
        # type: () -> bool
        """Return the expanded state."""
        return self.__expanded

    def __update(self):
        # type: () -> None
        """Update the splitter sizes."""
        if self.__splitter and self.__widget:
            if sum(self.__splitter.sizes()) == 0:
                # schedule update on next show event
                self.__updateOnShow = True
                return

            splitter = self.__splitter
            index = splitter.indexOf(self.__widget)
            sizes = splitter.sizes()
            current = sizes[index]
            diff = current - self.__size
            sizes[index] = self.__size
            sizes[index - 1] = sizes[index - 1] + diff
            self.__splitter.setSizes(sizes)

    def eventFilter(self, obj, event):
        # type: (QObject, QEvent) -> bool
        if event.type() == QEvent.Resize and obj is self.__widget and \
                self.__animation.state() == QPropertyAnimation.Stopped:
            # Update the expanded state when the user opens/closes the widget
            # by dragging the splitter handle.
            assert self.__splitter is not None
            assert isinstance(event, QResizeEvent)
            if self.__splitter.orientation() == Qt.Vertical:
                size = event.size().height()
            else:
                size = event.size().width()

            if self.__expanded and size == 0:
                self.__action.setChecked(False)
                self.__expanded = False
            elif not self.__expanded and size > 0:
                self.__action.setChecked(True)
                self.__expanded = True

        if event.type() == QEvent.Show and obj is self.__splitter and \
                self.__updateOnShow:
            # Update the splitter state after receiving valid geometry
            self.__updateOnShow = False
            self.__update()
        return super().eventFilter(obj, event)


class QuickHelpWidget(QuickHelp):
    def minimumSizeHint(self):
        # type: () -> QSize
        """Reimplemented to allow the Splitter to resize the widget
        with a continuous animation.
        """
        hint = super().minimumSizeHint()
        return QSize(hint.width(), 0)


class CanvasToolDock(QWidget):
    """Canvas dock widget with widget toolbox, quick help and
    canvas actions.
    """
    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QWidget], Any) -> None
        super().__init__(parent, **kwargs)

        self.__setupUi()

    def __setupUi(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.toolbox = WidgetToolBox()

        self.help = QuickHelpWidget(objectName="quick-help")

        self.__splitter = QSplitter()
        self.__splitter.setOrientation(Qt.Vertical)

        self.__splitter.addWidget(self.toolbox)
        self.__splitter.addWidget(self.help)

        self.toolbar = DynamicResizeToolBar()
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)

        self.toolbar.setSizePolicy(QSizePolicy.Ignored,
                                   QSizePolicy.Preferred)

        layout.addWidget(self.__splitter, 10)
        layout.addWidget(self.toolbar)

        self.setLayout(layout)
        self.__splitterResizer = SplitterResizer(self)
        self.__splitterResizer.setSplitterAndWidget(self.__splitter, self.help)

    def setQuickHelpVisible(self, state):
        # type: (bool) -> None
        """Set the quick help box visibility status."""
        self.__splitterResizer.setExpanded(state)

    def quickHelpVisible(self):
        # type: () -> bool
        return self.__splitterResizer.expanded()

    def setQuickHelpAnimationEnabled(self, enabled):
        # type: (bool) -> None
        """Enable/disable the quick help animation."""
        self.__splitterResizer.setAnimationEnabled(enabled)

    def toggleQuickHelpAction(self):
        # type: () -> QAction
        """Return a checkable QAction for help show/hide."""
        return self.__splitterResizer.toggleExpandedAction()

    def toogleQuickHelpAction(self):
        warnings.warn(
            "'toogleQuickHelpAction' is deprecated, use "
            "'toggleQuickHelpAction' instead.", DeprecationWarning,
            stacklevel=2
        )
        return self.toggleQuickHelpAction()


class QuickCategoryToolbar(ToolGrid):
    """A toolbar with category buttons."""
    def __init__(self, parent=None, buttonSize=QSize(), iconSize=QSize(),
                 **kwargs):
        # type: (Optional[QWidget], QSize, QSize, Any) -> None
        super().__init__(parent, 1, buttonSize, iconSize,
                         Qt.ToolButtonIconOnly, **kwargs)
        self.__model = None  # type: Optional[QAbstractItemModel]

    def setColumnCount(self, count):
        raise Exception("Cannot set the column count on a Toolbar")

    def setModel(self, model):
        # type: (Optional[QAbstractItemModel]) -> None
        """
        Set the registry model.
        """
        if self.__model is not None:
            self.__model.dataChanged.disconnect(self.__on_dataChanged)
            self.__model.rowsInserted.disconnect(self.__on_rowsInserted)
            self.__model.rowsRemoved.disconnect(self.__on_rowsRemoved)
            self.clear()

        self.__model = model
        if model is not None:
            model.dataChanged.connect(self.__on_dataChanged)
            model.rowsInserted.connect(self.__on_rowsInserted)
            model.rowsRemoved.connect(self.__on_rowsRemoved)
            self.__initFromModel(model)

    def __initFromModel(self, model):
        # type: (QAbstractItemModel) -> None
        """
        Initialize the toolbar from the model.
        """
        for index in iter_index(model, QModelIndex()):
            action = self.createActionForItem(index)
            self.addAction(action)

    def createActionForItem(self, index):
        # type: (QModelIndex) -> QAction
        """
        Create the QAction instance for item at `index` (`QModelIndex`).
        """
        action = QAction(
            item_icon(index), item_text(index), self,
            toolTip=item_tooltip(index)
        )
        action.setData(QPersistentModelIndex(index))
        return action

    def createButtonForAction(self, action):
        # type: (QAction) -> QToolButton
        """
        Create a button for the action.
        """
        button = super().createButtonForAction(action)

        item = action.data()  # QPersistentModelIndex
        assert isinstance(item, QPersistentModelIndex)

        brush = item.data(Qt.BackgroundRole)
        if not isinstance(brush, QBrush):
            brush = item.data(QtWidgetRegistry.BACKGROUND_ROLE)
            if not isinstance(brush, QBrush):
                brush = self.palette().brush(QPalette.Button)

        palette = button.palette()
        palette.setColor(QPalette.Button, brush.color())
        palette.setColor(QPalette.Window, brush.color())
        button.setPalette(palette)
        button.setProperty("quick-category-toolbutton", True)

        style_sheet = ("QToolButton {\n"
                       "    background: %s;\n"
                       "    border: none;\n"
                       "    border-bottom: 1px solid palette(mid);\n"
                       "}")
        button.setStyleSheet(style_sheet % create_css_gradient(brush.color()))

        return button

    def __on_dataChanged(self, topLeft, bottomRight):
        # type: (QModelIndex, QModelIndex) -> None
        assert self.__model is not None
        parent = topLeft.parent()
        if not parent.isValid():
            for row in range(topLeft.row(), bottomRight.row() + 1):
                item = self.__model.index(row, 0)
                action = self.actions()[row]
                action.setText(item_text(item))
                action.setIcon(item_icon(item))
                action.setToolTip(item_tooltip(item))

    def __on_rowsInserted(self, parent, start, end):
        # type: (QModelIndex, int, int) -> None
        assert self.__model is not None
        if not parent.isValid():
            for row in range(start, end + 1):
                item = self.__model.index(row, 0)
                self.insertAction(row, self.createActionForItem(item))

    def __on_rowsRemoved(self, parent, start, end):
        # type: (QModelIndex, int, int) -> None
        assert self.__model is not None
        if not parent.isValid():
            for row in range(end, start - 1, -1):
                action = self.actions()[row]
                self.removeAction(action)


# This implements the (single category) node selection popup when the
# tooldock is not expanded.
class CategoryPopupMenu(FramelessWindow):
    """
    A menu popup from which nodes can be dragged or clicked/activated.
    """
    triggered = Signal(QAction)
    hovered = Signal(QAction)

    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QWidget], Any) -> None
        super().__init__(parent, **kwargs)
        self.setWindowFlags(self.windowFlags() | Qt.Popup)

        layout = QVBoxLayout()
        layout.setContentsMargins(6, 6, 6, 6)

        self.__menu = MenuPage()
        self.__menu.setActionRole(QtWidgetRegistry.WIDGET_ACTION_ROLE)

        if sys.platform == "darwin":
            self.__menu.view().setAttribute(Qt.WA_MacShowFocusRect, False)

        self.__menu.triggered.connect(self.__onTriggered)
        self.__menu.hovered.connect(self.hovered)

        self.__dragListener = ItemViewDragStartEventListener(self)
        self.__dragListener.dragStarted.connect(self.__onDragStarted)

        self.__menu.view().viewport().installEventFilter(self.__dragListener)
        self.__menu.view().installEventFilter(self)

        layout.addWidget(self.__menu)

        self.setLayout(layout)

        self.__action = None  # type: Optional[QAction]
        self.__loop = None    # type: Optional[QEventLoop]

    def setCategoryItem(self, item):
        """
        Set the category root item (:class:`QStandardItem`).
        """
        warnings.warn(
            "setCategoryItem is deprecated. Use the more general 'setModel'"
            "and setRootIndex", DeprecationWarning, stacklevel=2
        )
        model = item.model()
        self.__menu.setModel(model)
        self.__menu.setRootIndex(item.index())

    def setModel(self, model):
        # type: (QAbstractItemModel) -> None
        """
        Set the model.

        Parameters
        ----------
        model : QAbstractItemModel
        """
        self.__menu.setModel(model)

    def setRootIndex(self, index):
        # type: (QModelIndex) -> None
        """
        Set the root index in `model`.

        Parameters
        ----------
        index : QModelIndex
        """
        self.__menu.setRootIndex(index)

    def setActionRole(self, role):
        # type: (Qt.ItemDataRole) -> None
        """
        Set the action role in model.

        This is an item role in `model` that returns a QAction for the item.

        Parameters
        ----------
        role : Qt.ItemDataRole
        """
        self.__menu.setActionRole(role)

    def popup(self, pos=None):
        # type: (Optional[QPoint]) -> None
        """
        Show the popup at `pos`.

        Parameters
        ----------
        pos : Optional[QPoint]
            The position in global screen coordinates
        """
        if pos is None:
            pos = self.pos()
        self.adjustSize()
        geom = widget_popup_geometry(pos, self)
        self.setGeometry(geom)
        self.show()
        self.__menu.view().setFocus()

    def exec_(self, pos=None):
        # type: (Optional[QPoint]) -> Optional[QAction]
        self.popup(pos)
        self.__loop = QEventLoop()

        self.__action = None
        self.__loop.exec_()
        self.__loop = None

        if self.__action is not None:
            action = self.__action
        else:
            action = None
        return action

    def hideEvent(self, event):
        # type: (QHideEvent) -> None
        if self.__loop is not None:
            self.__loop.exit(0)
        super().hideEvent(event)

    def __onTriggered(self, action):
        # type: (QAction) -> None
        self.__action = action
        self.triggered.emit(action)
        self.hide()

        if self.__loop:
            self.__loop.exit(0)

    def __onDragStarted(self, index):
        # type: (QModelIndex) -> None
        desc = index.data(QtWidgetRegistry.WIDGET_DESC_ROLE)
        icon = index.data(Qt.DecorationRole)

        drag_data = QMimeData()
        drag_data.setData(
            "application/vnv.orange-canvas.registry.qualified-name",
            desc.qualified_name.encode('utf-8')
        )
        drag = QDrag(self)
        drag.setPixmap(icon.pixmap(38))
        drag.setMimeData(drag_data)

        # TODO: Should animate (accept) hide.
        self.hide()

        # When a drag is started and the menu hidden the item's tool tip
        # can still show for a short time UNDER the cursor preventing a
        # drop.
        viewport = self.__menu.view().viewport()
        filter = ToolTipEventFilter()
        viewport.installEventFilter(filter)

        drag.exec_(Qt.CopyAction)

        viewport.removeEventFilter(filter)

    def eventFilter(self, obj, event):
        if isinstance(obj, QTreeView) and event.type() == QEvent.KeyPress:
            key = event.key()
            if key in [Qt.Key_Return, Qt.Key_Enter]:
                curr = obj.currentIndex()
                if curr.isValid():
                    obj.activated.emit(curr)
                    return True
        return super().eventFilter(obj, event)


class ItemViewDragStartEventListener(QObject):
    dragStarted = Signal(QModelIndex)

    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QObject], Any) -> None
        super().__init__(parent, **kwargs)
        self._pos = None    # type: Optional[QPoint]
        self._index = None  # type: Optional[QPersistentModelIndex]

    def eventFilter(self, viewport, event):
        # type: (QObject, QEvent) -> bool
        view = viewport.parent()

        if event.type() == QEvent.MouseButtonPress and \
                event.button() == Qt.LeftButton:

            index = view.indexAt(event.pos())

            if index is not None:
                self._pos = event.pos()
                self._index = QPersistentModelIndex(index)

        elif event.type() == QEvent.MouseMove and self._pos is not None and \
                ((self._pos - event.pos()).manhattanLength() >=
                 QApplication.startDragDistance()):
            assert self._index is not None
            if self._index.isValid():
                # Map to a QModelIndex in the model.
                index = QModelIndex(self._index)
                self._pos = None
                self._index = None

                self.dragStarted.emit(index)

        return super().eventFilter(view, event)


class ToolTipEventFilter(QObject):
    def eventFilter(self, receiver, event):
        # type: (QObject, QEvent) -> bool
        if event.type() == QEvent.ToolTip:
            return True

        return super().eventFilter(receiver, event)


def widget_popup_geometry(pos, widget):
    # type: (QPoint, QWidget) -> QRect
    widget.ensurePolished()

    if widget.testAttribute(Qt.WA_Resized):
        size = widget.size()
    else:
        size = widget.sizeHint()

    desktop = QApplication.desktop()
    screen_geom = desktop.availableGeometry(pos)

    # Adjust the size to fit inside the screen.
    if size.height() > screen_geom.height():
        size.setHeight(screen_geom.height())
    if size.width() > screen_geom.width():
        size.setWidth(screen_geom.width())

    geom = QRect(pos, size)

    if geom.top() < screen_geom.top():
        geom.setTop(screen_geom.top())

    if geom.left() < screen_geom.left():
        geom.setLeft(screen_geom.left())

    bottom_margin = screen_geom.bottom() - geom.bottom()
    right_margin = screen_geom.right() - geom.right()
    if bottom_margin < 0:
        # Falls over the bottom of the screen, move it up.
        geom.translate(0, bottom_margin)

    # TODO: right to left locale
    if right_margin < 0:
        # Falls over the right screen edge, move the menu to the
        # other side of pos.
        geom.translate(-size.width(), 0)

    return geom


def popup_position_from_source(popup, source, orientation=Qt.Vertical):
    # type: (QWidget, QWidget, Qt.Orientation) -> QPoint
    popup.ensurePolished()
    source.ensurePolished()

    if popup.testAttribute(Qt.WA_Resized):
        size = popup.size()
    else:
        size = popup.sizeHint()

    desktop = QApplication.desktop()
    screen_geom = desktop.availableGeometry(source)
    source_rect = QRect(source.mapToGlobal(QPoint(0, 0)), source.size())

    if orientation == Qt.Vertical:
        if source_rect.right() + size.width() < screen_geom.right():
            x = source_rect.right()
        else:
            x = source_rect.left() - size.width()

        # bottom overflow
        dy = source_rect.top() + size.height() - screen_geom.bottom()
        if dy < 0:
            y = source_rect.top()
        else:
            y = source_rect.top() - dy
    else:
        # right overflow
        dx = source_rect.left() + size.width() - screen_geom.right()
        if dx < 0:
            x = source_rect.left()
        else:
            x = source_rect.left() - dx

        if source_rect.bottom() + size.height() < screen_geom.bottom():
            y = source_rect.bottom()
        else:
            y = source_rect.top() - size.height()

    return QPoint(x, y)

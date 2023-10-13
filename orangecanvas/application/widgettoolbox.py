"""
Widget Tool Box
===============


A tool box with a tool grid for each category.

"""
from typing import Optional, Iterable, Any

from AnyQt.QtWidgets import (
    QAbstractButton, QSizePolicy, QAction, QApplication, QToolButton,
    QWidget, QLineEdit
)
from AnyQt.QtGui import (
    QDrag, QPalette, QBrush, QIcon, QColor, QGradient, QActionEvent,
    QMouseEvent
)
from AnyQt.QtCore import (
    Qt, QObject, QAbstractItemModel, QModelIndex, QSize, QEvent, QMimeData,
    QByteArray, QDataStream, QIODevice, QPoint, QPersistentModelIndex
)
from AnyQt.QtCore import pyqtSignal as Signal, pyqtProperty as Property

from ..gui.itemmodels import FilterProxyModel
from ..gui.toolbox import ToolBox
from ..gui.toolgrid import ToolGrid
from ..gui.quickhelp import StatusTipPromoter
from ..gui.utils import create_gradient_brush
from ..registry import WidgetDescription
from ..registry.qt import QtWidgetRegistry
from ..registry.utils import search_filter_query_helper
from ..resources import load_styled_svg_icon


def iter_index(model, index):
    # type: (QAbstractItemModel, QModelIndex) -> Iterable[QModelIndex]
    """
    Iterate over child indexes of a `QModelIndex` in a `model`.
    """
    for row in range(model.rowCount(index)):
        yield model.index(row, 0, index)


def item_text(index):  # type: (QModelIndex) -> str
    value = index.data(Qt.DisplayRole)
    if value is None:
        return ""
    else:
        return str(value)


def item_icon(index):  # type: (QModelIndex) -> QIcon
    value = index.data(Qt.DecorationRole)
    if isinstance(value, QIcon):
        return value
    else:
        return QIcon()


def item_tooltip(index):  # type: (QModelIndex) -> str
    value = index.data(Qt.ToolTipRole)
    if isinstance(value, str):
        return value
    return item_text(index)


def item_background(index):  # type: (QModelIndex) -> Optional[QBrush]
    value = index.data(Qt.BackgroundRole)
    if isinstance(value, QBrush):
        return value
    elif isinstance(value, (QColor, Qt.GlobalColor, QGradient)):
        return QBrush(value)
    else:
        return None


class WidgetToolGrid(ToolGrid):
    """
    A Tool Grid with widget buttons. Populates the widget buttons
    from an item model. Also adds support for drag operations.

    """
    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None
        super().__init__(*args, **kwargs)

        self.__model = None               # type: Optional[QAbstractItemModel]
        self.__rootIndex = QPersistentModelIndex()  # type: QPersistentModelIndex
        self.__actionRole = QtWidgetRegistry.WIDGET_ACTION_ROLE  # type: int

        self.__dragListener = DragStartEventListener(self)
        self.__dragListener.dragStartOperationRequested.connect(
            self.__startDrag
        )
        self.__statusTipPromoter = StatusTipPromoter(self)

    def setModel(self, model, rootIndex=QModelIndex()):
        # type: (QAbstractItemModel, QModelIndex) -> None
        """
        Set a model (`QStandardItemModel`) for the tool grid. The
        widget actions are children of the rootIndex.

        .. warning:: The model should not be deleted before the
                     `WidgetToolGrid` instance.

        """
        if self.__model is not None:
            self.__model.rowsInserted.disconnect(self.__on_rowsInserted)
            self.__model.rowsRemoved.disconnect(self.__on_rowsRemoved)
            self.__model.modelReset.disconnect(self.__on_modelReset)
            self.__model = None

        self.__model = model
        self.__rootIndex = QPersistentModelIndex(rootIndex)

        if self.__model is not None:
            self.__model.rowsInserted.connect(self.__on_rowsInserted)
            self.__model.rowsRemoved.connect(self.__on_rowsRemoved)
            self.__model.modelReset.connect(self.__on_modelReset)

        self.__initFromModel(model, rootIndex)

    def model(self):  # type: () -> Optional[QAbstractItemModel]
        """
        Return the model for the tool grid.
        """
        return self.__model

    def rootIndex(self):  # type: () -> QModelIndex
        """
        Return the root index of the model.
        """
        return QModelIndex(self.__rootIndex)

    def setActionRole(self, role):
        # type: (int) -> None
        """
        Set the action role. This is the model role containing a
        `QAction` instance.
        """
        if self.__actionRole != role:
            self.__actionRole = role
            if self.__model:
                self.__update()

    def actionRole(self):  # type: () -> int
        """
        Return the action role.
        """
        return self.__actionRole

    def actionEvent(self, event):  # type: (QActionEvent) -> None
        if event.type() == QEvent.ActionAdded:
            # Creates and inserts the button instance.
            super().actionEvent(event)

            button = self.buttonForAction(event.action())
            button.installEventFilter(self.__dragListener)
            button.installEventFilter(self.__statusTipPromoter)
            return
        elif event.type() == QEvent.ActionRemoved:
            button = self.buttonForAction(event.action())
            button.removeEventFilter(self.__dragListener)
            button.removeEventFilter(self.__statusTipPromoter)

            # Removes the button
            super().actionEvent(event)
            return
        else:
            super().actionEvent(event)

    def __initFromModel(self, model, rootIndex):
        # type: (QAbstractItemModel, QModelIndex) -> None
        """
        Initialize the grid from the model with rootIndex as the root.
        """
        for i, index in enumerate(iter_index(model, rootIndex)):
            self.__insertItem(i, index)

    def __insertItem(self, index, item):
        # type: (int, QModelIndex) -> None
        """
        Insert a widget action from `item` (`QModelIndex`) at `index`.
        """
        value = item.data(self.__actionRole)
        if isinstance(value, QAction):
            action = value
        else:
            action = QAction(item_text(item), self)
            action.setIcon(item_icon(item))
            action.setToolTip(item_tooltip(item))

        self.insertAction(index, action)

    def __update(self):  # type: () -> None
        self.clear()
        if self.__model is not None:
            self.__initFromModel(self.__model, QModelIndex(self.__rootIndex))

    def __on_rowsInserted(self, parent, start, end):
        # type: (QModelIndex, int, int) -> None
        """
        Insert items from range start:end into the grid.
        """
        if parent == QModelIndex(self.__rootIndex):
            for i in range(start, end + 1):
                item = self.__model.index(i, 0, parent)
                self.__insertItem(i, item)

    def __on_rowsRemoved(self, parent, start, end):
        # type: (QModelIndex, int, int) -> None
        """
        Remove items from range start:end from the grid.
        """
        if parent == QModelIndex(self.__rootIndex):
            actions = self.actions()
            actions = actions[start: end + 1]
            self.__removeActions(actions)

    def __on_modelReset(self):
        self.__removeActions(self.actions())

    def __removeActions(self, actions: Iterable[QAction]):
        for action in actions:
            self.removeAction(action)

    def __startDrag(self, button):
        # type: (QToolButton) -> None
        """
        Start a drag from button
        """
        action = button.defaultAction()
        desc = action.data()  # Widget Description
        icon = action.icon()
        drag_data = QMimeData()
        drag_data.setData(
            "application/vnd.orange-canvas.registry.qualified-name",
            desc.qualified_name.encode("utf-8")
        )
        drag = QDrag(button)
        drag.setPixmap(icon.pixmap(self.iconSize()))
        drag.setMimeData(drag_data)
        drag.exec(Qt.CopyAction)


class DragStartEventListener(QObject):
    """
    An event filter object that can be used to detect drag start
    operation on buttons which otherwise do not support it.

    """
    dragStartOperationRequested = Signal(QAbstractButton)
    """A drag operation started on a button."""

    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QObject], Any) -> None
        super().__init__(parent, **kwargs)
        self.button = None         # type: Optional[Qt.MouseButton]
        self.buttonDownObj = None  # type: Optional[QAbstractButton]
        self.buttonDownPos = None  # type: Optional[QPoint]

    def eventFilter(self, obj, event):
        # type: (QObject, QEvent) -> bool
        if event.type() == QEvent.MouseButtonPress:
            assert isinstance(event, QMouseEvent)
            self.buttonDownPos = event.pos()
            self.buttonDownObj = obj
            self.button = event.button()

        elif event.type() == QEvent.MouseMove and obj is self.buttonDownObj:
            assert self.buttonDownObj is not None
            if (self.buttonDownPos - event.pos()).manhattanLength() > \
                    QApplication.startDragDistance() and \
                    not self.buttonDownObj.hitButton(event.pos()):
                # Process the widget's mouse event, before starting the
                # drag operation, so the widget can update its state.
                obj.mouseMoveEvent(event)
                self.dragStartOperationRequested.emit(obj)

                obj.setDown(False)

                self.button = None
                self.buttonDownPos = None
                self.buttonDownObj = None
                return True  # Already handled

        return super().eventFilter(obj, event)


class WidgetToolBox(ToolBox):
    """
    `WidgetToolBox` widget shows a tool box containing button grids of
    actions for a :class:`QtWidgetRegistry` item model.
    """

    triggered = Signal(QAction)
    hovered = Signal(QAction)

    def __init__(self, parent=None):
        # type: (Optional[QWidget]) -> None
        super().__init__(parent)
        self.__model = None  # type: Optional[QAbstractItemModel]
        self.__proxyModel = FilterProxyModel()
        self.__proxyModel.dataChanged.connect(self.__on_dataChanged)
        self.__proxyModel.rowsInserted.connect(self.__on_rowsInserted)
        self.__proxyModel.rowsRemoved.connect(self.__on_rowsRemoved)
        self.__proxyModel.modelReset.connect(self.__on_modelReset)

        self.__iconSize = QSize(25, 25)
        self.__buttonSize = QSize(50, 50)
        self.__filterText = ""
        self.__filteredSavedState = {}
        self.setSizePolicy(QSizePolicy.Fixed,
                           QSizePolicy.Expanding)
        action = QAction(
            load_styled_svg_icon("Search.svg"), self.tr("Search"), self
        )
        self.__filterEdit = QLineEdit(
            objectName="filter-edit-line",
            placeholderText=self.tr("Filter..."),
            toolTip=self.tr("Filter/search the list of available widgets."),
            clearButtonEnabled=True,
        )
        self.__filterEdit.setAttribute(Qt.WA_MacShowFocusRect, False)
        self.__filterEdit.addAction(action, QLineEdit.LeadingPosition)
        self.__filterEdit.textChanged.connect(self.__on_filterTextChanged)
        layout = self.layout()
        layout.setSpacing(1)
        layout.insertWidget(0, self.__filterEdit)

        open_all = QAction(self.tr("Open all"), self)
        open_all.triggered.connect(self.openAllTabs)
        close_all = QAction(self.tr("Close all"), self)
        close_all.triggered.connect(self.closeAllTabs)
        self.addActions([open_all, close_all])
        self.setContextMenuPolicy(Qt.ActionsContextMenu)

    def filterLineEdit(self) -> QLineEdit:
        return self.__filterEdit

    def setIconSize(self, size):  # type: (QSize) -> None
        """
        Set the widget icon size (icons in the button grid).
        """
        if self.__iconSize != size:
            self.__iconSize = QSize(size)
            for widget in map(self.widget, range(self.count())):
                widget.setIconSize(size)

    def iconSize(self):  # type: () -> QSize
        """
        Return the widget buttons icon size.
        """
        return QSize(self.__iconSize)

    iconSize_ = Property(QSize, fget=iconSize, fset=setIconSize,
                         designable=True)

    def setButtonSize(self, size):  # type: (QSize) -> None
        """
        Set fixed widget button size.
        """
        if self.__buttonSize != size:
            self.__buttonSize = QSize(size)
            for widget in map(self.widget, range(self.count())):
                widget.setButtonSize(size)

    def buttonSize(self):  # type: () -> QSize
        """Return the widget button size
        """
        return QSize(self.__buttonSize)

    buttonSize_ = Property(QSize, fget=buttonSize, fset=setButtonSize,
                           designable=True)

    def saveState(self):  # type: () -> QByteArray
        """
        Return the toolbox state (as a `QByteArray`).

        .. note:: Individual tabs are stored by their action's text.

        """
        version = 2

        actions = map(self.tabAction, range(self.count()))
        expanded = [action for action in actions if action.isChecked()]
        expanded = [action.text() for action in expanded]

        byte_array = QByteArray()
        stream = QDataStream(byte_array, QIODevice.WriteOnly)
        stream.writeInt(version)
        stream.writeQStringList(expanded)

        return byte_array

    def restoreState(self, state):  # type: (QByteArray) -> bool
        """
        Restore the toolbox from a :class:`QByteArray` `state`.

        .. note:: The toolbox should already be populated for the state
                  changes to take effect.

        """
        stream = QDataStream(state, QIODevice.ReadOnly)
        version = stream.readInt()
        if version == 2:
            expanded = stream.readQStringList()
            for action in map(self.tabAction, range(self.count())):
                if (action.text() in expanded) != action.isChecked():
                    action.trigger()
            return True
        return False

    def setModel(self, model):
        # type: (QAbstractItemModel) -> None
        """
        Set the widget registry model (:class:`QAbstractItemModel`) for
        this toolbox.
        """
        self.__model = model
        rows = self.__proxyModel.rowCount()
        if rows:
            self.__on_rowsRemoved(QModelIndex(), 0, rows - 1)
        self.__proxyModel.setSourceModel(model)
        self.__initFromModel(self.__proxyModel)

    def __initFromModel(self, model):
        # type: (QAbstractItemModel) -> None
        for row in range(model.rowCount()):
            self.__insertItem(model.index(row, 0), self.count())

    def __insertItem(self, item, index):
        # type: (QModelIndex, int) -> None
        """
        Insert category item  (`QModelIndex`) at index.
        """
        grid = WidgetToolGrid()
        grid.setModel(item.model(), item)
        grid.actionTriggered.connect(self.triggered)
        grid.actionHovered.connect(self.hovered)

        grid.setIconSize(self.__iconSize)
        grid.setButtonSize(self.__buttonSize)
        grid.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        text = item_text(item)
        icon = item_icon(item)
        tooltip = item_tooltip(item)

        # Set the 'tab-title' property to text.
        grid.setProperty("tab-title", text)
        grid.setObjectName("widgets-toolbox-grid")

        self.insertItem(index, grid, text, icon, tooltip)
        button = self.tabButton(index)

        # Set the 'highlight' color if applicable
        highlight_foreground = None
        highlight = item_background(item)
        if highlight is None \
                and item.data(QtWidgetRegistry.BACKGROUND_ROLE) is not None:
            highlight = item.data(QtWidgetRegistry.BACKGROUND_ROLE)

        if isinstance(highlight, QBrush) and highlight.style() != Qt.NoBrush:
            if not highlight.gradient():
                value = highlight.color().value()
                highlight = create_gradient_brush(highlight.color())
                highlight_foreground = Qt.black if value > 128 else Qt.white

        palette = button.palette()

        if highlight is not None:
            palette.setBrush(QPalette.Highlight, highlight)
        if highlight_foreground is not None:
            palette.setBrush(QPalette.HighlightedText, highlight_foreground)
        button.setPalette(palette)

    def __on_dataChanged(self, topLeft, bottomRight):
        # type: (QModelIndex, QModelIndex) -> None
        parent = topLeft.parent()
        if not parent.isValid():
            for row in range(topLeft.row(), bottomRight.row() + 1):
                item = topLeft.sibling(row, topLeft.column())
                button = self.tabButton(row)
                button.setIcon(item_icon(item))
                button.setText(item_text(item))
                button.setToolTip(item_tooltip(item))

    def __on_rowsInserted(self, parent, start, end):
        # type: (QModelIndex, int, int) -> None
        """
        Items have been inserted in the model.
        """
        # Only the top level items (categories) are handled here.
        assert self.__model is not None
        if not parent.isValid():
            for i in range(start, end + 1):
                item = self.__proxyModel.index(i, 0)
                self.__insertItem(item, i)

    def __on_rowsRemoved(self, parent, start, end):
        # type: (QModelIndex, int, int) -> None
        """
        Rows have been removed from the model.
        """
        # Only the top level items (categories) are handled here.
        if not parent.isValid():
            for i in reversed(range(start, end + 1)):
                self.removeItem(i)

    def __on_modelReset(self):
        for i in reversed(range(self.count())):
            self.removeItem(i)

    def __on_filterTextChanged(self, text: str) -> None:
        def acceptable(desc: Optional[WidgetDescription]) -> bool:
            if desc is not None:
                return search_filter_query_helper(desc, text.strip().lower())
            else:
                return True  # accept other (category, ...)

        self.__proxyModel.setFilters([
            FilterProxyModel.Filter(0, QtWidgetRegistry.WIDGET_DESC_ROLE,
                                    acceptable),
        ])
        if not self.__filterText and text:
            self.__filterText = text
            self.__openAllTabsForFilter()
        elif self.__filterText and not text:
            self.__filterText = ""
            self.__restoreAllTabsForFilter()

    def __openAllTabsForFilter(self):
        """Open all tabs for displaying filter/search results."""
        self.__filteredSavedState = {"!__exclusive": self.exclusive()}
        self.setExclusive(False)
        for i in range(self.count()):
            b = self.tabButton(i)
            self.__filteredSavedState[b.text()] = b.isChecked()
            b.defaultAction().setChecked(True)

    def __restoreAllTabsForFilter(self):
        """Restore open tabs after filter/search."""
        self.setExclusive(self.__filteredSavedState.get("!__exclusive", False))
        for i in range(self.count()):
            b = self.tabButton(i)
            b.defaultAction().setChecked(self.__filteredSavedState.get(b.text(), b.isChecked()))

    def openAllTabs(self):
        """Open all tabs."""
        self.setExclusive(False)
        for i in range(self.count()):
            self.tabButton(i).defaultAction().setChecked(True)

    def closeAllTabs(self):
        """Close all tabs."""
        self.setExclusive(False)
        for i in range(self.count()):
            self.tabButton(i).defaultAction().setChecked(False)
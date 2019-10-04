"""
==========
Quick Menu
==========

A :class:`QuickMenu` widget provides lists of actions organized in tabs
with a quick search functionality.

"""
import typing
import statistics
import sys
import logging

from collections import namedtuple

from typing import Optional, Any, List, Callable

from AnyQt.QtWidgets import (
    QWidget, QFrame, QToolButton, QAbstractButton, QAction, QTreeView,
    QButtonGroup, QStackedWidget, QHBoxLayout, QVBoxLayout, QSizePolicy,
    QStyleOptionToolButton, QStylePainter, QStyle, QApplication,
    QStyleOptionViewItem, QSizeGrip, QAbstractItemView, QStyledItemDelegate
)
from AnyQt.QtGui import (
    QIcon, QStandardItemModel, QPolygon, QRegion, QBrush, QPalette,
    QPaintEvent, QColor, QMouseEvent, QPixmap)
from AnyQt.QtCore import (
    Qt, QObject, QPoint, QSize, QRect, QEventLoop, QEvent, QModelIndex,
    QTimer, QRegExp, QSortFilterProxyModel, QItemSelectionModel,
    QAbstractItemModel,
    QSettings)
from AnyQt.QtCore import pyqtSignal as Signal, pyqtProperty as Property
from PyQt5.QtCore import QRectF, QPointF
from PyQt5.QtGui import QPainter

from .usagestatistics import UsageStatistics
from ..gui.framelesswindow import FramelessWindow
from ..gui.lineedit import LineEdit
from ..gui.tooltree import ToolTree, FlattenedTreeItemModel
from ..gui.utils import StyledWidget_paintEvent, innerGlowBackgroundPixmap, innerShadowPixmap
from ..registry.qt import QtWidgetRegistry

from ..resources import icon_loader

log = logging.getLogger(__name__)


class _MenuItemDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        widget = option.widget
        if widget is not None:
            style = widget.style()
        else:
            style = QApplication.style()

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        rect = option.rect
        tl = rect.topLeft()
        br = rect.bottomRight()
        """ Draw icon background """

        # get category color
        brush = as_qbrush(index.data(QtWidgetRegistry.BACKGROUND_ROLE))
        if brush is not None:
            color = brush.color()
        else:
            color = QColor("FFA840")  # orange!

        # (get) cache(d) pixmap
        bg = innerGlowBackgroundPixmap(color,
                                       QSize(rect.height(), rect.height()))

        # draw background
        bgRect = QRect(tl.x(), tl.y(), rect.height(), rect.height())
        painter.drawPixmap(bgRect, bg, bg.rect())

        """ Draw icon """

        # get item decoration (icon)
        dec = opt.icon
        decSize = option.decorationSize  # use as approximate/minimum size
        x = rect.left() + rect.height() / 2 - decSize.width() / 2
        y = rect.top() + rect.height() / 2 - decSize.height() / 2

        # decoration rect, where the icon is drawn
        decTl = QPointF(x, y)
        decBr = QPointF(x + decSize.width(), y + decSize.height())
        decRect = QRectF(decTl, decBr)

        # draw icon pixmap
        dec.paint(painter, decRect.toAlignedRect())

        # draw display
        rect = QRect(opt.rect)
        rect.setLeft(bgRect.left() + bgRect.width())  # move to icon area end
        opt.rect = rect
        # no focus display (selected state is the sole indicator)
        opt.state &= ~ QStyle.State_KeyboardFocusChange
        opt.state &= ~ QStyle.State_HasFocus
        # no icon
        opt.decorationSize = QSize()
        opt.icon = QIcon()
        opt.features &= ~QStyleOptionViewItem.HasDecoration
        if not opt.state & QStyle.State_Selected:
            style.drawControl(QStyle.CE_ItemViewItem, opt, painter, widget)
            return
        # draw as 2 side by side items, first with the actual text,
        # the second with 'enter key' shortcut indicator
        optleft = QStyleOptionViewItem(opt)
        optright = QStyleOptionViewItem(opt)

        optright.decorationSize = QSize()
        optright.icon = QIcon()
        optright.features &= ~QStyleOptionViewItem.HasDecoration
        optright.viewItemPosition = QStyleOptionViewItem.End
        optright.textElideMode = Qt.ElideNone
        optright.text = "\u21B5"
        sh = style.sizeFromContents(
            QStyle.CT_ItemViewItem, optright, QSize(), widget)
        rectright = QRect(opt.rect)
        rectright.setLeft(rectright.left() + rectright.width() - sh.width())
        optright.rect = rectright

        rectleft = QRect(opt.rect)
        rectleft.setRight(rectright.left())
        optleft.rect = rectleft
        optleft.viewItemPosition = QStyleOptionViewItem.Beginning
        optleft.textElideMode = Qt.ElideRight

        style.drawControl(QStyle.CE_ItemViewItem, optright, painter, widget)
        style.drawControl(QStyle.CE_ItemViewItem, optleft, painter, widget)

    def sizeHint(self, option, index):
        # type: (QStyleOptionViewItem, QModelIndex) -> QSize
        if option.widget is not None:
            style = option.widget.style()
        else:
            style = QApplication.style()
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # content size without the icon
        optnoicon = QStyleOptionViewItem(opt)
        optnoicon.decorationSize = QSize()
        optnoicon.icon = QIcon()
        optnoicon.features &= ~QStyleOptionViewItem.HasDecoration
        sh = style.sizeFromContents(
            QStyle.CT_ItemViewItem, optnoicon, QSize(), option.widget
        )
        # size with the icon
        shicon = style.sizeFromContents(
            QStyle.CT_ItemViewItem, opt, QSize(), option.widget
        )
        sh.setHeight(max(sh.height(), shicon.height(), 25))
        # add the custom drawn icon area rect to sh (height x height)
        sh.setWidth(sh.width() + sh.height())
        return sh


class MenuPage(ToolTree):
    """
    A menu page in a :class:`QuickMenu` widget, showing a list of actions.
    Shown actions can be disabled by setting a filtering function using the
    :func:`setFilterFunc`.

    """
    def __init__(self, parent=None, title="", icon=QIcon(), **kwargs):
        # type: (Optional[QWidget], str, QIcon, Any) -> None
        super().__init__(parent, **kwargs)

        self.__title = title
        self.__icon = QIcon(icon)
        self.__sizeHint = None  # type: Optional[QSize]

        self.view().setItemDelegate(_MenuItemDelegate(self.view()))
        self.view().viewport().setMouseTracking(True)
        self.view().viewport().installEventFilter(self)

        # Make sure the initial model is wrapped in a ItemDisableFilter.
        self.setModel(self.model())

    def setTitle(self, title):
        # type: (str) -> None
        """
        Set the title of the page.
        """
        if self.__title != title:
            self.__title = title
            self.update()

    def title(self):
        # type: () -> str
        """
        Return the title of this page.
        """
        return self.__title

    title_ = Property(str, fget=title, fset=setTitle, doc="Title of the page.")

    def setIcon(self, icon):  # type: (QIcon) -> None
        """
        Set icon for this menu page.
        """
        if self.__icon != icon:
            self.__icon = icon
            self.update()

    def icon(self):  # type: () -> QIcon
        """
        Return the icon of this menu page.
        """
        return QIcon(self.__icon)

    icon_ = Property(QIcon, fget=icon, fset=setIcon,
                     doc="Page icon")

    def setFilterFunc(self, func):
        # type: (Optional[Callable[[QModelIndex], bool]]) -> None
        """
        Set the filtering function. `func` should a function taking a single
        :class:`QModelIndex` argument and returning True if the item at index
        should be disabled and False otherwise. To disable filtering `func` can
        be set to ``None``.

        """
        proxyModel = self.view().model()
        proxyModel.setFilterFunc(func)

    def setModel(self, model):
        # type: (QAbstractItemModel) -> None
        """
        Reimplemented from :func:`ToolTree.setModel`.
        """
        proxyModel = ItemDisableFilter(self)
        proxyModel.setSourceModel(model)
        super().setModel(proxyModel)

        self.__invalidateSizeHint()

    def setRootIndex(self, index):
        # type: (QModelIndex) -> None
        """
        Reimplemented from :func:`ToolTree.setRootIndex`
        """
        proxyModel = self.view().model()
        mappedIndex = proxyModel.mapFromSource(index)
        super().setRootIndex(mappedIndex)

        self.__invalidateSizeHint()

    def rootIndex(self):
        # type: () -> QModelIndex
        """
        Reimplemented from :func:`ToolTree.rootIndex`
        """
        proxyModel = self.view().model()
        return proxyModel.mapToSource(super().rootIndex())

    def sizeHint(self):
        # type: () -> QSize
        """
        Reimplemented from :func:`QWidget.sizeHint`.
        """
        if self.__sizeHint is None:
            view = self.view()
            model = view.model()

            # This will not work for nested items (tree).
            count = model.rowCount(view.rootIndex())

            # 'sizeHintForColumn' is the reason for size hint caching
            # since it must traverse all items in the column.
            width = view.sizeHintForColumn(0)

            if count:
                height = view.sizeHintForRow(0)
                height = height * count
            else:
                height = 0

            # add scrollbar width
            scroll = self.view().verticalScrollBar()
            isTransient = scroll.style().styleHint(QStyle.SH_ScrollBar_Transient, widget=scroll)
            if not isTransient:
                width += scroll.style().pixelMetric(QStyle.PM_ScrollBarExtent, widget=scroll)

            self.__sizeHint = QSize(width, height)

        return self.__sizeHint

    def __invalidateSizeHint(self):  # type: () -> None
        self.__sizeHint = None
        self.updateGeometry()

    def eventFilter(self, recv: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.MouseMove and recv is self.view().viewport():
            mouseevent = typing.cast(QMouseEvent, event)
            view = self.view()
            index = view.indexAt(mouseevent.pos())
            if index.isValid() and index.flags() & Qt.ItemIsEnabled:
                view.setCurrentIndex(index)
        return super().eventFilter(recv, event)


if typing.TYPE_CHECKING:
    FilterFunc = Callable[[QModelIndex], bool]


class ItemDisableFilter(QSortFilterProxyModel):
    """
    An filter proxy model used to disable selected items based on
    a filtering function.

    """
    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QObject], Any) -> None
        super().__init__(parent, **kwargs)
        self.__filterFunc = None  # type: Optional[FilterFunc]

    def setFilterFunc(self, func):
        # type: (Optional[FilterFunc]) -> None
        """
        Set the filtering function.
        """
        if not (callable(func) or func is None):
            raise TypeError("A callable object or None expected.")

        if self.__filterFunc != func:
            self.__filterFunc = func
            # Mark the whole model as changed.
            self.dataChanged.emit(self.index(0, 0),
                                  self.index(self.rowCount(), 0))

    def flags(self, index):
        # type: (QModelIndex) -> Qt.ItemFlags
        """
        Reimplemented from :class:`QSortFilterProxyModel.flags`
        """
        source = self.mapToSource(index)
        flags = source.flags()

        if self.__filterFunc is not None:
            enabled = flags & Qt.ItemIsEnabled
            if enabled and not self.__filterFunc(source):
                flags = Qt.ItemFlags(flags ^ Qt.ItemIsEnabled)

        return flags


class SuggestMenuPage(MenuPage):
    """
    A MenuMage for the QuickMenu widget supporting item filtering
    (searching).

    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def setModel(self, model):
        # type: (QAbstractItemModel) -> None
        """
        Reimplemented from :ref:`MenuPage.setModel`.
        """
        flat = FlattenedTreeItemModel(self)
        flat.setSourceModel(model)
        flat.setFlatteningMode(flat.InternalNodesDisabled)
        flat.setFlatteningMode(flat.LeavesOnly)
        proxy = SortFilterProxyModel(self)
        proxy.setFilterCaseSensitivity(Qt.CaseSensitive)
        proxy.setSourceModel(flat)
        # bypass MenuPage.setModel and its own proxy
        # TODO: store my self.__proxy
        ToolTree.setModel(self, proxy)
        self.ensureCurrent()

    def __proxy(self):
        # type: () -> SortFilterProxyModel
        model = self.view().model()
        assert isinstance(model, SortFilterProxyModel)
        assert model.parent() is self
        return model

    def setFilterFixedString(self, pattern):
        # type: (str) -> None
        """
        Set the fixed string filtering pattern. Only items which contain the
        `pattern` string will be shown.
        """
        proxy = self.__proxy()
        proxy.setFilterFixedString(pattern)
        self.ensureCurrent()

    def setFilterRegExp(self, pattern):
        # type: (QRegExp) -> None
        """
        Set the regular expression filtering pattern. Only items matching
        the `pattern` expression will be shown.
        """
        filter_proxy = self.__proxy()
        filter_proxy.setFilterRegExp(pattern)

        # re-sorts to make sure items that match by title are on top
        filter_proxy.invalidate()
        filter_proxy.sort(0)

        self.ensureCurrent()

    def setFilterWildCard(self, pattern):
        # type: (str) -> None
        """
        Set a wildcard filtering pattern.
        """
        filter_proxy = self.__proxy()
        filter_proxy.setFilterWildCard(pattern)
        self.ensureCurrent()

    def setFilterFunc(self, func):
        # type: (Optional[FilterFunc]) -> None
        """
        Set a filtering function.
        """
        filter_proxy = self.__proxy()
        filter_proxy.setFilterFunc(func)

    def setSortingFunc(self, func):
        # type: (Callable[[Any, Any], bool]) -> None
        """
        Set a sorting function.
        """
        filter_proxy = self.__proxy()
        filter_proxy.setSortingFunc(func)


class SortFilterProxyModel(QSortFilterProxyModel):
    """
    An filter proxy model used to sort and filter items based on
    a sort and filtering function.

    """
    def __init__(self, parent=None):
        # type: (Optional[QObject]) -> None
        super().__init__(parent)

        self.__filterFunc = None  # type: Optional[FilterFunc]
        self.__sortingFunc = None

    def setFilterFunc(self, func):
        # type: (Optional[FilterFunc]) -> None
        """
        Set the filtering function.
        """
        if not (func is None or callable(func)):
            raise ValueError("A callable object or None expected.")

        if self.__filterFunc is not func:
            self.__filterFunc = func
            self.invalidateFilter()

    def filterFunc(self):
        # type: () -> Optional[FilterFunc]
        return self.__filterFunc

    def filterAcceptsRow(self, row, parent=QModelIndex()):
        # type: (int, QModelIndex) -> bool
        flat_model = self.sourceModel()
        index = flat_model.index(row, self.filterKeyColumn(), parent)
        description = flat_model.data(index, role=QtWidgetRegistry.WIDGET_DESC_ROLE)
        if description is None:
            return False

        name = description.name
        keywords = description.keywords or []

        # match name and keywords
        accepted = False
        for keyword in [name] + keywords:
            if self.filterRegExp().indexIn(keyword) > -1:
                accepted = True
                break

        # if matches query, apply filter function (compatibility with paired widget)
        if accepted and self.__filterFunc is not None:
            model = self.sourceModel()
            index = model.index(row, self.filterKeyColumn(), parent)
            return self.__filterFunc(index)
        else:
            return accepted

    def setSortingFunc(self, func):
        # type: (Callable[[Any, Any], bool]) -> None
        self.__sortingFunc = func
        self.invalidate()
        self.sort(0)

    def sortingFunc(self):
        return self.__sortingFunc

    def lessThan(self, left, right):
        # type: (QModelIndex, QModelIndex) -> bool
        if self.__sortingFunc is None:
            return super().lessThan(left, right)
        model = self.sourceModel()
        left_data = model.data(left)
        right_data = model.data(right)

        flat_model = self.sourceModel()
        left_description = flat_model.data(left, role=QtWidgetRegistry.WIDGET_DESC_ROLE)
        right_description = flat_model.data(right, role=QtWidgetRegistry.WIDGET_DESC_ROLE)

        left_matches_title = self.filterRegExp().indexIn(left_description.name) > -1
        right_matches_title = self.filterRegExp().indexIn(right_description.name) > -1

        if left_matches_title != right_matches_title:
            return left_matches_title
        return self.__sortingFunc(left_data, right_data)


class SearchWidget(LineEdit):
    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QWidget], Any) -> None
        super().__init__(parent, **kwargs)
        self.setAttribute(Qt.WA_MacShowFocusRect, 0)

        self.__setupUi()

    def __setupUi(self):
        icon = icon_loader().get("icons/Search.svg")
        action = QAction(icon, "Search", self)
        self.setAction(action, LineEdit.LeftPosition)

        button = self.button(SearchWidget.LeftPosition)
        button.setCheckable(True)

    def setChecked(self, checked):
        button = self.button(SearchWidget.LeftPosition)
        if button.isChecked() != checked:
            button.setChecked(checked)
            button.update()
            button.style().polish(button)  # QTBUG-2982


class MenuStackWidget(QStackedWidget):
    """
    Stack widget for the menu pages.
    """

    def sizeHint(self):
        # type: () -> QSize
        """
        Size hint is the maximum width and median height of the widgets
        contained in the stack.
        """
        default_size = QSize(200, 400)
        widget_hints = [default_size]
        for i in range(self.count()):
            hint = self.widget(i).sizeHint()
            widget_hints.append(hint)

        width = max([s.width() for s in widget_hints])

        if widget_hints:
            # Take the median for the height
            height = statistics.median([s.height() for s in widget_hints])
        else:
            height = default_size.height()
        return QSize(width, int(height))

    def __sizeHintForTreeView(self, view):
        # type: (QTreeView) -> QSize
        hint = view.sizeHint()
        model = view.model()

        count = model.rowCount()
        width = view.sizeHintForColumn(0)

        if count:
            height = view.sizeHintForRow(0)
            height = height * count
        else:
            height = hint.height()

        return QSize(max(width, hint.width()), max(height, hint.height()))


class TabButton(QToolButton):
    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QWidget], Any) -> None
        super().__init__(parent, **kwargs)
        self.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.setCheckable(True)

        self.__flat = True
        self.__showMenuIndicator = False
        self.__shadowLength = 5
        self.__shadowColor = QColor("#000000")

        self.shadowPosition = 0

    def setShadowLength(self, shadowSize):
        if self.__shadowLength != shadowSize:
            self.__shadowLength = shadowSize
            self.update()

    def shadowLength(self):
        return self.__shadowLength

    shadowLength_ = Property(int, fget=shadowLength, fset=setShadowLength, designable=True)

    def setShadowColor(self, shadowColor):
        if self.__shadowColor != shadowColor:
            self.__shadowColor = shadowColor
            self.update()

    def shadowColor(self):
        return self.__shadowColor

    shadowColor_ = Property(QColor, fget=shadowColor, fset=setShadowColor, designable=True)

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

    def setShownMenuIndicator(self, show):
        # type: (bool) -> None
        if self.__showMenuIndicator != show:
            self.__showMenuIndicator = show
            self.update()

    def showMenuIndicator(self):
        # type: () -> bool
        return self.__showMenuIndicator

    showMenuIndicator_ = Property(bool, fget=showMenuIndicator,
                                  fset=setShownMenuIndicator,
                                  designable=True)

    def paintEvent(self, event):
        # type: (QPaintEvent) -> None
        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)
        if self.__showMenuIndicator and self.isChecked():
            opt.features |= QStyleOptionToolButton.HasMenu
        if self.__flat:
            # Use default widget background/border styling.
            StyledWidget_paintEvent(self, event)

            p = QStylePainter(self)
            p.drawControl(QStyle.CE_ToolButtonLabel, opt)
        else:
            p = QStylePainter(self)
            p.drawComplexControl(QStyle.CC_ToolButton, opt)

        # if checked, no shadow
        if self.isChecked():
            return

        targetShadowRect = QRect(self.rect().x(), self.rect().y(), self.width(), self.height())

        shadow = innerShadowPixmap(self.__shadowColor,
                                   targetShadowRect.size(),
                                   self.shadowPosition,
                                   self.__shadowLength)

        p.drawPixmap(targetShadowRect, shadow, shadow.rect())

    def sizeHint(self):
        # type: () -> QSize
        opt = QStyleOptionToolButton()
        self.initStyleOption(opt)
        if self.__showMenuIndicator and self.isChecked():
            opt.features |= QStyleOptionToolButton.HasMenu
        style = self.style()
        hint = style.sizeFromContents(QStyle.CT_ToolButton, opt,
                                      opt.iconSize, self)
        # should there be no margin around the icon, add extra margin;
        # in the absence of a better alternative use the text <-> border margin of a push button
        margin = style.pixelMetric(QStyle.PM_ButtonMargin, None, self)
        width = max(hint.width(), opt.iconSize.width() + margin)
        height = max(hint.height(), opt.iconSize.height() + margin)
        hint.setWidth(width)
        hint.setHeight(height)
        return hint


_Tab = namedtuple(
    "_Tab",
    ["text",
     "icon",
     "toolTip",
     "button",
     "data",
     "palette"]
)


class TabBarWidget(QWidget):
    """
    A vertical tab bar widget using tool buttons as for tabs.
    """

    currentChanged = Signal(int)

    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QWidget], Any) -> None
        super().__init__(parent, **kwargs)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self.setSizePolicy(QSizePolicy.Fixed,
                           QSizePolicy.Expanding)
        self.__tabs = []  # type: List[_Tab]

        self.__currentIndex = -1
        self.__changeOnHover = False

        self.__iconSize = QSize(26, 26)

        self.__group = QButtonGroup(self, exclusive=True)
        self.__group.buttonPressed[QAbstractButton].connect(
            self.__onButtonPressed
        )
        self.setMouseTracking(True)

        self.__sloppyButton = None  # type: Optional[QAbstractButton]
        self.__sloppyRegion = QRegion()
        self.__sloppyTimer = QTimer(self, singleShot=True)
        self.__sloppyTimer.timeout.connect(self.__onSloppyTimeout)

        self.currentChanged.connect(self.__updateShadows)

    def setChangeOnHover(self, changeOnHover):
        #  type: (bool) -> None
        """
        If set to ``True`` the tab widget will change the current index when
        the mouse hovers over a tab button.
        """
        if self.__changeOnHover != changeOnHover:
            self.__changeOnHover = changeOnHover

    def changeOnHover(self):
        # type: () -> bool
        """
        Does the current tab index follow the mouse cursor.
        """
        return self.__changeOnHover

    def count(self):
        # type: () -> int
        """
        Return the number of tabs in the widget.
        """
        return len(self.__tabs)

    def addTab(self, text, icon=QIcon(), toolTip=""):
        # type: (str, QIcon, str) -> int
        """
        Add a new tab and return it's index.
        """
        return self.insertTab(self.count(), text, icon, toolTip)

    def insertTab(self, index, text, icon=QIcon(), toolTip=""):
        # type: (int, str, QIcon, str) -> int
        """
        Insert a tab at `index`
        """
        button = TabButton(self, objectName="tab-button")
        button.setSizePolicy(QSizePolicy.Expanding,
                             QSizePolicy.Expanding)
        button.setIconSize(self.__iconSize)
        button.setMouseTracking(True)

        self.__group.addButton(button)

        button.installEventFilter(self)

        tab = _Tab(text, icon, toolTip, button, None, None)
        self.layout().insertWidget(index, button)

        self.__tabs.insert(index, tab)
        self.__updateTab(index)

        if self.currentIndex() == -1:
            self.setCurrentIndex(0)

        self.__updateShadows()

        return index

    def removeTab(self, index):
        # type: (int) -> None
        """
        Remove a tab at `index`.
        """
        if 0 <= index < self.count():
            tab = self.__tabs.pop(index)
            layout_index = self.layout().indexOf(tab.button)
            if layout_index != -1:
                self.layout().takeAt(layout_index)

            self.__group.removeButton(tab.button)

            tab.button.removeEventFilter(self)

            if tab.button is self.__sloppyButton:
                self.__sloppyButton = None
                self.__sloppyRegion = QRegion()

            tab.button.deleteLater()
            tab.button.setParent(None)

            if self.currentIndex() == index:
                if self.count():
                    self.setCurrentIndex(max(index - 1, 0))
                else:
                    self.setCurrentIndex(-1)

            self.__updateShadows()

    def setTabIcon(self, index, icon):
        # type: (int, QIcon) -> None
        """
        Set the `icon` for tab at `index`.
        """
        self.__tabs[index] = self.__tabs[index]._replace(icon=QIcon(icon))
        self.__updateTab(index)

    def setTabToolTip(self, index, toolTip):
        # type: (int, str) -> None
        """
        Set `toolTip` for tab at `index`.
        """
        self.__tabs[index] = self.__tabs[index]._replace(toolTip=toolTip)
        self.__updateTab(index)

    def setTabText(self, index, text):
        # type: (int, str) -> None
        """
        Set tab `text` for tab at `index`
        """
        self.__tabs[index] = self.__tabs[index]._replace(text=text)
        self.__updateTab(index)

    def setTabPalette(self, index, palette):
        # type: (int, QPalette) -> None
        """
        Set the tab button palette.
        """
        self.__tabs[index] = self.__tabs[index]._replace(palette=QPalette(palette))
        self.__updateTab(index)

    def setCurrentIndex(self, index):
        # type: (int) -> None
        """
        Set the current tab index.
        """
        if self.__currentIndex != index:
            self.__currentIndex = index

            self.__sloppyRegion = QRegion()
            self.__sloppyButton = None

            if index != -1:
                self.__tabs[index].button.setChecked(True)

            self.currentChanged.emit(index)

    def currentIndex(self):
        # type: () -> int
        """
        Return the current index.
        """
        return self.__currentIndex

    def button(self, index):
        # type: (int) -> QAbstractButton
        """
        Return the `TabButton` instance for index.
        """
        return self.__tabs[index].button

    def setIconSize(self, size):
        # type: (QSize) -> None
        if self.__iconSize != size:
            self.__iconSize = QSize(size)
            for tab in self.__tabs:
                tab.button.setIconSize(self.__iconSize)

    def __updateTab(self, index):
        # type: (int) -> None
        """
        Update the tab button.
        """
        tab = self.__tabs[index]
        b = tab.button

        if tab.text:
            b.setText(tab.text)

        if tab.icon is not None and not tab.icon.isNull():
            b.setIcon(tab.icon)

        if tab.palette:
            b.setPalette(tab.palette)

    def __updateShadows(self):
        currentIndex = self.currentIndex()

        buttons = [tab.button for tab in self.__tabs if tab.button.isVisibleTo(self.parent())]
        if not buttons:
            return

        # set right shadow
        buttonShadows = [2] * len(buttons)

        # if button not visible
        if self.__tabs[currentIndex].button not in buttons:
            belowChosen = aboveChosen = None
        else:
            i = currentIndex + 1
            belowChosen = self.__tabs[i].button if i < len(self.__tabs) else None

            i = currentIndex - 1
            aboveChosen = self.__tabs[i].button if i >= 0 else None

        for i in range(len(buttons)):
            button = buttons[i]
            if button is belowChosen:
                buttonShadows[i] |= 1
            if button is aboveChosen:
                buttonShadows[i] |= 4

            if buttonShadows[i] != button.shadowPosition:
                button.shadowPosition = buttonShadows[i]
                button.update()

    def __onButtonPressed(self, button):
        # type: (QAbstractButton) -> None
        for i, tab in enumerate(self.__tabs):
            if tab.button is button:
                self.setCurrentIndex(i)
                break

    def __calcSloppyRegion(self, current):
        # type: (QPoint) -> QRegion
        """
        Given a current mouse cursor position return a region of the widget
        where hover/move events should change the current tab only on a
        timeout.
        """
        p1 = current + QPoint(0, 2)
        p2 = current + QPoint(0, -2)
        p3 = self.pos() + QPoint(self.width()+10, 0)
        p4 = self.pos() + QPoint(self.width()+10, self.height())
        return QRegion(QPolygon([p1, p2, p3, p4]))

    def __setSloppyButton(self, button):
        # type: (QAbstractButton) -> None
        """
        Set the current sloppy button (a tab button inside sloppy region)
        and reset the sloppy timeout.
        """
        if not button.isChecked():
            self.__sloppyButton = button
            delay = self.style().styleHint(QStyle.SH_Menu_SubMenuPopupDelay, None)
            # The delay timeout is the same as used by Qt in the QMenu.
            self.__sloppyTimer.start(delay)
        else:
            self.__sloppyTimer.stop()

    def __onSloppyTimeout(self):
        # type: () -> None
        if self.__sloppyButton is not None:
            button = self.__sloppyButton
            self.__sloppyButton = None
            if not button.isChecked():
                index = [tab.button for tab in self.__tabs].index(button)
                self.setCurrentIndex(index)

    def eventFilter(self, receiver, event):
        if event.type() == QEvent.MouseMove and \
                isinstance(receiver, TabButton):
            pos = receiver.mapTo(self, event.pos())
            if self.__sloppyRegion.contains(pos):
                self.__setSloppyButton(receiver)
            else:
                if not receiver.isChecked():
                    index = [tab.button for tab in self.__tabs].index(receiver)
                    self.setCurrentIndex(index)
                #also update sloppy region if mouse is moved on the same icon
                self.__sloppyRegion = self.__calcSloppyRegion(pos)

        return super().eventFilter(receiver, event)

    def leaveEvent(self, event):
        self.__sloppyButton = None
        self.__sloppyRegion = QRegion()

        return super().leaveEvent(event)


class PagedMenu(QWidget):
    """
    Tabbed container for :class:`MenuPage` instances.
    """
    triggered = Signal(QAction)
    hovered = Signal(QAction)

    currentChanged = Signal(int)

    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QWidget], Any) -> None
        super().__init__(parent, **kwargs)

        self.__currentIndex = -1

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.__tab = TabBarWidget(self)
        self.__tab.currentChanged.connect(self.setCurrentIndex)
        self.__tab.setChangeOnHover(True)

        self.__stack = MenuStackWidget(self)

        self.navigator = ItemViewKeyNavigator(self)

        layout.addWidget(self.__tab, alignment=Qt.AlignTop)
        layout.addWidget(self.__stack)

        self.setLayout(layout)

        self.update_from_settings()

    def addPage(self, page, title, icon=QIcon(), toolTip=""):
        # type: (QWidget, str, QIcon, str) -> int
        """
        Add a `page` to the menu and return its index.
        """
        return self.insertPage(self.count(), page, title, icon, toolTip)

    def insertPage(self, index, page, title, icon=QIcon(), toolTip=""):
        # type: (int, QWidget, str, QIcon, str) -> int
        """
        Insert `page` at `index`.
        """
        page.triggered.connect(self.triggered)
        page.hovered.connect(self.hovered)

        self.__stack.insertWidget(index, page)
        self.__tab.insertTab(index, title, icon, toolTip)
        return index

    def page(self, index):
        # type: (int) -> QWidget
        """
        Return the page at index.
        """
        return self.__stack.widget(index)

    def removePage(self, index):
        # type: (int) -> None
        """
        Remove the page at `index`.
        """
        page = self.__stack.widget(index)
        page.triggered.disconnect(self.triggered)
        page.hovered.disconnect(self.hovered)

        self.__stack.removeWidget(page)
        self.__tab.removeTab(index)

    def count(self):
        # type: () -> int
        """
        Return the number of pages.
        """
        return self.__stack.count()

    def setCurrentIndex(self, index):
        # type: (int) -> None
        """
        Set the current page index.
        """
        if self.__currentIndex != index:
            self.__currentIndex = index
            self.__tab.setCurrentIndex(index)
            self.__stack.setCurrentIndex(index)

            view = self.currentPage().view()
            self.navigator.setView(view)
            self.navigator.ensureCurrent()
            view.setFocus()

            self.currentChanged.emit(index)

    def currentIndex(self):
        # type: () -> int
        """
        Return the index of the current page.
        """
        return self.__currentIndex

    def nextPage(self):
        """
        Set current index to next index, if one exists.
        """
        index = self.currentIndex() + 1
        if index < self.__stack.count():
            self.setCurrentIndex(index)

    def previousPage(self):
        """
        Set current index to previous index, if one exists.
        """
        index = self.currentIndex() - 1
        if index >= 0:
            self.setCurrentIndex(index)

    def setCurrentPage(self, page):
        # type: (QWidget) -> None
        """
        Set `page` to be the current shown page.
        """
        index = self.__stack.indexOf(page)
        self.setCurrentIndex(index)

    def currentPage(self):
        # type: () -> QWidget
        """
        Return the current page.
        """
        return self.__stack.currentWidget()

    def indexOf(self, page):
        # type: (QWidget) -> int
        """
        Return the index of `page`.
        """
        return self.__stack.indexOf(page)

    def tabButton(self, index):
        # type: (int) -> QAbstractButton
        """
        Return the tab button instance for index.
        """
        return self.__tab.button(index)

    def update_from_settings(self):
        settings = QSettings()
        showCategories = settings.value("quickmenu/show-categories", False, bool)

        if self.count() != 0 and not showCategories:
            self.setCurrentIndex(0)

        self.__tab.setVisible(showCategories)
        if showCategories:
            self.__tab._TabBarWidget__updateShadows()  # why must this be called manually?

        self.navigator.setCategoriesEnabled(showCategories)


def as_qbrush(value):
    # type: (Any) -> Optional[QBrush]
    if isinstance(value, QBrush):
        return value
    else:
        return None


# format with:
# {0} - inactive background
# {1} - active/checked/hover background
# {2} - shadow color
TAB_BUTTON_STYLE_TEMPLATE = """\
TabButton {{
    qproperty-flat_: false;
    qproperty-shadowColor_: {2};
    background: {0};
    border: none;
    border-right: 2px solid {0};
}}

TabButton:checked {{
    background: {1};
    border-right: hidden;
}}
"""

# TODO: Cleanup the QuickMenu interface. It should not have a 'dual' public
# interface (i.e. as an item model view (`setModel` method) and `addPage`,
# ...)


class QuickMenu(FramelessWindow):
    """
    A quick menu popup for the widgets.

    The widgets are set using :func:`QuickMenu.setModel` which must be a
    model as returned by :func:`QtWidgetRegistry.model`

    """

    #: An action has been triggered in the menu.
    triggered = Signal(QAction)

    #: An action has been hovered in the menu
    hovered = Signal(QAction)

    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QWidget], Any) -> None
        super().__init__(parent, **kwargs)
        self.setWindowFlags(self.windowFlags() | Qt.Popup)

        self.__filterFunc = None  # type: Optional[FilterFunc]
        self.__sortingFunc = None  # type: Optional[Callable[[Any, Any], bool]]

        self.setLayout(QVBoxLayout(self))
        self.layout().setContentsMargins(6, 6, 6, 6)
        self.layout().setSpacing(self.radius())

        self.__search = SearchWidget(self, objectName="search-line")
        self.__search.setPlaceholderText(
            self.tr("Search for a widget...")
        )
        self.__search.setChecked(True)

        self.layout().addWidget(self.__search)

        self.__frame = QFrame(self, objectName="menu-frame")
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.__frame.setLayout(layout)

        self.layout().addWidget(self.__frame)

        self.__pages = PagedMenu(self, objectName="paged-menu")
        self.__pages.currentChanged.connect(self.setCurrentIndex)
        self.__pages.triggered.connect(self.triggered)
        self.__pages.hovered.connect(self.hovered)

        self.__frame.layout().addWidget(self.__pages)

        self.setSizePolicy(QSizePolicy.Fixed,
                           QSizePolicy.Expanding)

        self.__suggestPage = SuggestMenuPage(self, objectName="suggest-page")
        self.__suggestPage.setActionRole(QtWidgetRegistry.WIDGET_ACTION_ROLE)
        self.__suggestPage.setIcon(icon_loader().get("icons/Search.svg"))

        self.__search.installEventFilter(self.__pages.navigator)
        self.__pages.navigator.setView(self.__suggestPage.view())

        if sys.platform == "darwin":
            view = self.__suggestPage.view()
            view.verticalScrollBar().setAttribute(Qt.WA_MacMiniSize, True)
            # Don't show the focus frame because it expands into the tab bar.
            view.setAttribute(Qt.WA_MacShowFocusRect, False)

        i = self.addPage(self.tr("Quick Search"), self.__suggestPage)
        button = self.__pages.tabButton(i)
        button.setVisible(False)

        searchAction = self.__search.actionAt(SearchWidget.LeftPosition)
        searchAction.hovered.connect(self.triggerSearch)

        self.__pages.currentChanged.connect(lambda index:
                                            self.__search.setChecked(i == index))

        self.__search.textEdited.connect(self.__on_textEdited)

        self.__grip = WindowSizeGrip(self)  # type: Optional[WindowSizeGrip]
        self.__grip.raise_()

        self.__loop = None   # type: Optional[QEventLoop]
        self.__model = None  # type: Optional[QAbstractItemModel]
        self.setModel(QStandardItemModel())
        self.__triggeredAction = None  # type: Optional[QAction]

    def setSizeGripEnabled(self, enabled):
        # type: (bool) -> None
        """
        Enable the resizing of the menu with a size grip in a bottom
        right corner (enabled by default).
        """
        if bool(enabled) != bool(self.__grip):
            if self.__grip:
                self.__grip.deleteLater()
                self.__grip = None
            else:
                self.__grip = WindowSizeGrip(self)
                self.__grip.raise_()

    def sizeGripEnabled(self):
        # type: () -> bool
        """
        Is the size grip enabled.
        """
        return bool(self.__grip)

    def addPage(self, name, page):
        # type: (str, MenuPage) -> int
        """
        Add the `page` (:class:`MenuPage`) with `name` and return it's index.
        The `page.icon()` will be used as the icon in the tab bar.
        """
        return self.insertPage(self.__pages.count(), name, page)

    def insertPage(self, index, name, page):
        # type: (int, str, MenuPage) -> int
        icon = page.icon()

        tip = name
        if page.toolTip():
            tip = page.toolTip()

        index = self.__pages.insertPage(index, page, name, icon, tip)

        # Route the page's signals
        page.triggered.connect(self.__onTriggered)
        page.hovered.connect(self.hovered)

        # All page views focus on the search LineEdit
        page.view().setFocusProxy(self.__search)

        return index

    def createPage(self, index):
        # type: (QModelIndex) -> MenuPage
        """
        Create a new page based on the contents of an index
        (:class:`QModeIndex`) item.
        """
        page = MenuPage(self)

        page.setModel(index.model())
        page.setRootIndex(index)

        view = page.view()

        if sys.platform == "darwin":
            view.verticalScrollBar().setAttribute(Qt.WA_MacMiniSize, True)
            # Don't show the focus frame because it expands into the tab
            # bar at the top.
            view.setAttribute(Qt.WA_MacShowFocusRect, False)

        name = str(index.data(Qt.DisplayRole))
        page.setTitle(name)

        icon = index.data(Qt.DecorationRole)
        if isinstance(icon, QIcon):
            page.setIcon(icon)

        page.setToolTip(index.data(Qt.ToolTipRole))
        return page

    def __clear(self):
        # type: () -> None
        for i in range(self.__pages.count() - 1, 0, -1):
            self.__pages.removePage(i)

    def setModel(self, model):
        # type: (QAbstractItemModel) -> None
        """
        Set the model containing the actions.
        """
        if self.__model is not None:
            self.__model.dataChanged.disconnect(self.__on_dataChanged)
            self.__model.rowsInserted.disconnect(self.__on_rowsInserted)
            self.__model.rowsRemoved.disconnect(self.__on_rowsRemoved)
            self.__clear()

        for i in range(model.rowCount()):
            index = model.index(i, 0)
            self.__insertPage(i + 1, index)

        self.__model = model
        self.__suggestPage.setModel(model)
        if model is not None:
            model.dataChanged.connect(self.__on_dataChanged)
            model.rowsInserted.connect(self.__on_rowsInserted)
            model.rowsRemoved.connect(self.__on_rowsRemoved)

    def __on_dataChanged(self, topLeft, bottomRight):
        # type: (QModelIndex, QModelIndex) -> None
        parent = topLeft.parent()
        # Only handle top level item (categories).
        if not parent.isValid():
            for row in range(topLeft.row(), bottomRight.row() + 1):
                index = topLeft.sibling(row, 0)
                # Note: the tab buttons are offest by 1 (to accommodate
                # the Suggest Page).
                button = self.__pages.tabButton(row + 1)
                brush = as_qbrush(index.data(QtWidgetRegistry.BACKGROUND_ROLE))
                if brush is not None:
                    base_color = brush.color()
                    shadow_color = base_color.fromHsv(base_color.hsvHue(),
                                                      base_color.hsvSaturation(),
                                                      100)
                    button.setStyleSheet(
                        TAB_BUTTON_STYLE_TEMPLATE.format
                        (base_color.darker(110).name(),
                         base_color.name(),
                         shadow_color.name())
                    )

    def __on_rowsInserted(self, parent, start, end):
        # type: (QModelIndex, int, int) -> None
        # Only handle top level item (categories).
        assert self.__model is not None
        if not parent.isValid():
            for row in range(start, end + 1):
                index = self.__model.index(row, 0)
                self.__insertPage(row + 1, index)

    def __on_rowsRemoved(self, parent, start, end):
        # type: (QModelIndex, int, int) -> None
        # Only handle top level item (categories).
        if not parent.isValid():
            for row in range(end, start - 1, -1):
                self.__removePage(row + 1)

    def __insertPage(self, row, index):
        # type: (int, QModelIndex) -> None
        page = self.createPage(index)
        page.setActionRole(QtWidgetRegistry.WIDGET_ACTION_ROLE)

        i = self.insertPage(row, page.title(), page)

        brush = as_qbrush(index.data(QtWidgetRegistry.BACKGROUND_ROLE))
        if brush is not None:
            base_color = brush.color()
            shadow_color = base_color.fromHsv(base_color.hsvHue(),
                                              base_color.hsvSaturation(),
                                              100)
            button = self.__pages.tabButton(i)
            button.setStyleSheet(
                TAB_BUTTON_STYLE_TEMPLATE.format
                (base_color.darker(110).name(),
                 base_color.name(),
                 shadow_color.name())
            )

    def __removePage(self, row):
        # type: (int) -> None
        page = self.__pages.page(row)
        page.triggered.disconnect(self.__onTriggered)
        page.hovered.disconnect(self.hovered)
        page.view().removeEventFilter(self)
        self.__pages.removePage(row)

    def setSortingFunc(self, func):
        # type: (Callable[[Any, Any], bool]) -> None
        """
        Set a sorting function in the suggest (search) menu.
        """
        if self.__sortingFunc != func:
            self.__sortingFunc = func
            for i in range(0, self.__pages.count()):
                page = self.__pages.page(i)
                if isinstance(page, SuggestMenuPage):
                    page.setSortingFunc(func)

    def setFilterFunc(self, func):
        # type: (Optional[FilterFunc]) -> None
        """
        Set a filter function.
        """
        if func != self.__filterFunc:
            self.__filterFunc = func
            for i in range(0, self.__pages.count()):
                self.__pages.page(i).setFilterFunc(func)

    def popup(self, pos=None, searchText=""):
        # type: (Optional[QPoint], str) -> None
        """
        Popup the menu at `pos` (in screen coordinates). 'Search' text field
        is initialized with `searchText` if provided.
        """
        if pos is None:
            pos = QPoint()

        self.__clearCurrentItems()

        self.__search.setText(searchText)
        patt = QRegExp(r"(^|\W)"+searchText)
        patt.setCaseSensitivity(Qt.CaseInsensitive)
        self.__suggestPage.setFilterRegExp(patt)

        UsageStatistics.set_last_search_query(searchText)

        self.ensurePolished()

        if self.testAttribute(Qt.WA_Resized) and self.sizeGripEnabled():
            size = self.size()
        else:
            size = self.sizeHint()
            settings = QSettings()
            ssize = settings.value('quickmenu/size', defaultValue=QSize(),
                                   type=QSize)
            if ssize.isValid():
                size.setHeight(ssize.height())
                size = size.expandedTo(self.minimumSizeHint())

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

        self.setGeometry(geom)

        self.show()

        self.setFocusProxy(self.__search)

    def exec_(self, pos=None, searchText=""):
        # type: (Optional[QPoint], str) -> Optional[QAction]
        """
        Execute the menu at position `pos` (in global screen coordinates).
        Return the triggered :class:`QAction` or `None` if no action was
        triggered. 'Search' text field is initialized with `searchText` if
        provided.
        """
        self.popup(pos, searchText)
        self.setFocus(Qt.PopupFocusReason)

        self.__triggeredAction = None
        self.__loop = QEventLoop()
        self.__loop.exec_()
        self.__loop.deleteLater()
        self.__loop = None

        action = self.__triggeredAction
        self.__triggeredAction = None
        return action

    def hideEvent(self, event):
        """
        Reimplemented from :class:`QWidget`
        """
        settings = QSettings()
        settings.setValue('quickmenu/size', self.size())
        super().hideEvent(event)
        if self.__loop:
            self.__loop.exit()

    def setCurrentPage(self, page):
        # type: (MenuPage) -> None
        """
        Set the current shown page to `page`.
        """
        self.__pages.setCurrentPage(page)

    def setCurrentIndex(self, index):
        # type: (int) -> None
        """
        Set the current page index.
        """
        self.__pages.setCurrentIndex(index)

    def __clearCurrentItems(self):
        # type: () -> None
        """
        Clear any selected (or current) items in all the menus.
        """
        for i in range(self.__pages.count()):
            self.__pages.page(i).view().selectionModel().clear()

    def __onTriggered(self, action):
        # type: (QAction) -> None
        """
        Re-emit the action from the page.
        """
        self.__triggeredAction = action

        # Hide and exit the event loop if necessary.
        self.hide()
        self.triggered.emit(action)

    def __on_textEdited(self, text):
        # type: (str) -> None
        patt = QRegExp(r"(^|\W)" + text)
        patt.setCaseSensitivity(Qt.CaseInsensitive)
        self.__suggestPage.setFilterRegExp(patt)
        self.__pages.setCurrentPage(self.__suggestPage)
        self.__selectFirstIndex()
        UsageStatistics.set_last_search_query(text)

    def __selectFirstIndex(self):
        # type: () -> None
        view = self.__pages.currentPage().view()
        model = view.model()

        index = model.index(0, 0)
        view.setCurrentIndex(index)

    def triggerSearch(self):
        # type: () -> None
        """
        Trigger action search. This changes to current page to the
        'Suggest' page and sets the keyboard focus to the search line edit.
        """
        self.__pages.setCurrentPage(self.__suggestPage)
        self.__search.setFocus(Qt.ShortcutFocusReason)

        # Make sure that the first enabled item is set current.
        self.__suggestPage.ensureCurrent()

    def update_from_settings(self):
        self.__pages.update_from_settings()


class ItemViewKeyNavigator(QObject):
    """
    A event filter class listening to key press events and responding
    by moving 'currentItem` on a :class:`QListView`.
    """
    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QObject], Any) -> None
        super().__init__(parent, **kwargs)
        self.__view = None  # type: Optional[QAbstractItemView]
        self.__categoriesEnabled = False

    def setCategoriesEnabled(self, enabled):
        self.__categoriesEnabled = enabled

    def setView(self, view):
        # type: (Optional[QAbstractItemView]) -> None
        """
        Set the QListView.
        """
        if self.__view != view:
            self.__view = view

    def view(self):
        # type: () -> Optional[QAbstractItemView]
        """
        Return the view
        """
        return self.__view

    def eventFilter(self, obj, event):
        etype = event.type()
        if etype == QEvent.KeyPress:
            key = event.key()
            # down
            if key == Qt.Key_Down:
                self.moveCurrent(1, 0)
                return True
            # up
            elif key == Qt.Key_Up:
                self.moveCurrent(-1, 0)
                return True
            # enter / return
            elif key == Qt.Key_Enter or key == Qt.Key_Return:
                self.activateCurrent()
                return True
            # shift + tab
            elif key == Qt.Key_Backtab:
                if self.__categoriesEnabled:
                    self.parent().previousPage()
                return True
            # tab
            elif key == Qt.Key_Tab:
                if self.__categoriesEnabled:
                    self.parent().nextPage()
                return True

        return super().eventFilter(obj, event)

    def moveCurrent(self, rows, columns=0):
        # type: (int, int) -> None
        """
        Move the current index by rows, columns.
        """
        if self.__view is not None:
            view = self.__view
            model = view.model()
            root = view.rootIndex()

            curr = view.currentIndex()
            curr_row, curr_col = curr.row(), curr.column()

            sign = 1 if rows >= 0 else -1

            row = curr_row
            row_count = model.rowCount(root)
            for _ in range(row_count):
                row = (row + sign) % row_count
                index = root.child(row, 0) if root.isValid() else model.index(row, 0)
                if index.flags() & Qt.ItemIsEnabled:
                    view.selectionModel().setCurrentIndex(
                        index,
                        QItemSelectionModel.ClearAndSelect
                    )
                    break
            # TODO: move by columns

    def activateCurrent(self):
        # type: () -> None
        """
        Activate the current index.
        """
        if self.__view is not None:
            curr = self.__view.currentIndex()
            if curr.isValid():
                self.__view.activated.emit(curr)

    def ensureCurrent(self):
        # type: () -> None
        """
        Ensure the view has a current item if one is available.
        """
        if self.__view is not None:
            model = self.__view.model()
            curr = self.__view.currentIndex()
            if not curr.isValid():
                root = self.__view.rootIndex()
                for i in range(model.rowCount(root)):
                    index = root.child(i, 0) if root.isValid() else model.index(i, 0)
                    if index.flags() & Qt.ItemIsEnabled:
                        self.__view.setCurrentIndex(index)
                        break


class WindowSizeGrip(QSizeGrip):
    """
    Automatically positioning :class:`QSizeGrip`.
    The widget automatically maintains its position in the window
    corner during resize events.

    """
    def __init__(self, parent):
        super().__init__(parent)
        self.__corner = Qt.BottomRightCorner

        self.resize(self.sizeHint())

        self.__updatePos()

    def setCorner(self, corner):
        """
        Set the corner (:class:`Qt.Corner`) where the size grip should
        position itself.

        """
        if corner not in [Qt.TopLeftCorner, Qt.TopRightCorner,
                          Qt.BottomLeftCorner, Qt.BottomRightCorner]:
            raise ValueError("Qt.Corner flag expected")

        if self.__corner != corner:
            self.__corner = corner
            self.__updatePos()

    def corner(self):
        """
        Return the corner where the size grip is positioned.
        """
        return self.__corner

    def eventFilter(self, obj, event):
        if obj is self.window():
            if event.type() == QEvent.Resize:
                self.__updatePos()
        return super().eventFilter(obj, event)

    def sizeHint(self):
        self.ensurePolished()
        sh = super().sizeHint()
        # Qt5 on macOS forces size grip to be zero size.
        if sh.width() == 0 and \
                QApplication.style().metaObject().className() == "QMacStyle":
            sh.setWidth(sh.height())
        return sh

    def changeEvent(self, event):
        # type: (QEvent) -> None
        super().changeEvent(event)
        if event.type() in (QEvent.StyleChange, QEvent.MacSizeChange):
            self.resize(self.sizeHint())
            self.__updatePos()
        super().changeEvent(event)

    def __updatePos(self):
        window = self.window()

        if window is not self.parent():
            return

        corner = self.__corner
        size = self.size()

        window_geom = window.geometry()
        window_size = window_geom.size()

        if corner in [Qt.TopLeftCorner, Qt.BottomLeftCorner]:
            x = 0
        else:
            x = window_geom.width() - size.width()

        if corner in [Qt.TopLeftCorner, Qt.TopRightCorner]:
            y = 0
        else:
            y = window_size.height() - size.height()

        self.move(x, y)

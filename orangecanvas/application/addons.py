import types
import enum
import sys
import sysconfig
import os
import logging
import errno
import shlex
import itertools
import json
import traceback
import typing

from concurrent.futures import ThreadPoolExecutor, Future
from collections import deque

from typing import (
    List, Dict, Any, Optional, Union, Tuple, NamedTuple, Callable, AnyStr,
    Iterable
)

import requests
import pkg_resources

from AnyQt.QtWidgets import (
    QWidget, QDialog, QLabel, QLineEdit, QTreeView, QHeaderView,
    QTextBrowser, QDialogButtonBox, QProgressDialog, QVBoxLayout,
    QPushButton, QFormLayout, QHBoxLayout, QMessageBox,
    QStyledItemDelegate, QStyle, QApplication, QStyleOptionViewItem
)
from AnyQt.QtGui import (
    QStandardItemModel, QStandardItem, QPalette, QTextOption,
    QDropEvent, QDragEnterEvent
)
from AnyQt.QtCore import (
    QSortFilterProxyModel, QItemSelectionModel,
    Qt, QObject, QMetaObject, QSize, QTimer, QThread, Q_ARG,
    QSettings, QStandardPaths, QEvent, QAbstractItemModel, QModelIndex
)
from AnyQt.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from orangecanvas.utils import unique, name_lookup, markup
from orangecanvas.utils.shtools import python_process, create_process, \
    temp_named_file
from ..gui.utils import message_warning, message_critical as message_error
from ..help.manager import get_dist_meta, parse_meta

from .. import config
from ..config import Config

Requirement = pkg_resources.Requirement
Distribution = pkg_resources.Distribution

log = logging.getLogger(__name__)


class Installable(
    NamedTuple(
        "Installable", (
            ("name", str),
            ("version", str),
            ("summary", str),
            ("description", str),
            ("package_url", str),
            ("release_urls", List['ReleaseUrl']),
            ("description_content_type", Optional[str]),
        ))):
    """
    An installable distribution from PyPi

    Attributes
    ----------
    name: str
        The distribution/project name
    version: str
        The release version
    summary: str
        Short one line summary text
    description: str
        A longer more detailed description
    package_url: str
    release_urls: List[ReleaseUrls]
    """

Installable.__new__.__defaults__ = (
    None,  # description_content_type = None,
)


class ReleaseUrl(
    NamedTuple(
        "ReleaseUrl", (
            ("filename", str),
            ("url", str),
            ("size", int),
            ("python_version", str),
            ("package_type", str),
        ))):
    """
    An source/wheel/egg release for a distribution,
    """


class Available(
    NamedTuple(
        "Available", (
            ("installable", Installable),
    ))):
    """
    An available package.

    Attributes
    ----------
    installable : Installable
    """


class Installed(
    NamedTuple(
        "Installed", (
            ("installable", Optional[Installable]),
            ("local", 'Distribution'),
            ("required", bool),
            ("constraint", Optional[Requirement]),
        ))):
    """
    An installed package. Does not need to have a corresponding installable
    entry (eg. only local or private distribution)

    Attributes
    ----------
    installable: Installable
        An optional installable item. Is None if the package is not available
        from any package index (is not published and installed locally or
        possibly orphaned).
    local : Distribution
        A :class:`~.Distribution` instance representing the distribution meta
        of the locally installed package.
    required : bool
        Is the distribution required (is part of the core application and
        must not be uninstalled).
    constraint: Optional[Requirement]
        A version constraint string.
    """
    def __new__(cls, installable, local, required=False, constraint=None):
        # type: (Optional[Installable], Distribution, bool, Optional[Requirement]) -> Installed
        return super().__new__(cls, installable, local, required, constraint)


#: An installable item/slot
Item = Union[Available, Installed]


def is_updatable(item):
    # type: (Item) -> bool
    if isinstance(item, Available):
        return False
    elif item.installable is None:
        return False
    else:
        inst, dist = item.installable, item.local
        try:
            v1 = pkg_resources.parse_version(dist.version)
            v2 = pkg_resources.parse_version(inst.version)
        except ValueError:
            return False

        if item.constraint is not None and str(v2) not in item.constraint:
            return False
        else:
            return v1 < v2


def get_meta_from_archive(path):
    """Return project metadata extracted from sdist or wheel archive, or None
    if metadata can't be found."""

    def is_metadata(fname):
        return fname.endswith(('PKG-INFO', 'METADATA'))

    meta = None
    if path.endswith(('.zip', '.whl')):
        from zipfile import ZipFile
        with ZipFile(path) as archive:
            meta = next(filter(is_metadata, archive.namelist()), None)
            if meta:
                meta = archive.read(meta).decode('utf-8')
    elif path.endswith(('.tar.gz', '.tgz')):
        import tarfile
        with tarfile.open(path) as archive:
            meta = next(filter(is_metadata, archive.getnames()), None)
            if meta:
                meta = archive.extractfile(meta).read().decode('utf-8')
    if meta:
        return parse_meta(meta)


HasConstraintRole = Qt.UserRole + 0xf45
DetailedText = HasConstraintRole + 1


def description_rich_text(item):  # type: (Item) -> str
    description = ""     # type: str
    content_type = None  # type: Optional[str]

    if isinstance(item, Installed):
        remote, dist = item.installable, item.local
        if remote is None:
            meta = get_dist_meta(dist)
            description = meta.get("Description", "") or \
                          meta.get('Summary', "")
            content_type = meta.get("Description-Content-Type")
        else:
            description = remote.description
            content_type = remote.description_content_type
    else:
        description = item.installable.description
        content_type = item.installable.description_content_type

    try:
        html = markup.render_as_rich_text(description, content_type)
    except Exception:
        html = markup.render_as_rich_text(description, "text/plain")
    return html


class ActionItem(QStandardItem):
    def data(self, role=Qt.UserRole + 1) -> Any:
        if role == Qt.DisplayRole:
            model = self.model()
            modelindex = self._sibling(PluginsModel.StateColumn)
            item = model.data(modelindex, Qt.UserRole)
            state = model.data(modelindex, Qt.CheckStateRole)
            flags = model.flags(modelindex)
            if flags & Qt.ItemIsUserTristate and state == Qt.Checked:
                return "Update"
            elif isinstance(item, Available) and state == Qt.Checked:
                return "Install"
            elif isinstance(item, Installed) and state == Qt.Unchecked:
                return "Uninstall"
            else:
                return ""
        elif role == DetailedText:
            item = self.data(Qt.UserRole)
            if isinstance(item, (Available, Installed)):
                return description_rich_text(item)
        return super().data(role)

    def _sibling(self, column) -> QModelIndex:
        model = self.model()
        if model is None:
            return QModelIndex()
        index = model.indexFromItem(self)
        return index.sibling(self.row(), column)

    def _siblingData(self, column: int, role: int):
        return self._sibling(column).data(role)


class StateItem(QStandardItem):
    def setData(self, value: Any, role: int = Qt.UserRole + 1) -> None:
        if role == Qt.CheckStateRole:
            super().setData(value, role)
            # emit the dependent ActionColumn's data changed
            sib = self.index().sibling(self.row(), PluginsModel.ActionColumn)
            if sib.isValid():
                self.model().dataChanged.emit(sib, sib, (Qt.DisplayRole,))
            return
        return super().setData(value, role)

    def data(self, role=Qt.UserRole + 1):
        if role == DetailedText:
            item = self.data(Qt.UserRole)
            if isinstance(item, (Available, Installed)):
                return description_rich_text(item)
        return super().data(role)


class PluginsModel(QStandardItemModel):
    StateColumn, NameColumn, VersionColumn, ActionColumn = range(4)

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.setHorizontalHeaderLabels(
            ["", self.tr("Name"), self.tr("Version"), self.tr("Action")]
        )

    @staticmethod
    def createRow(item):
        # type: (Item) -> List[QStandardItem]
        dist = None  # type: Optional[Distribution]
        if isinstance(item, Installed):
            installed = True
            ins, dist = item.installable, item.local
            name = dist.project_name
            summary = get_dist_meta(dist).get("Summary", "")
            version = ins.version if ins is not None else dist.version
            item_is_core = item.required
        else:
            installed = False
            ins = item.installable
            dist = None
            name = ins.name
            summary = ins.summary
            version = ins.version
            item_is_core = False

        updatable = is_updatable(item)

        item1 = StateItem()
        item1.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable |
                       Qt.ItemIsUserCheckable |
                       (Qt.ItemIsUserTristate if updatable else 0))
        item1.setEnabled(not (item_is_core and not updatable))
        item1.setData(item_is_core, HasConstraintRole)

        if installed and updatable:
            item1.setCheckState(Qt.PartiallyChecked)
        elif installed:
            item1.setCheckState(Qt.Checked)
        else:
            item1.setCheckState(Qt.Unchecked)
        item1.setData(item, Qt.UserRole)

        item2 = QStandardItem(name)
        item2.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        item2.setToolTip(summary)
        item2.setData(item, Qt.UserRole)

        if updatable:
            assert dist is not None
            assert ins is not None
            version = "{} < {}".format(dist.version, ins.version)

        item3 = QStandardItem(version)
        item3.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

        item4 = ActionItem()
        item4.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

        return [item1, item2, item3, item4]

    def itemState(self):
        # type: () -> List['Action']
        """
        Return the current `items` state encoded as a list of actions to be
        performed.

        Return
        ------
        actions : List['Action']
            For every item that is has been changed in the GUI interface
            return a tuple of (command, item) where Command is one of
             `Install`, `Uninstall`, `Upgrade`.
        """
        steps = []
        for i in range(self.rowCount()):
            modelitem = self.item(i, 0)
            item = modelitem.data(Qt.UserRole)
            state = modelitem.checkState()
            if modelitem.flags() & Qt.ItemIsUserTristate and state == Qt.Checked:
                steps.append((Upgrade, item))
            elif isinstance(item, Available) and state == Qt.Checked:
                steps.append((Install, item))
            elif isinstance(item, Installed) and state == Qt.Unchecked:
                steps.append((Uninstall, item))

        return steps

    def setItemState(self, steps):
        # type: (List['Action']) -> None
        """
        Set the current state as a list of actions to perform.

        i.e. `w.setItemState([(Install, item1), (Uninstall, item2)])`
        will mark item1 for installation and item2 for uninstallation, all
        other items will be reset to their default state

        Parameters
        ----------
        steps : List[Tuple[Command, Item]]
            State encoded as a list of commands.
        """
        if self.rowCount() == 0:
            return

        for row in range(self.rowCount()):
            modelitem = self.item(row, 0)  # type: QStandardItem
            item = modelitem.data(Qt.UserRole)  # type: Item
            # Find the action command in the steps list for the item
            cmd = None  # type: Optional[Command]
            for cmd_, item_ in steps:
                if item == item_:
                    cmd = cmd_
                    break
            if isinstance(item, Available):
                modelitem.setCheckState(
                    Qt.Checked if cmd == Install else Qt.Unchecked
                )
            elif isinstance(item, Installed):
                if cmd == Upgrade:
                    modelitem.setCheckState(Qt.Checked)
                elif cmd == Uninstall:
                    modelitem.setCheckState(Qt.Unchecked)
                elif is_updatable(item):
                    modelitem.setCheckState(Qt.PartiallyChecked)
                else:
                    modelitem.setCheckState(Qt.Checked)
            else:
                assert False


class TristateCheckItemDelegate(QStyledItemDelegate):
    """
    A QStyledItemDelegate with customizable Qt.CheckStateRole state toggle
    on user interaction.
    """
    def editorEvent(self, event, model, option, index):
        # type: (QEvent, QAbstractItemModel, QStyleOptionViewItem, QModelIndex) -> bool
        """
        Reimplemented.
        """
        flags = model.flags(index)
        if not flags & Qt.ItemIsUserCheckable or \
                not option.state & QStyle.State_Enabled or \
                not flags & Qt.ItemIsEnabled:
            return False

        checkstate = model.data(index, Qt.CheckStateRole)
        if checkstate is None:
            return False

        widget = option.widget
        style = widget.style() if widget is not None else QApplication.style()
        if event.type() in {QEvent.MouseButtonPress, QEvent.MouseButtonRelease,
                            QEvent.MouseButtonDblClick}:
            pos = event.pos()
            opt = QStyleOptionViewItem(option)
            self.initStyleOption(opt, index)
            rect = style.subElementRect(
                QStyle.SE_ItemViewItemCheckIndicator, opt, widget)

            if event.button() != Qt.LeftButton or not rect.contains(pos):
                return False

            if event.type() in {QEvent.MouseButtonPress,
                                QEvent.MouseButtonDblClick}:
                return True

        elif event.type() == QEvent.KeyPress:
            if event.key() != Qt.Key_Space and event.key() != Qt.Key_Select:
                return False
        else:
            return False
        checkstate = self.nextCheckState(checkstate, index)
        return model.setData(index, checkstate, Qt.CheckStateRole)

    def nextCheckState(self, state, index):
        # type: (Qt.CheckState, QModelIndex) -> Qt.CheckState
        """
        Return the next check state for index.
        """
        constraint = index.data(HasConstraintRole)
        flags = index.flags()
        if flags & Qt.ItemIsUserTristate and constraint:
            return Qt.PartiallyChecked if state == Qt.Checked else Qt.Checked
        elif flags & Qt.ItemIsUserTristate:
            return Qt.CheckState((state + 1) % 3)
        else:
            return Qt.Unchecked if state == Qt.Checked else Qt.Checked


class AddonManagerWidget(QWidget):

    stateChanged = Signal()

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.__items = []  # type: List[Item]

        self.setLayout(QVBoxLayout())

        self.__header = QLabel(
            wordWrap=True,
            textFormat=Qt.RichText
        )
        self.__search = QLineEdit(
            placeholderText=self.tr("Filter")
        )
        self.tophlayout = topline = QHBoxLayout()
        topline.addWidget(self.__search)
        self.layout().addLayout(topline)

        self.__view = view = QTreeView(
            rootIsDecorated=False,
            editTriggers=QTreeView.NoEditTriggers,
            selectionMode=QTreeView.SingleSelection,
            alternatingRowColors=True
        )
        view.setItemDelegateForColumn(0, TristateCheckItemDelegate(view))
        self.layout().addWidget(view)

        self.__model = model = PluginsModel()
        model.dataChanged.connect(self.__data_changed)
        proxy = QSortFilterProxyModel(
            filterKeyColumn=1,
            filterCaseSensitivity=Qt.CaseInsensitive
        )
        proxy.setSourceModel(model)
        self.__search.textChanged.connect(proxy.setFilterFixedString)

        view.setModel(proxy)
        view.selectionModel().selectionChanged.connect(
            self.__update_details
        )
        header = self.__view.header()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self.__details = QTextBrowser(
            frameShape=QTextBrowser.NoFrame,
            readOnly=True,
            lineWrapMode=QTextBrowser.WidgetWidth,
            openExternalLinks=True,
        )

        self.__details.setWordWrapMode(QTextOption.WordWrap)
        palette = QPalette(self.palette())
        palette.setColor(QPalette.Base, Qt.transparent)
        self.__details.setPalette(palette)
        self.layout().addWidget(self.__details)

    def setItems(self, items):
        # type: (List[Item]) -> None
        """
        Set a list of items to display.

        Parameters
        ----------
        items: List[Item]
            A list of :class:`Available` or :class:`Installed`
        """
        self.__items = items
        model = self.__model
        model.setRowCount(0)

        for item in items:
            row = model.createRow(item)
            model.appendRow(row)

        model.sort(1)

        self.__view.resizeColumnToContents(0)
        self.__view.setColumnWidth(
            1, max(150, self.__view.sizeHintForColumn(1)))
        self.__view.setColumnWidth(
            2, max(150, self.__view.sizeHintForColumn(2)))

        if self.__items:
            self.__view.selectionModel().select(
                self.__view.model().index(0, 0),
                QItemSelectionModel.Select | QItemSelectionModel.Rows
            )

    def items(self):
        # type: () -> List[Item]
        """
        Return a list of items.

        Return
        ------
        items: List[Item]
        """
        return list(self.__items)

    def itemState(self):
        # type: () -> List['Action']
        """
        Return the current `items` state encoded as a list of actions to be
        performed.

        Return
        ------
        actions : List['Action']
            For every item that is has been changed in the GUI interface
            return a tuple of (command, item) where Ccmmand is one of
             `Install`, `Uninstall`, `Upgrade`.
        """
        return self.__model.itemState()

    def setItemState(self, steps):
        # type: (List['Action']) -> None
        """
        Set the current state as a list of actions to perform.

        i.e. `w.setItemState([(Install, item1), (Uninstall, item2)])`
        will mark item1 for installation and item2 for uninstallation, all
        other items will be reset to their default state

        Parameters
        ----------
        steps : List[Tuple[Command, Item]]
            State encoded as a list of commands.
        """
        self.__model.setItemState(steps)

    def __selected_row(self):
        indices = self.__view.selectedIndexes()
        if indices:
            proxy = self.__view.model()
            indices = [proxy.mapToSource(index) for index in indices]
            return indices[0].row()
        else:
            return -1

    def __data_changed(self, topleft, bottomright):
        self.stateChanged.emit()

    def __update_details(self):
        index = self.__selected_row()
        if index == -1:
            text = ""
            self.__details.setText("")
        else:
            item = self.__model.item(index, PluginsModel.StateColumn)
            text = item.data(DetailedText)
            if not isinstance(text, str):
                text = ""
        self.__details.setText(text)

    def sizeHint(self):
        return QSize(480, 420)


def method_queued(method, sig, conntype=Qt.QueuedConnection):
    # type: (types.MethodType, Tuple[type, ...], int) -> Callable[[], bool]
    name = method.__name__
    obj = method.__self__
    if not isinstance(obj, QObject):
        raise TypeError()

    def call(*args):
        args = [Q_ARG(atype, arg) for atype, arg in zip(sig, args)]
        return QMetaObject.invokeMethod(obj, name, conntype, *args)

    return call


class _QueryResult(types.SimpleNamespace):
    queryname = None    # type: str
    installable = None  # type: Optional[Installable]


class AddonManagerDialog(QDialog):
    """
    A add-on manager dialog.
    """
    #: cached packages list.
    __packages = None  # type: List[Installable]
    __f_pypi_addons = None
    __config = None    # type: Optional[Config]

    def __init__(self, parent=None, acceptDrops=True, **kwargs):
        super().__init__(parent, acceptDrops=acceptDrops, **kwargs)
        self.setLayout(QVBoxLayout())

        self.addonwidget = AddonManagerWidget()
        self.addonwidget.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(self.addonwidget)
        buttons = QDialogButtonBox(
            orientation=Qt.Horizontal,
            standardButtons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel,

        )
        addmore = QPushButton(
            "Add more...", toolTip="Add an add-on not listed below",
            autoDefault=False
        )
        self.addonwidget.tophlayout.addWidget(addmore)
        addmore.clicked.connect(self.__run_add_package_dialog)

        buttons.accepted.connect(self.__accepted)
        buttons.rejected.connect(self.reject)

        self.layout().addWidget(buttons)
        self.__progress = None  # type: Optional[QProgressDialog]

        self.__executor = ThreadPoolExecutor(max_workers=1)
        # The installer thread
        self.__thread = None
        # The installer object
        self.__installer = None
        self.__add_package_by_name_dialog = None  # type: Optional[QDialog]

    def setConfig(self, config):
        self.__config = config

    def config(self):
        # type: () -> Config
        if self.__config is None:
            return config.default
        else:
            return self.__config

    @Slot()
    def start(self, config):
        # type: (Config) -> None
        """
        Initialize the dialog/manager for the specified configuration namespace.

        Calling this method will start an async query of ...

        At the end the found items will be set using `setItems` overriding any
        previously set items.

        Parameters
        ----------
        config : config.Config
        """
        self.__config = config

        if self.__packages is not None:
            # method_queued(self.setItems, (object,))(self.__packages)
            installed = [ep.dist for ep in config.addon_entry_points()
                         if ep.dist is not None]
            items = installable_items(self.__packages, installed)
            self.setItems(items)
            return

        progress = self.progressDialog()
        self.show()
        progress.show()
        progress.setLabelText(
            self.tr("Retrieving package list")
        )
        self.__f_pypi_addons = self.__executor.submit(
            lambda config=config: (config, list_available_versions(config)),
        )
        self.__f_pypi_addons.add_done_callback(
            method_queued(self.__on_query_done, (object,))
        )

    @Slot(object)
    def __on_query_done(self, f):
        # type: (Future[Tuple[Config, List[Installable]]]) -> None
        assert f.done()
        if self.__progress is not None:
            self.__progress.hide()

        if f.exception() is not None:
            exc = typing.cast(BaseException, f.exception())
            etype, tb = type(exc), exc.__traceback__
            log.error(
                "Error fetching package list",
                exc_info=(etype, exc, tb)
            )
            message_warning(
                "Could not retrieve package list",
                title="Error",
                informative_text=
                    "".join(traceback.format_exception_only(etype, exc)),
                details=
                    "".join(traceback.format_exception(etype, exc, tb)),
                parent=self
            )
            self.__f_pypi_addons = None
            self.__addon_items = None
            return

        config, packages = f.result()
        assert all(isinstance(p, Installable) for p in packages)
        AddonManagerDialog.__packages = packages
        installed = [ep.dist for ep in config.addon_entry_points()
                     if ep.dist is not None]
        items = installable_items(packages, installed)
        core_constraints = {
            r.project_name.casefold(): r
            for r in (Requirement.parse(r) for r in config.core_packages())
        }

        def constrain(item):  # type: (Item) -> Item
            """Include constraint in Installed when in core_constraint"""
            if isinstance(item, Installed):
                name = item.local.project_name.casefold()
                if name in core_constraints:
                    return item._replace(
                        required=True, constraint=core_constraints[name]
                    )
            return item
        self.setItems([constrain(item) for item in items])

    @Slot(object)
    def setItems(self, items):
        # type: (List[Item]) -> None
        """
        Set items

        Parameters
        ----------
        items: List[Items]
        """
        self.addonwidget.setItems(items)

    @Slot(object)
    def addInstallable(self, installable):
        # type: (Installable) -> None
        """
        Add/append a single Installable item.

        Parameters
        ----------
        installable: Installable
        """
        items = self.addonwidget.items()
        if installable.name in {item.installable.name for item in items
                                if item.installable is not None}:
            return
        installed = [ep.dist for ep in self.config().addon_entry_points()]
        new_ = installable_items([installable], filter(None, installed))

        def match(item):
            # type: (Item) -> bool
            if isinstance(item, Available):
                return item.installable.name == installable.name
            elif item.installable is not None:
                return item.installable.name == installable.name
            else:
                return item.local.project_name.lower() == installable.name.lower()

        new = next(filter(match, new_), None)
        assert new is not None
        state = self.addonwidget.itemState()
        self.addonwidget.setItems(items + [new])
        self.addonwidget.setItemState(state)  # restore state

    def __run_add_package_dialog(self):
        self.__add_package_by_name_dialog = dlg = QDialog(
            self, windowTitle="Add add-on by name",
        )
        dlg.setAttribute(Qt.WA_DeleteOnClose)

        vlayout = QVBoxLayout()
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        nameentry = QLineEdit(
            placeholderText="Package name",
            toolTip="Enter a package name as displayed on "
                    "PyPI (capitalization is not important)")
        nameentry.setMinimumWidth(250)
        form.addRow("Name:", nameentry)
        vlayout.addLayout(form)
        buttons = QDialogButtonBox(
            standardButtons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        okb = buttons.button(QDialogButtonBox.Ok)
        okb.setEnabled(False)
        okb.setText("Add")

        def changed(name):
            okb.setEnabled(bool(name))
        nameentry.textChanged.connect(changed)
        vlayout.addWidget(buttons)
        vlayout.setSizeConstraint(QVBoxLayout.SetFixedSize)
        dlg.setLayout(vlayout)
        f = None

        def query():
            nonlocal f
            name = nameentry.text()

            def query_pypi(name):
                # type: (str) -> _QueryResult
                res, = pypi_json_query_project_meta([name])
                inst = None  # type: Optional[Installable]
                if res is not None:
                    inst = installable_from_json_response(res)
                else:
                    inst = None
                return _QueryResult(queryname=name, installable=inst)
            f = self.__executor.submit(query_pypi, name)

            okb.setDisabled(True)

            f.add_done_callback(
                method_queued(self.__on_add_single_query_finish, (object,))
            )
        buttons.accepted.connect(query)
        buttons.rejected.connect(dlg.reject)
        dlg.exec_()

    @Slot(str, str)
    def __show_error_for_query(self, text, error_details):
        message_error(text, title="Error", details=error_details)

    @Slot(object)
    def __on_add_single_query_finish(self, f):
        # type: (Future[_QueryResult]) -> None
        error_text = ""
        error_details = ""
        try:
            result = f.result()
        except Exception:
            log.error("Query error:", exc_info=True)
            error_text = "Failed to query package index"
            error_details = traceback.format_exc()
            pkg = None
        else:
            pkg = result.installable
            if pkg is None:
                error_text = "'{}' not was not found".format(result.queryname)
        dlg = self.__add_package_by_name_dialog
        assert dlg is not None
        if pkg:
            self.addInstallable(pkg)
            dlg.accept()
        else:
            dlg.reject()
            self.__show_error_for_query(error_text, error_details)

    def progressDialog(self):
        # type: () -> QProgressDialog
        if self.__progress is None:
            self.__progress = QProgressDialog(
                self,
                minimum=0, maximum=0,
                labelText=self.tr("Retrieving package list"),
                sizeGripEnabled=False,
                windowTitle="Progress"
            )
            self.__progress.setWindowModality(Qt.WindowModal)
            self.__progress.hide()
            self.__progress.canceled.connect(self.reject)
        return self.__progress

    def done(self, retcode):
        super().done(retcode)
        if self.__thread is not None:
            self.__thread.quit()
            self.__thread.wait(1000)

    def closeEvent(self, event):
        super().closeEvent(event)
        if self.__thread is not None:
            self.__thread.quit()
            self.__thread.wait(1000)

    ADDON_EXTENSIONS = ('.zip', '.whl', '.tar.gz')

    def dragEnterEvent(self, event):
        # type: (QDragEnterEvent) -> None
        """Reimplemented."""
        urls = event.mimeData().urls()
        if any(url.toLocalFile().endswith(self.ADDON_EXTENSIONS)
               for url in urls):
            event.acceptProposedAction()

    def dropEvent(self, event):
        # type: (QDropEvent) -> None
        """
        Reimplemented.

        Allow dropping add-ons (zip or wheel archives) on this dialog to
        install them.
        """
        packages = []
        names = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.endswith(self.ADDON_EXTENSIONS):
                meta = get_meta_from_archive(path) or {}
                name = meta.get("Name", os.path.basename(path))
                vers = meta.get("Version", "")
                summary = meta.get("Summary", "")
                descr = meta.get("Description", "")
                content_type = meta.get("Description-Content-Type", None)
                names.append(name)
                packages.append(
                    Installable(name, vers, summary,
                                descr or summary, path, [path], content_type)
                )

        for installable in packages:
            self.addInstallable(installable)
        items = self.addonwidget.items()
        # lookup items for the new entries
        new_items = [item for item in items if item.installable in packages]
        state_new = [(Install, item) if isinstance(item, Available) else
                     (Upgrade, item) for item in new_items]
        state = self.addonwidget.itemState()
        self.addonwidget.setItemState(state + state_new)
        event.acceptProposedAction()

    def __accepted(self):
        steps = self.addonwidget.itemState()

        if steps:
            # Move all uninstall steps to the front
            steps = sorted(
                steps, key=lambda step: 0 if step[0] == Uninstall else 1
            )
            self.__installer = Installer(steps=steps)
            self.__thread = QThread(self)
            self.__thread.start()

            self.__installer.moveToThread(self.__thread)
            self.__installer.finished.connect(self.__on_installer_finished)
            self.__installer.error.connect(self.__on_installer_error)

            progress = self.progressDialog()

            self.__installer.installStatusChanged.connect(progress.setLabelText)
            progress.show()
            progress.setLabelText("Installing")
            self.__installer.start()

        else:
            self.accept()

    def __on_installer_error(self, command, pkg, retcode, output):
        if self.__progress is not None:
            self.__progress.close()
            self.__progress = None
        message_error(
            "An error occurred while running a subprocess", title="Error",
            informative_text="{} exited with non zero status.".format(command),
            details="".join(output),
            parent=self
        )
        self.reject()

    def __on_installer_finished(self):
        if self.__progress is not None:
            self.__progress.close()
            self.__progress = None

        def message_restart(parent):
            icon = QMessageBox.Information
            buttons = QMessageBox.Ok | QMessageBox.Cancel
            title = 'Information'
            text = 'Orange needs to be restarted for the changes to take effect.'

            msg_box = QMessageBox(icon, title, text, buttons, parent)
            msg_box.setDefaultButton(QMessageBox.Ok)
            msg_box.setInformativeText('Press OK to close Orange now.')

            msg_box.button(QMessageBox.Cancel).setText('Close later')
            return msg_box.exec_()

        if QMessageBox.Ok == message_restart(self):
            self.accept()
            self.parent().close()
        else:
            self.reject()


PYPI_API_JSON = "https://pypi.org/pypi/{name}/json"


def pypi_json_query_project_meta(projects, session=None):
    # type: (List[str], Optional[requests.Session]) -> List[Optional[dict]]
    """
    Parameters
    ----------
    projects : List[str]
        List of project names to query
    session : Optional[requests.Session]
    """
    if session is None:
        session = _session()
    rval = []  # type: List[Optional[dict]]
    for name in projects:
        r = session.get(PYPI_API_JSON.format(name=name))
        if r.status_code != 200:
            rval.append(None)
        else:
            try:
                meta = r.json()
            except json.JSONDecodeError:
                rval.append(None)
            else:
                try:
                    # sanity check
                    installable_from_json_response(meta)
                except (TypeError, KeyError):
                    rval.append(None)
                else:
                    rval.append(meta)
    return rval


def installable_from_json_response(meta):
    # type: (dict) -> Installable
    """
    Extract relevant project meta data from a PyPiJSONRPC response

    Parameters
    ----------
    meta : dict
        JSON response decoded into python native dict.

    Returns
    -------
    installable : Installable
    """
    info = meta["info"]
    name = info["name"]
    version = info.get("version", "0")
    summary = info.get("summary", "")
    description = info.get("description", "")
    content_type = info.get("description_content_type", None)
    package_url = info.get("package_url", "")
    distributions = meta.get("releases", {}).get(version, [])
    release_urls = [ReleaseUrl(r["filename"], url=r["url"], size=r["size"],
                               python_version=r.get("python_version", ""),
                               package_type=r["packagetype"])
                    for r in distributions]

    return Installable(name, version, summary, description, package_url, release_urls,
                       content_type)


def _session(cachedir=None):
    # type: (...) -> requests.Session
    """
    Return a requests.Session instance

    Parameters
    ----------
    cachedir : Optional[str]
        HTTP cache location.

    Returns
    -------
    session : requests.Session
    """
    import cachecontrol.caches
    if cachedir is None:
        cachedir = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
        cachedir = os.path.join(cachedir, "networkcache", "requests")
    session = requests.Session()
    session = cachecontrol.CacheControl(
        session,
        cache=cachecontrol.caches.FileCache(
            directory=cachedir
        )
    )
    return session


def list_available_versions(config, session=None):
    # type: (config.Config, Optional[requests.Session]) -> List[Installable]
    if session is None:
        session = _session()

    defaults = config.addon_defaults_list()

    def getname(item):
        # type: (Dict[str, Any]) -> str
        info = item.get("info", {})
        if not isinstance(info, dict):
            return ""
        name = info.get("name", "")
        assert isinstance(name, str)
        return name

    defaults_names = {getname(a) for a in defaults}

    # query pypi.org for installed add-ons that are not in the defaults
    # list
    installed = [ep.dist for ep in config.addon_entry_points()
                 if ep.dist is not None]
    missing = {dist.project_name.casefold() for dist in installed} - \
              {name.casefold() for name in defaults_names}

    distributions = []
    for p in missing:
        response = session.get(PYPI_API_JSON.format(name=p))
        if response.status_code != 200:
            continue
        distributions.append(response.json())

    packages = []
    for addon in defaults + distributions:
        try:
            packages.append(installable_from_json_response(addon))
        except (TypeError, KeyError):
            continue  # skip invalid packages

    return packages


def installable_items(pypipackages, installed=[]):
    # type: (Iterable[Installable], Iterable[Distribution]) -> List[Item]
    """
    Return a list of installable items.

    Parameters
    ----------
    pypipackages : list of Installable
    installed : list of pkg_resources.Distribution
    """

    dists = {dist.project_name: dist for dist in installed}
    packages = {pkg.name: pkg for pkg in pypipackages}

    # For every pypi available distribution not listed by
    # `installed`, check if it is actually already installed.
    ws = pkg_resources.WorkingSet()
    for pkg_name in set(packages.keys()).difference(set(dists.keys())):
        try:
            d = ws.find(Requirement.parse(pkg_name))
        except pkg_resources.ResolutionError:
            pass
        except ValueError:
            # Requirements.parse error ?
            pass
        else:
            if d is not None:
                dists[d.project_name] = d

    project_names = unique(
        itertools.chain(packages.keys(), dists.keys())
    )

    items = []  # type: List[Item]
    for name in project_names:
        if name in dists and name in packages:
            item = Installed(packages[name], dists[name])
        elif name in dists:
            item = Installed(None, dists[name])
        elif name in packages:
            item = Available(packages[name])
        else:
            assert False
        items.append(item)
    return items


def have_install_permissions():
    """Check if we can create a file in the site-packages folder.
    This works on a Win7 miniconda install, where os.access did not. """
    try:
        fn = os.path.join(sysconfig.get_path("purelib"), "test_write_" + str(os.getpid()))
        with open(fn, "w"):
            pass
        os.remove(fn)
        return True
    except PermissionError:
        return False


class Command(enum.Enum):
    Install = "Install"
    Upgrade = "Upgrade"
    Uninstall = "Uninstall"


Install = Command.Install
Upgrade = Command.Upgrade
Uninstall = Command.Uninstall

Action = Tuple[Command, Item]


class CommandFailed(Exception):
    def __init__(self, cmd, retcode, output):
        if not isinstance(cmd, str):
            cmd = " ".join(map(shlex.quote, cmd))
        self.cmd = cmd
        self.retcode = retcode
        self.output = output


class Installer(QObject):
    installStatusChanged = Signal(str)
    started = Signal()
    finished = Signal()
    error = Signal(str, object, int, list)

    def __init__(self, parent=None, steps=[]):
        super().__init__(parent)
        self.__interupt = False
        self.__queue = deque(steps)
        self.__statusMessage = ""
        self.pip = PipInstaller()
        self.conda = CondaInstaller()

    def start(self):
        QTimer.singleShot(0, self._next)

    def interupt(self):
        self.__interupt = True

    def setStatusMessage(self, message):
        if self.__statusMessage != message:
            self.__statusMessage = message
            self.installStatusChanged.emit(message)

    @Slot()
    def _next(self):
        command, pkg = self.__queue.popleft()

        try:
            if command == Install:
                self.setStatusMessage(
                    "Installing {}".format(pkg.installable.name))
                if self.conda:
                    self.conda.install(pkg.installable, raise_on_fail=False)
                self.pip.install(pkg.installable)
            elif command == Upgrade:
                self.setStatusMessage(
                    "Upgrading {}".format(pkg.installable.name))
                if self.conda:
                    self.conda.upgrade(pkg.installable, raise_on_fail=False)
                self.pip.upgrade(pkg.installable)
            elif command == Uninstall:
                self.setStatusMessage(
                    "Uninstalling {}".format(pkg.local.project_name))
                if self.conda:
                    try:
                        self.conda.uninstall(pkg.local, raise_on_fail=True)
                    except CommandFailed:
                        self.pip.uninstall(pkg.local)
                else:
                    self.pip.uninstall(pkg.local)
        except CommandFailed as ex:
            self.error.emit(
                "Command failed: python {}".format(ex.cmd),
                pkg, ex.retcode, ex.output
            )
            return

        if self.__queue:
            QTimer.singleShot(0, self._next)
        else:
            self.finished.emit()


class PipInstaller:

    def __init__(self):
        arguments = QSettings().value('add-ons/pip-install-arguments', '', type=str)
        self.arguments = shlex.split(arguments)

    def install(self, pkg):
        # type: (Installable) -> None
        constraints = config.default.core_packages()
        constraints = ("\n".join(constraints))
        with temp_named_file(constraints, suffix=".txt") as cfile:
            cmd = [
                "python", "-m", "pip",  "install",
                      "--constraint", cfile,
            ] + self.arguments

            if pkg.package_url.startswith(("http://", "https://")):
                cmd.append(pkg.name)
            else:
                # Package url is path to the (local) wheel
                cmd.append(pkg.package_url)

            run_command(cmd)

    def upgrade(self, package):
        constraints = config.default.core_packages()
        constraints = ("\n".join(constraints))
        with temp_named_file(constraints, suffix=".txt") as cfile:
            cmd = [
                "python", "-m", "pip", "install",
                    "--upgrade", "--upgrade-strategy=only-if-needed",
                    "--constraint", cfile,
            ] + self.arguments
            if package.package_url.startswith(("http://", "https://")):
                cmd.append(package.name)
            else:
                cmd.append(package.package_url)
            run_command(cmd)

    def uninstall(self, dist):
        cmd = ["python", "-m", "pip", "uninstall", "--yes", dist.project_name]
        run_command(cmd)


class CondaInstaller:
    def __init__(self):
        enabled = QSettings().value('add-ons/allow-conda',
                                    True, type=bool)
        if enabled:
            self.conda = self._find_conda()
        else:
            self.conda = None

    def _find_conda(self):
        executable = sys.executable
        bin = os.path.dirname(executable)

        # posix
        conda = os.path.join(bin, "conda")
        if os.path.exists(conda):
            return conda

        # windows
        conda = os.path.join(bin, "Scripts", "conda.bat")
        if os.path.exists(conda):
            # "activate" conda environment orange is running in
            os.environ["CONDA_PREFIX"] = bin
            os.environ["CONDA_DEFAULT_ENV"] = bin
            return conda

    def install(self, pkg, raise_on_fail=False):
        cmd = [self.conda, "install", "--yes", "--quiet",
               self._normalize(pkg.name)]
        run_command(cmd, raise_on_fail=raise_on_fail)

    def upgrade(self, pkg, raise_on_fail=False):
        cmd = [self.conda, "upgrade", "--yes", "--quiet",
               self._normalize(pkg.name)]
        run_command(cmd, raise_on_fail=raise_on_fail)

    def uninstall(self, dist, raise_on_fail=False):
        cmd = [self.conda, "uninstall", "--yes",
               self._normalize(dist.project_name)]
        run_command(cmd, raise_on_fail=raise_on_fail)

    def _normalize(self, name):
        # Conda 4.3.30 is inconsistent, upgrade command is case sensitive
        # while install and uninstall are not. We assume that all conda
        # package names are lowercase which fixes the problems (for now)
        return name.lower()

    def __bool__(self):
        return bool(self.conda)


def run_command(command, raise_on_fail=True, **kwargs):
    # type: (List[str], bool, Any) -> Tuple[int, List[AnyStr]]
    """
    Run command in a subprocess.

    Return `process` return code and output once it completes.
    """
    log.info("Running %s", " ".join(command))

    if command[0] == "python":
        process = python_process(command[1:], **kwargs)
    else:
        process = create_process(command, **kwargs)

    output = []
    while process.poll() is None:
        try:
            line = process.stdout.readline()
        except IOError as ex:
            if ex.errno != errno.EINTR:
                raise
        else:
            output.append(line)
            print(line, end="")
    # Read remaining output if any
    line = process.stdout.read()
    if line:
        output.append(line)
        print(line, end="")

    if process.returncode != 0:
        log.info("Command %s failed with %s",
                 " ".join(command), process.returncode)
        log.debug("Output:\n%s", "\n".join(output))
        if raise_on_fail:
            raise CommandFailed(command, process.returncode, output)

    return process.returncode, output


def main(argv=None):  # noqa
    import argparse
    from AnyQt.QtWidgets import QApplication
    app = QApplication(argv if argv is not None else [])
    argv = app.arguments()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", metavar="CLASSNAME",
        default="orangecanvas.config.default",
        help="The configuration namespace to use"
    )
    args = parser.parse_args(argv[1:])
    config_ = name_lookup(args.config)
    config_ = config_()
    config_.init()
    config.set_default(config_)
    dlg = AddonManagerDialog()
    dlg.start(config_)
    dlg.show()
    dlg.raise_()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv))

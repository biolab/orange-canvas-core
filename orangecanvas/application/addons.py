import types
import tempfile
import enum
import sys
import sysconfig
import os
import logging
import errno
import shlex
import subprocess
import itertools
import xmlrpc.client
import json
import traceback
import urllib.request

from concurrent.futures import ThreadPoolExecutor, Future
from collections import deque
from xml.sax.saxutils import escape

from typing import (
    List, Dict, Any, Optional, Union, Tuple, NamedTuple, Callable, AnyStr
)

import requests
import pkg_resources

import packaging.version
import packaging.requirements

import docutils.core
import docutils.utils

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

from orangecanvas.utils import unique, name_lookup
from ..gui.utils import message_warning, message_critical as message_error
from ..help.manager import get_dist_meta, trim, parse_meta

from .. import config

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
            ("release_urls", List['ReleaseUrl'])
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
            v1 = packaging.version.parse(dist.version)
            v2 = packaging.version.parse(inst.version)
        except ValueError:
            return False

        if item.constraint is not None and str(v2) not in item.constraint:
            return False
        else:
            return v1 < v2


def get_meta_from_archive(path):
    """Return project name, version and summary extracted from
    sdist or wheel metadata in a ZIP or tar.gz archive, or None if metadata
    can't be found."""

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
        meta = parse_meta(meta)
        return [meta.get(key, '')
                for key in ('Name', 'Version', 'Description', 'Summary')]


HasConstraintRole = Qt.UserRole + 0xf45


class PluginsModel(QStandardItemModel):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.setHorizontalHeaderLabels(
            ["", self.tr("Name"), self.tr("Version"), self.tr("Action")]
        )

    @staticmethod
    def createRow(item):
        # type: (Item) -> List[QStandardItem]
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

        item1 = QStandardItem()
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
            version = "{} < {}".format(dist.version, ins.version)

        item3 = QStandardItem(version)
        item3.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

        item4 = QStandardItem()
        item4.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

        return [item1, item2, item3, item4]


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
        # type: (Qt.CheckeState, QModelIndex) -> Qt.CheckState
        """
        Return the next check state for index.
        """
        constraint = index.data(HasConstraintRole)
        flags = index.flags()
        if flags & Qt.ItemIsUserTristate and constraint:
            return Qt.PartiallyChecked if state == Qt.Checked else Qt.Checked
        elif flags & Qt.ItemIsUserTristate:
            return (state + 1) % 3
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
        steps = []
        for i in range(self.__model.rowCount()):
            modelitem = self.__model.item(i, 0)
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
        model = self.__model
        if model.rowCount() == 0:
            return

        for row in range(model.rowCount()):
            modelitem = model.item(row, 0)  # type: QStandardItem
            item = modelitem.data(Qt.UserRole)  # type: Item
            # Find the action command in the steps list for the item
            cmd = -1
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

    def __selected_row(self):
        indices = self.__view.selectedIndexes()
        if indices:
            proxy = self.__view.model()
            indices = [proxy.mapToSource(index) for index in indices]
            return indices[0].row()
        else:
            return -1

    def __data_changed(self, topleft, bottomright):
        rows = range(topleft.row(), bottomright.row() + 1)
        for i in rows:
            modelitem = self.__model.item(i, 0)
            actionitem = self.__model.item(i, 3)
            item = modelitem.data(Qt.UserRole)

            state = modelitem.checkState()
            flags = modelitem.flags()

            if flags & Qt.ItemIsUserTristate and state == Qt.Checked:
                actionitem.setText("Update")
            elif isinstance(item, Available) and state == Qt.Checked:
                actionitem.setText("Install")
            elif isinstance(item, Installed) and state == Qt.Unchecked:
                actionitem.setText("Uninstall")
            else:
                actionitem.setText("")
        self.stateChanged.emit()

    def __update_details(self):
        index = self.__selected_row()
        if index == -1:
            self.__details.setText("")
        else:
            item = self.__model.item(index, 1)
            item = item.data(Qt.UserRole)
            assert isinstance(item, (Installed, Available))
            text = self._detailed_text(item)
            self.__details.setText(text)

    def _detailed_text(self, item):
        # type: (Item) -> str
        if isinstance(item, Installed):
            remote, dist = item.installable, item.local
            if remote is None:
                meta = get_dist_meta(dist)
                description = meta.get("Description", "") or \
                              meta.get('Summary', "")
            else:
                description = remote.description
        else:
            description = item.installable.description

        try:
            html = docutils.core.publish_string(
                trim(description),
                writer_name="html",
                settings_overrides={
                    "output-encoding": "utf-8",
                }
            ).decode("utf-8")
        except docutils.utils.SystemMessage:
            html = "<pre>{}<pre>".format(escape(description))
        except Exception:
            html = "<pre>{}<pre>".format(escape(description))
        return html

    def sizeHint(self):
        return QSize(480, 420)


def method_queued(method, sig, conntype=Qt.QueuedConnection):
    # type: (types.MethodType, Tuple[type, ...], int) -> Callable[[], bool]
    name = method.__name__
    obj = method.__self__  # type: QObject
    assert isinstance(obj, QObject)

    def call(*args):
        args = [Q_ARG(atype, arg) for atype, arg in zip(sig, args)]
        return QMetaObject.invokeMethod(obj, name, conntype, *args)

    return call


class _QueryResult(types.SimpleNamespace):
    queryname = ...    # type: str
    installable = ...  # type: Optional[Installable]


class AddonManagerDialog(QDialog):
    """
    A add-on manager dialog.
    """
    #: cached packages list.
    __packages = None  # type: List[Installable]
    __f_pypi_addons = None
    __config = None

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
        if self.__config is None:
            return config.default
        else:
            return self.__config

    @Slot()
    def start(self, config):
        # type: (config.Config) -> None
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
            installed = [ep.dist for ep in config.addon_entry_points()]
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
        # type: (Future[Tuple[config.Config, List[Installable]]]) -> None
        assert f.done()
        if self.__progress is not None:
            self.__progress.hide()

        if f.exception():
            exc = f.exception()
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
        installed = [ep.dist for ep in config.addon_entry_points()]
        items = installable_items(packages, installed)
        core_constraints = {
            r.project_name.casefold(): r
            for r in (Requirement.parse(r) for r in config.core_packages())
        }

        def f(item):  # type: (Item) -> Item
            """Include constraint in Installed when in core_constraint"""
            if isinstance(item, Installed):
                name = item.local.project_name.casefold()
                if name in core_constraints:
                    return item._replace(
                        required=True, constraint=core_constraints[name]
                    )
            return item
        self.setItems([f(item) for item in items])

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
        new_ = installable_items([installable], installed)
        new = next(
            filter(
                lambda item: item.installable.name == installable.name,
                new_
            ),
            None
        )
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
                res = pypi_json_query_project_meta([name])
                assert len(res) == 1
                r = res[0]
                if r is not None:
                    r = installable_from_json_response(r)
                return _QueryResult(queryname=name, installable=r)
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
                name, vers, summary, descr = (get_meta_from_archive(path) or
                                              (os.path.basename(path), '', '', ''))
                names.append(name)
                packages.append(
                    Installable(name, vers, summary,
                                descr or summary, path, [path]))

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


class SafeTransport(xmlrpc.client.SafeTransport):
    def __init__(self, use_datetime=0, timeout=None):
        super().__init__(use_datetime)
        self._timeout = timeout

    def make_connection(self, *args, **kwargs):
        conn = super().make_connection(*args, **kwargs)
        if self._timeout is not None:
            conn.timeout = self._timeout
        return conn


PYPI_API_JSON = "https://pypi.org/pypi/{name}/json"
PYPI_API_XMLRPC = "https://pypi.org/pypi"


def pypi_search(spec, timeout=None):
    """
    Search package distributions available on PyPi using PyPiXMLRPC.
    """
    pypi = xmlrpc.client.ServerProxy(
        PYPI_API_XMLRPC,
        transport=SafeTransport(timeout=timeout)
    )
    # pypi search
    spec = {key: [v] if isinstance(v, str) else v
            for key, v in spec.items()}
    _spec = {}
    for key, values in spec.items():
        if isinstance(values, str):
            _spec[key] = values
        elif key == "keywords" and len(values) > 1:
            _spec[key] = [values[0]]
        else:
            _spec[key] = values
    addons = pypi.search(_spec, 'and')
    addons = [item["name"] for item in addons if "name" in item]
    metas_ = pypi_json_query_project_meta(addons)

    # post filter on multiple keywords
    def matches(meta, spec):
        # type: (Dict[str, Any], Dict[str, List[str]]) -> bool
        def match_list(meta, query):
            # type: (List[str], List[str]) -> bool
            meta = {s.casefold() for s in meta}
            return all(q.casefold() in meta for q in query)

        def match_string(meta, query):
            # type: (str, List[str]) -> bool
            meta = meta.casefold()
            return all(q.casefold() in meta for q in query)

        for key, query in spec.items():
            value = meta.get(key, None)
            if isinstance(value, str) and not match_string(value, query):
                return False
            elif isinstance(value, list) and not match_list(value, query):
                return False
        return True

    metas = []
    for meta in metas_:
        if meta is not None:
            if matches(meta["info"], spec):
                metas.append(meta)
    return [installable_from_json_response(m) for m in metas]


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
    rval = []
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
    package_url = info.get("package_url", "")
    distributions = meta.get("releases", {}).get(version, [])
    release_urls = [ReleaseUrl(r["filename"], url=r["url"], size=r["size"],
                               python_version=r.get("python_version", ""),
                               package_type=r["packagetype"])
                    for r in distributions]

    return Installable(name, version, summary, description, package_url, release_urls)


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
    defaults_names = {a.get("info", {}).get("name", "") for a in defaults}

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
            p = installable_from_json_response(addon)
        except (TypeError, KeyError):
            continue  # skip invalid packages
        else:
            packages.append(p)

    return packages


def installable_items(pypipackages, installed=[]):
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

    items = []
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


def _env_with_proxies():
    """
    Return system environment with proxies obtained from urllib so that
    they can be used with pip.
    """
    proxies = urllib.request.getproxies()
    env = dict(os.environ)
    if "http" in proxies:
        env["HTTP_PROXY"] = proxies["http"]
    if "https" in proxies:
        env["HTTPS_PROXY"] = proxies["https"]
    return env


class Command(enum.Enum):
    Install = "Install"
    Upgrade = "Upgrade"
    Uninstall = "Uninstall"


Install, Upgrade, Uninstall = Command

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
        with tempfile.NamedTemporaryFile(
                mode="w+t", suffix=".txt", encoding="utf-8") as cfile:
            cfile.write(constraints)
            cfile.flush()
            cmd = [
                "python", "-m", "pip",  "install",
                      "--constraint", cfile.name,
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
        with tempfile.NamedTemporaryFile(
                mode="w+t", suffix=".txt", encoding="utf-8") as cfile:
            cfile.write(constraints)
            cfile.flush()
            cmd = [
                "python", "-m", "pip", "install",
                    "--upgrade", "--upgrade-strategy=only-if-needed",
                    "--constraint", cfile.name,
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
        enabled = QSettings().value('add-ons/allow-conda-experimental',
                                    False, type=bool)
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


def python_process(args, script_name=None, **kwargs):
    # type: (List[str], Optional[str], Any) -> subprocess.Popen
    """
    Run a `sys.executable` in a subprocess with `args`.
    """
    executable = sys.executable
    if os.name == "nt" and os.path.basename(executable) == "pythonw.exe":
        # Don't run the script with a 'gui' (detached) process.
        dirname = os.path.dirname(executable)
        executable = os.path.join(dirname, "python.exe")

    if script_name is not None:
        script = script_name
    else:
        script = executable

    return create_process(
        [script] + args,
        executable=executable,
        **kwargs
    )


def create_process(cmd, executable=None, **kwargs):
    # type: (List[str], Optional[str], Any) -> subprocess.Popen
    if hasattr(subprocess, "STARTUPINFO"):
        # do not open a new console window for command on windows
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs["startupinfo"] = startupinfo

    return subprocess.Popen(
        cmd,
        executable=executable,
        cwd=None,
        env=_env_with_proxies(),
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        bufsize=-1,
        universal_newlines=True,
        **kwargs
    )


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

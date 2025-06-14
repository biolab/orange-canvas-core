"""
User settings/preference dialog
===============================

"""
import sys
import logging
import warnings
from functools import cmp_to_key
from collections import namedtuple

from AnyQt.QtWidgets import (
    QWidget, QMainWindow, QComboBox, QCheckBox, QListView, QTabWidget,
    QToolBar, QAction, QStackedWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QSizePolicy, QDialogButtonBox, QLineEdit, QLabel,
    QStyleFactory, QLayout)
from AnyQt.QtGui import QStandardItemModel, QStandardItem
from AnyQt.QtCore import (
    Qt, QEventLoop, QAbstractItemModel, QModelIndex, QSettings,
    Property,
    Signal)

from .. import config
from ..localization import get_languages
from ..utils.settings import SettingChangedEvent
from ..utils.propertybindings import (
    AbstractBoundProperty, PropertyBinding, BindingManager
)

log = logging.getLogger(__name__)


def refresh_proxies():
    from orangecanvas.main import fix_set_proxy_env
    fix_set_proxy_env()


class UserDefaultsPropertyBinding(AbstractBoundProperty):
    """
    A Property binding for a setting in a
    :class:`orangecanvas.utility.settings.Settings` instance.

    """
    def __init__(self, obj, propertyName, parent=None):
        super().__init__(obj, propertyName, parent)

        obj.installEventFilter(self)

    def get(self):
        return self.obj.get(self.propertyName)

    def set(self, value):
        self.obj[self.propertyName] = value

    def eventFilter(self, obj, event):
        if event.type() == SettingChangedEvent.SettingChanged and \
                event.key() == self.propertyName:
            self.notifyChanged()

        return super().eventFilter(obj, event)


class UserSettingsModel(QAbstractItemModel):
    """
    An Item Model for user settings presenting a list of
    key, setting value entries along with it's status and type.

    """
    def __init__(self, parent=None, settings=None):
        super().__init__(parent)

        self.__settings = settings
        self.__headers = ["Name", "Status", "Type", "Value"]

    def setSettings(self, settings):
        if self.__settings != settings:
            self.__settings = settings
            self.reset()

    def settings(self):
        return self.__settings

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        elif self.__settings:
            return len(self.__settings)
        else:
            return 0

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        else:
            return len(self.__headers)

    def parent(self, index):
        return QModelIndex()

    def index(self, row, column=0, parent=QModelIndex()):
        if parent.isValid() or \
                column < 0 or column >= self.columnCount() or \
                row < 0 or row >= self.rowCount():
            return QModelIndex()

        return self.createIndex(row, column, row)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if section >= 0 and section < 4 and orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return self.__headers[section]

        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.DisplayRole):
        if self._valid(index):
            key = self._keyFromIndex(index)
            column = index.column()
            if role == Qt.DisplayRole:
                if column == 0:
                    return key
                elif column == 1:
                    default = self.__settings.isdefault(key)
                    return "Default" if default else "User"
                elif column == 2:
                    return type(self.__settings.get(key)).__name__
                elif column == 3:
                    return self.__settings.get(key)
                return self

        return None

    def flags(self, index):
        if self._valid(index):
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
            if index.column() == 3:
                return Qt.ItemIsEditable | flags
            else:
                return flags
        return Qt.NoItemFlags

    def setData(self, index, value, role=Qt.EditRole):
        if self._valid(index) and index.column() == 3:
            key = self._keyFromIndex(index)
            try:
                self.__settings[key] = value
            except (TypeError, ValueError) as ex:
                log.error("Failed to set value (%r) for key %r", value, key,
                          exc_info=True)
            else:
                self.dataChanged.emit(index, index)
                return True

        return False

    def _valid(self, index):
        row = index.row()
        return row >= 0 and row < self.rowCount()

    def _keyFromIndex(self, index):
        row = index.row()
        return list(self.__settings.keys())[row]


def container_widget_helper(orientation=Qt.Vertical, spacing=None, margin=0):
    widget = QWidget()
    if orientation == Qt.Vertical:
        layout = QVBoxLayout()
        widget.setSizePolicy(QSizePolicy.Fixed,
                             QSizePolicy.MinimumExpanding)
    else:
        layout = QHBoxLayout()

    if spacing is not None:
        layout.setSpacing(spacing)

    if margin is not None:
        layout.setContentsMargins(0, 0, 0, 0)

    widget.setLayout(layout)

    return widget


_State = namedtuple("_State", ["visible", "position"])


class FormLayout(QFormLayout):
    """
    When adding a row to a QFormLayout, wherein the field is a layout
    (or a widget with a layout), the label's height is too large to look pretty.
    This subclass sets the label a fixed height to match the first item in
    the layout.
    """
    def addRow(self, *args):
        if len(args) != 2:
            return super().addRow(*args)
        label, field = args
        if not isinstance(field, QLayout) and field.layout() is None:
            return super().addRow(label, field)

        layout = field if isinstance(field, QLayout) else field.layout()
        widget = layout.itemAt(0).widget()
        height = widget.sizeHint().height()
        if isinstance(label, str):
            label = QLabel(label)
        label.setFixedHeight(height)
        return super().addRow(label, field)


class UserSettingsDialog(QMainWindow):
    """
    A User Settings/Defaults dialog.

    """
    MAC_UNIFIED = True

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.setWindowFlags(Qt.Dialog)
        self.setWindowModality(Qt.ApplicationModal)

        self.layout().setSizeConstraint(QVBoxLayout.SetFixedSize)

        self.__macUnified = sys.platform == "darwin" and self.MAC_UNIFIED
        self._manager = BindingManager(self,
                                       submitPolicy=BindingManager.AutoSubmit)

        self.__loop = None

        self.__settings = config.settings()
        self.__setupUi()

    def __setupUi(self):
        """Set up the UI.
        """
        if self.__macUnified:
            self.tab = QToolBar(
                floatable=False, movable=False, allowedAreas=Qt.TopToolBarArea,
            )
            self.addToolBar(Qt.TopToolBarArea, self.tab)
            self.setUnifiedTitleAndToolBarOnMac(True)

            # This does not seem to work
            self.setWindowFlags(self.windowFlags() & \
                                ~Qt.MacWindowToolBarButtonHint)

            self.tab.actionTriggered[QAction].connect(
                self.__macOnToolBarAction
            )

            central = QStackedWidget()

            central.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        else:
            self.tab = central = QTabWidget(self)

        # Add a close button to the bottom of the dialog
        # (to satisfy GNOME 3 which shows the dialog  without a title bar).
        container = container_widget_helper()
        container.layout().addWidget(central)
        buttonbox = QDialogButtonBox(QDialogButtonBox.Close)
        buttonbox.rejected.connect(self.close)
        container.layout().addWidget(buttonbox)

        self.setCentralWidget(container)

        self.stack = central

        # General Tab
        tab = QWidget()
        self.addTab(tab, self.tr("General"),
                    toolTip=self.tr("General Options"))

        form = FormLayout()
        tab.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        languages = get_languages()
        if languages:
            langlay = QHBoxLayout()
            label = QLabel(
                "Changes will take effect on next application startup.")
            label.setHidden(True)

            cm_lang = QComboBox(
                objectName="combo-language",
                toolTip=self.tr("Select the application language.")
            )
            cm_lang.addItems(list(languages))
            self.bind(cm_lang, "currentText", "application/language")
            cm_lang.currentTextChanged.connect(lambda: label.setHidden(False))

            langlay.addWidget(cm_lang)
            langlay.addWidget(label)
            form.addRow(self.tr("Language"), langlay)

        nodes = QWidget(self, objectName="nodes")
        nodes.setLayout(QVBoxLayout())
        nodes.layout().setContentsMargins(0, 0, 0, 0)

        cb_anim = QCheckBox(
            self.tr("Enable node animations"),
            objectName="enable-node-animations",
            toolTip=self.tr("Enable shadow and ping animations for nodes "
                            "in the workflow.")
        )
        cb_anchors = QCheckBox(
            self.tr("Open anchors on hover"),
            objectName="open-anchors-on-hover",
            toolTip=self.tr(
                "Open/expand node anchors on mouse hover (if unchecked the "
                "anchors are expanded when Shift key is pressed)."
            ),
        )
        self.bind(cb_anim, "checked", "schemeedit/enable-node-animations")
        self.bind(cb_anchors, "checked", "schemeedit/open-anchors-on-hover")
        nodes.layout().addWidget(cb_anim)
        nodes.layout().addWidget(cb_anchors)
        form.addRow(self.tr("Nodes"), nodes)

        links = QWidget(self, objectName="links")
        links.setLayout(QVBoxLayout())
        links.layout().setContentsMargins(0, 0, 0, 0)

        cb_show = QCheckBox(
            self.tr("Show channel names between widgets"),
            objectName="show-channel-names",
            toolTip=self.tr("Show source and sink channel names "
                            "over the links.")
        )

        self.bind(cb_show, "checked", "schemeedit/show-channel-names")

        links.layout().addWidget(cb_show)

        form.addRow(self.tr("Links"), links)

        quickmenu = QWidget(self, objectName="quickmenu-options")
        quickmenu.setLayout(QVBoxLayout())
        quickmenu.layout().setContentsMargins(0, 0, 0, 0)

        cb1 = QCheckBox(self.tr("Open on double click"),
                        toolTip=self.tr("Open quick menu on a double click "
                                        "on an empty spot in the canvas"))

        cb2 = QCheckBox(self.tr("Open on right click"),
                        toolTip=self.tr("Open quick menu on a right click "
                                        "on an empty spot in the canvas"))

        cb3 = QCheckBox(self.tr("Open on space key press"),
                        toolTip=self.tr("Open quick menu on Space key press "
                                        "while the mouse is hovering over the canvas."))

        cb4 = QCheckBox(self.tr("Open on any key press"),
                        toolTip=self.tr("Open quick menu on any key press "
                                        "while the mouse is hovering over the canvas."))

        cb5 = QCheckBox(self.tr("Show categories"),
                        toolTip=self.tr("In addition to searching, allow filtering "
                                        "by categories."))

        self.bind(cb1, "checked", "quickmenu/trigger-on-double-click")
        self.bind(cb2, "checked", "quickmenu/trigger-on-right-click")
        self.bind(cb3, "checked", "quickmenu/trigger-on-space-key")
        self.bind(cb4, "checked", "quickmenu/trigger-on-any-key")
        self.bind(cb5, "checked", "quickmenu/show-categories")

        quickmenu.layout().addWidget(cb1)
        quickmenu.layout().addWidget(cb2)
        quickmenu.layout().addWidget(cb3)
        quickmenu.layout().addWidget(cb4)
        quickmenu.layout().addWidget(cb5)

        form.addRow(self.tr("Quick menu"), quickmenu)

        startup = QWidget(self, objectName="startup-group")
        startup.setLayout(QVBoxLayout())
        startup.layout().setContentsMargins(0, 0, 0, 0)

        cb_splash = QCheckBox(self.tr("Show splash screen"), self,
                              objectName="show-splash-screen")

        cb_welcome = QCheckBox(self.tr("Show welcome screen"), self,
                               objectName="show-welcome-screen")

        cb_crash = QCheckBox(self.tr("Load crashed scratch workflows"), self,
                             objectName="load-crashed-workflows")

        self.bind(cb_splash, "checked", "startup/show-splash-screen")
        self.bind(cb_welcome, "checked", "startup/show-welcome-screen")
        self.bind(cb_crash, "checked", "startup/load-crashed-workflows")

        startup.layout().addWidget(cb_splash)
        startup.layout().addWidget(cb_welcome)
        startup.layout().addWidget(cb_crash)

        form.addRow(self.tr("On startup"), startup)

        toolbox = QWidget(self, objectName="toolbox-group")
        toolbox.setLayout(QVBoxLayout())
        toolbox.layout().setContentsMargins(0, 0, 0, 0)

        exclusive = QCheckBox(self.tr("Only one tab can be open at a time"))

        self.bind(exclusive, "checked", "mainwindow/toolbox-dock-exclusive")

        toolbox.layout().addWidget(exclusive)

        form.addRow(self.tr("Tool box"), toolbox)
        tab.setLayout(form)

        # Style tab
        tab = StyleConfigWidget()
        self.addTab(tab, self.tr("&Style"), toolTip="Application style")
        self.bind(tab, "selectedStyle_", "application-style/style-name")
        self.bind(tab, "selectedPalette_", "application-style/palette")

        # Output Tab
        tab = QWidget()
        self.addTab(tab, self.tr("Output"),
                    toolTip="Output Redirection")

        form = FormLayout()

        combo = QComboBox()
        combo.addItems([self.tr("Critical"),
                        self.tr("Error"),
                        self.tr("Warn"),
                        self.tr("Info"),
                        self.tr("Debug")])
        self.bind(combo, "currentIndex", "logging/level")
        form.addRow(self.tr("Logging"), combo)

        box = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        cb1 = QCheckBox(self.tr("Open in external browser"),
                        objectName="open-in-external-browser")
        self.bind(cb1, "checked", "help/open-in-external-browser")
        layout.addWidget(cb1)
        box.setLayout(layout)
        form.addRow(self.tr("Help window"), box)

        tab.setLayout(form)

        # Categories Tab
        tab = QWidget()
        layout = QVBoxLayout()
        view = QListView(
            editTriggers=QListView.NoEditTriggers
        )
        from .. import registry
        reg = registry.global_registry()
        model = QStandardItemModel()
        settings = QSettings()
        for cat in reg.categories():
            item = QStandardItem()
            item.setText(cat.name)
            item.setCheckable(True)
            visible, _ = category_state(cat, settings)
            item.setCheckState(Qt.Checked if visible else Qt.Unchecked)
            model.appendRow([item])

        view.setModel(model)
        layout.addWidget(view)
        tab.setLayout(layout)
        model.itemChanged.connect(
            lambda item:
                save_category_state(
                    reg.category(str(item.text())),
                    _State(item.checkState() == Qt.Checked, -1),
                    settings
                )
        )

        self.addTab(tab, "Categories")

        # Add-ons Tab
        tab = QWidget()
        self.addTab(tab, self.tr("Add-ons"),
                    toolTip="Settings related to add-on installation")

        form = FormLayout()
        conda = QWidget(self, objectName="conda-group")
        conda.setLayout(QVBoxLayout())
        conda.layout().setContentsMargins(0, 0, 0, 0)

        cb_conda_install = QCheckBox(self.tr("Install add-ons with conda"), self,
                                     objectName="allow-conda")
        self.bind(cb_conda_install, "checked", "add-ons/allow-conda")
        conda.layout().addWidget(cb_conda_install)

        form.addRow(self.tr("Conda"), conda)

        form.addRow(self.tr("Pip"), QLabel("Pip install arguments:"))
        line_edit_pip = QLineEdit()
        self.bind(line_edit_pip, "text", "add-ons/pip-install-arguments")
        form.addRow("", line_edit_pip)

        tab.setLayout(form)

        # Network Tab
        tab = QWidget()
        self.addTab(tab, self.tr("Network"),
                    toolTip="Settings related to networking")

        form = FormLayout()
        line_edit_http_proxy = QLineEdit()
        self.bind(line_edit_http_proxy, "text", "network/http-proxy")
        form.addRow("HTTP proxy:", line_edit_http_proxy)
        line_edit_https_proxy = QLineEdit()
        self.bind(line_edit_https_proxy, "text", "network/https-proxy")
        form.addRow("HTTPS proxy:", line_edit_https_proxy)
        cb_use_certs = QCheckBox()
        self.bind(cb_use_certs, "checked", "network/use-certs")
        form.addRow("Use system certificates:", cb_use_certs)
        tab.setLayout(form)

        if self.__macUnified:
            # Need some sensible size otherwise mac unified toolbar 'takes'
            # the space that should be used for layout of the contents
            self.adjustSize()

    def addTab(self, widget, text, toolTip=None, icon=None):
        if self.__macUnified:
            action = QAction(text, self)

            if toolTip:
                action.setToolTip(toolTip)

            if icon:
                action.setIcon(toolTip)
            action.setData(len(self.tab.actions()))

            self.tab.addAction(action)

            self.stack.addWidget(widget)
        else:
            i = self.tab.addTab(widget, text)

            if toolTip:
                self.tab.setTabToolTip(i, toolTip)

            if icon:
                self.tab.setTabIcon(i, icon)

    def setCurrentIndex(self, index: int):
        if self.__macUnified:
            self.stack.setCurrentIndex(index)
        else:
            self.tab.setCurrentIndex(index)

    def widget(self, index):
        if self.__macUnified:
            return self.stack.widget(index)
        else:
            return self.tab.widget(index)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            self.deleteLater()

    def bind(self, source, source_property, key, transformer=None):
        target = UserDefaultsPropertyBinding(self.__settings, key)
        source = PropertyBinding(source, source_property)
        source.set(target.get())

        self._manager.bind(target, source)

    def commit(self):
        self._manager.commit()

    def revert(self):
        self._manager.revert()

    def reset(self):
        for target, source in self._manager.bindings():
            try:
                source.reset()
            except NotImplementedError:
                # Cannot reset.
                pass
            except Exception:
                log.error("Error reseting %r", source.propertyName,
                          exc_info=True)

    def exec(self):
        self.__loop = QEventLoop()
        self.show()
        status = self.__loop.exec()
        self.__loop = None
        refresh_proxies()
        return status

    def exec_(self, *args, **kwargs):
        warnings.warn(
            "exec_ is deprecated, use exec", DeprecationWarning, stacklevel=2
        )
        return self.exec(*args, **kwargs)

    def hideEvent(self, event):
        super().hideEvent(event)
        if self.__loop is not None:
            self.__loop.exit(0)
            self.__loop = None

    def __macOnToolBarAction(self, action):
        index = action.data()
        self.stack.setCurrentIndex(index)


class StyleConfigWidget(QWidget):
    DisplayNames = {
        "windowsvista": "Windows (default)",
        "macintosh": "macOS (default)",
        "windows": "MS Windows 9x",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current_palette = ""
        form = FormLayout()
        styles = QStyleFactory.keys()
        styles = sorted(styles, key=cmp_to_key(
            lambda a, b:
                1 if a.lower() == "windows" and b.lower() == "fusion" else
                (-1 if a.lower() == "fusion" and b.lower() == "windows" else 0)
        ))
        styles = [
            (self.DisplayNames.get(st.lower(), st.capitalize()), st)
            for st in styles
        ]
        # Default style with empty userData key so it cleared in
        # persistent settings, allowing for default style resolution
        # on application star.
        styles = [("Default", "")] + styles
        self.style_cb = style_cb = QComboBox(objectName="style-cb")
        for name, key in styles:
            self.style_cb.addItem(name, userData=key)

        style_cb.currentIndexChanged.connect(self._style_changed)

        self.colors_cb = colors_cb = QComboBox(objectName="palette-cb")
        colors_cb.addItem("Default", userData="")
        colors_cb.addItem("Breeze Light", userData="breeze-light")
        colors_cb.addItem("Breeze Dark", userData="breeze-dark")
        colors_cb.addItem("Zion Reversed", userData="zion-reversed")
        colors_cb.addItem("Dark", userData="dark")

        form.addRow("Style", style_cb)
        form.addRow("Color theme", colors_cb)
        label = QLabel(
            "<small>Changes will be applied on next application startup.</small>",
            enabled=False,
        )
        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        form.addRow(label)
        self.setLayout(form)
        self._update_colors_enabled_state()

        style_cb.currentIndexChanged.connect(self.selectedStyleChanged)
        colors_cb.currentIndexChanged.connect(self.selectedPaletteChanged)

    def _style_changed(self):
        self._update_colors_enabled_state()

    def _update_colors_enabled_state(self):
        current = self.style_cb.currentData(Qt.UserRole)
        enable = current is not None and current.lower() in ("fusion", "windows")
        self._set_palette_enabled(enable)

    def _set_palette_enabled(self, state: bool):
        cb = self.colors_cb
        if cb.isEnabled() != state:
            cb.setEnabled(state)
            if not state:
                current = cb.currentData(Qt.UserRole)
                self._current_palette = current
                cb.setCurrentIndex(-1)
            else:
                index = cb.findData(self._current_palette, Qt.UserRole)
                if index == -1:
                    index = 0
                cb.setCurrentIndex(index)

    def selectedStyle(self) -> str:
        """Return the current selected style key."""
        key = self.style_cb.currentData()
        return key if key is not None else ""

    def setSelectedStyle(self, style: str) -> None:
        """Set the current selected style key."""
        idx = self.style_cb.findData(style, Qt.DisplayRole, Qt.MatchFixedString)
        if idx == -1:
            idx = 0  # select the default style
        self.style_cb.setCurrentIndex(idx)

    selectedStyleChanged = Signal()
    selectedStyle_ = Property(
        str, selectedStyle, setSelectedStyle,
        notify=selectedStyleChanged
    )

    def selectedPalette(self) -> str:
        """The current selected palette key."""
        key = self.colors_cb.currentData(Qt.UserRole)
        return key if key is not None else ""

    def setSelectedPalette(self, key: str) -> None:
        """Set the current selected palette key."""
        if not self.colors_cb.isEnabled():
            self._current_palette = key
            return
        idx = self.colors_cb.findData(key, Qt.UserRole, Qt.MatchFixedString)
        if idx == -1:
            idx = 0  # select the default color theme
        self.colors_cb.setCurrentIndex(idx)

    selectedPaletteChanged = Signal()
    selectedPalette_ = Property(
        str, selectedPalette, setSelectedPalette,
        notify=selectedPaletteChanged
    )


def category_state(cat, settings):
    visible = settings.value(
        "mainwindow/categories/{0}/visible".format(cat.name),
        defaultValue=not cat.hidden,
        type=bool
    )
    position = settings.value(
        "mainwindow/categories/{0}/position".format(cat.name),
        defaultValue=-1,
        type=int
    )
    return (visible, position)


def save_category_state(cat, state, settings):
    settings.setValue(
        "mainwindow/categories/{0}/visible".format(cat.name),
        state.visible
    )

    settings.setValue(
        "mainwindow/categories/{0}/position".format(cat.name),
        state.position
    )

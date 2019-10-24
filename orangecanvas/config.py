"""
Orange Canvas Configuration

"""

import os
import sys
import logging
import warnings

from distutils.version import LooseVersion
import typing

from typing import Dict, Optional, Tuple, List, Union, Iterable, Any

import pkg_resources

from AnyQt.QtGui import (
    QPainter, QFont, QFontMetrics, QColor, QPixmap, QIcon
)

from AnyQt.QtCore import (
    Qt, QCoreApplication, QPoint, QRect, QSettings, QStandardPaths
)

from .utils.settings import Settings, config_slot

if typing.TYPE_CHECKING:
    import requests
    from .scheme import Scheme
    T = typing.TypeVar("T")

EntryPoint = pkg_resources.EntryPoint
Distribution = pkg_resources.Distribution

log = logging.getLogger(__name__)

__version__ = "0.0"


#: Entry point by which widgets are registered.
WIDGETS_ENTRY = "orangecanvas.widgets"

#: Entry point by which add-ons register with pkg_resources.
ADDONS_ENTRY = "orangecanvas.addon"

#: Parameters for searching add-on packages in PyPi using xmlrpc api.
ADDON_PYPI_SEARCH_SPEC = {"keywords": ["orange", "add-on"]}

EXAMPLE_WORKFLOWS_ENTRY = "orangecanvas.examples"


def standard_location(type):
    warnings.warn(
        "Use QStandardPaths.writableLocation", DeprecationWarning,
        stacklevel=2
    )
    return QStandardPaths.writableLocation(type)


standard_location.DesktopLocation = QStandardPaths.DesktopLocation      # type: ignore
standard_location.DataLocation = QStandardPaths.DataLocation            # type: ignore
standard_location.CacheLocation = QStandardPaths.CacheLocation          # type: ignore
standard_location.DocumentsLocation = QStandardPaths.DocumentsLocation  # type: ignore


class Config:
    """
    Application configuration.
    """
    #: Organization domain
    OrganizationDomain = ""  # type: str
    #: The application name
    ApplicationName = ""     # type: str
    #: Version
    ApplicationVersion = ""  # type: str

    def init(self):
        """
        Initialize the QCoreApplication.organizationDomain, applicationName,
        applicationVersion and the default settings format.

        Should only be run once at application startup.
        """
        QCoreApplication.setOrganizationDomain(self.OrganizationDomain)
        QCoreApplication.setApplicationName(self.ApplicationName)
        QCoreApplication.setApplicationVersion(self.ApplicationVersion)
        QSettings.setDefaultFormat(QSettings.IniFormat)

    def application_icon(self):
        # type: () -> QIcon
        """
        Return the main application icon.
        """
        return QIcon()

    def splash_screen(self):
        # type: () -> Tuple[QPixmap, QRect]
        """
        Return a splash screen pixmap and an text area within it.

        The text area is used for displaying text messages during application
        startup.

        The default implementation returns a bland rectangle splash screen.

        Returns
        -------
        t : Tuple[QPixmap, QRect]
            A QPixmap and a rect area within it.
        """
        return QPixmap(), QRect()

    def widgets_entry_points(self):
        # type: () -> Iterable[EntryPoint]
        """
        Return an iterator over entry points defining the set of
        'nodes/widgets' available to the workflow model.
        """
        return iter(())

    def addon_entry_points(self):
        # type: () -> Iterable[EntryPoint]
        return iter(())

    def addon_pypi_search_spec(self):
        return {}

    def addon_defaults_list(
            self,
            session=None  # type: Optional[requests.Session]
    ):  # type: (...) -> List[Dict[str, Union[str, list, dict, int, float]]]
        """
        Return a list of default add-ons.

        The return value must be a list with meta description following the
        `PyPI JSON api`_ specification. At the minimum 'info.name' and
        'info.version' must be supplied. e.g.

            `[{'info': {'name': 'Super Pkg', 'version': '4.2'}}]

        .. _`PyPI JSON api`:
            https://warehouse.readthedocs.io/api-reference/json/
        """
        return []

    def core_packages(self):
        # type: () -> List[str]
        """
        Return a list of core packages.

        List of packages that are core of the application. Most importantly,
        if they themselves define add-on/plugin entry points they must
        not be 'uninstalled' via a package manager, they can only be
        updated.

        Return
        ------
        packages : List[str]
            A list of package names (can also contain PEP-440 version
            specifiers).
        """
        return ["orange-canvas-core >= 0.1a, < 0.2a"]

    def examples_entry_points(self):
        # type: () -> Iterable[EntryPoint]
        """
        Return an iterator over entry points defining example/preset workflows.
        """
        return iter(())

    def widget_discovery(self, *args, **kwargs):
        raise NotImplementedError

    def workflow_constructor(self, *args, **kwargs):
        # type: (Any, Any) -> Scheme
        """
        The default workflow constructor.
        """
        raise NotImplementedError

    #: Standard application urls. If defined to a valid url appropriate actions
    #: are defined in various contexts
    APPLICATION_URLS = {
        #: Submit a bug report action in the Help menu
        "Bug Report": None,
        #: A url quick tour/getting started url
        "Quick Start": None,
        #: An url to the full documentation
        "Documentation": None,
        #: Video screencast/tutorials
        "Screencasts": None,
        #: Used for 'Submit Feedback' action in the help menu
        "Feedback": None,
    }  # type: Dict[str, Optional[str]]


class Default(Config):

    OrganizationDomain = "biolab.si"
    ApplicationName = "Orange Canvas Core"
    ApplicationVersion = __version__

    @staticmethod
    def application_icon():
        """
        Return the main application icon.
        """
        path = pkg_resources.resource_filename(
            __name__, "icons/orange-canvas.svg"
        )
        return QIcon(path)

    @staticmethod
    def splash_screen():
        # type: () -> Tuple[QPixmap, QRect]
        """
        Return a splash screen pixmap and an text area within it.

        The text area is used for displaying text messages during application
        startup.

        The default implementation returns a bland rectangle splash screen.

        Returns
        -------
        t : Tuple[QPixmap, QRect]
            A QPixmap and a rect area within it.
        """
        path = pkg_resources.resource_filename(
            __name__, "icons/orange-canvas-core-splash.svg")
        pm = QPixmap(path)

        version = QCoreApplication.applicationVersion()
        if version:
            version_parsed = LooseVersion(version)
            version_comp = version_parsed.version
            version = ".".join(map(str, version_comp[:2]))
        size = 21 if len(version) < 5 else 16
        font = QFont()
        font.setPixelSize(size)
        font.setBold(True)
        font.setItalic(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        metrics = QFontMetrics(font)
        br = metrics.boundingRect(version).adjusted(-5, 0, 5, 0)
        br.moveBottomRight(QPoint(pm.width() - 15, pm.height() - 15))

        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(font)
        p.setPen(QColor("#231F20"))
        p.drawText(br, Qt.AlignCenter, version)
        p.end()
        textarea = QRect(15, 15, 170, 20)
        return pm, textarea

    @staticmethod
    def widgets_entry_points():
        # type: () -> Iterable[EntryPoint]
        """
        Return an iterator over entry points defining the set of
        'nodes/widgets' available to the workflow model.
        """
        return pkg_resources.iter_entry_points(WIDGETS_ENTRY)

    @staticmethod
    def addon_entry_points():
        # type: () -> Iterable[EntryPoint]
        return pkg_resources.iter_entry_points(ADDONS_ENTRY)

    @staticmethod
    def addon_pypi_search_spec():
        return dict(ADDON_PYPI_SEARCH_SPEC)

    @staticmethod
    def addon_defaults_list(session=None):
        """
        Return a list of default add-ons.

        The return value must be a list with meta description following the
        `PyPI JSON api`_ specification. At the minimum 'info.name' and
        'info.version' must be supplied. e.g.

            `[{'info': {'name': 'Super Pkg', 'version': '4.2'}}]

        .. _`PyPI JSON api`:
            https://warehouse.readthedocs.io/api-reference/json/
        """
        return []

    @staticmethod
    def core_packages():
        # type: () -> List[str]
        """
        Return a list of core packages.

        List of packages that are core of the product. Most importantly,
        if they themselves define add-on/plugin entry points they must
        not be 'uninstalled' via a package manager, they can only be
        updated.

        Return
        ------
        packages : List[str]
            A list of package names (can also contain PEP-440 version
            specifiers).
        """
        return ["orange-canvas-core >= 0.0, < 0.1a"]

    @staticmethod
    def examples_entry_points():
        return pkg_resources.iter_entry_points(EXAMPLE_WORKFLOWS_ENTRY)

    @staticmethod
    def widget_discovery(*args, **kwargs):
        from . import registry
        return registry.WidgetDiscovery(*args, **kwargs)

    @staticmethod
    def workflow_constructor(*args, **kwargs):
        from . import scheme
        return scheme.Scheme(*args, **kwargs)


default = Default()


def init():
    """
    Initialize the QCoreApplication.organizationDomain, applicationName,
    applicationVersion and the default settings format. Will only run once.

    .. note:: This should not be run before QApplication has been initialized.
              Otherwise it can break Qt's plugin search paths.

    """
    default.init()
    # Make consecutive calls a null op.
    global init
    log.debug("Activating configuration for {}".format(default))
    init = lambda: None


rc = {}  # type: ignore


spec = \
    [("startup/show-splash-screen", bool, True,
      "Show splash screen at startup"),

     ("startup/show-welcome-screen", bool, True,
      "Show Welcome screen at startup"),

     ("stylesheet", str, "orange",
      "QSS stylesheet to use"),

     ("schemeinfo/show-at-new-scheme", bool, False,
      "Show Workflow Properties when creating a new Workflow"),

     ("mainwindow/scheme-margins-enabled", bool, False,
      "Show margins around the workflow view"),

     ("mainwindow/show-scheme-shadow", bool, True,
      "Show shadow around the workflow view"),

     ("mainwindow/toolbox-dock-exclusive", bool, False,
      "Should the toolbox show only one expanded category at the time"),

     ("mainwindow/toolbox-dock-floatable", bool, False,
      "Is the canvas toolbox floatable (detachable from the main window)"),

     ("mainwindow/toolbox-dock-movable", bool, True,
      "Is the canvas toolbox movable (between left and right edge)"),

     ("mainwindow/toolbox-dock-use-popover-menu", bool, True,
      "Use a popover menu to select a widget when clicking on a category "
      "button"),

     ("mainwindow/widgets-float-on-top", bool, False,
      "Float widgets on top of other windows"),

     ("mainwindow/number-of-recent-schemes", int, 15,
      "Number of recent workflows to keep in history"),

     ("schemeedit/show-channel-names", bool, True,
      "Show channel names"),

     ("schemeedit/show-link-state", bool, True,
      "Show link state hints."),

     ("schemeedit/enable-node-animations", bool, True,
      "Enable node animations."),

     ("schemeedit/freeze-on-load", bool, False,
      "Freeze signal propagation when loading a workflow."),

     ("quickmenu/trigger-on-double-click", bool, True,
      "Show quick menu on double click."),

     ("quickmenu/trigger-on-right-click", bool, True,
      "Show quick menu on right click."),

     ("quickmenu/trigger-on-space-key", bool, True,
      "Show quick menu on space key press."),

     ("quickmenu/trigger-on-any-key", bool, False,
      "Show quick menu on double click."),

     ("quickmenu/show-categories", bool, False,
      "Show categories in quick menu."),

     ("logging/level", int, 1, "Logging level"),

     ("logging/show-on-error", bool, True, "Show log window on error"),

     ("logging/dockable", bool, True, "Allow log window to be docked"),

     ("help/open-in-external-browser", bool, False,
      "Open help in an external browser"),

     ("add-ons/allow-conda", bool, True,
      "Install add-ons with conda"),

     ("add-ons/pip-install-arguments", str, '',
      'Arguments to pass to "pip install" when installing add-ons.'),

     ("network/http-proxy", str, '', 'HTTP proxy.'),

     ("network/https-proxy", str, '', 'HTTPS proxy.'),
     ]


spec = [config_slot(*t) for t in spec]


def register_setting(key, type, default, doc=""):
    # type: (str, typing.Type[T], T, str) -> None
    """
    Register an application setting.

    This only affects the `Settings` instance as returned by `settings`.

    Parameters
    ----------
    key : str
        The setting key path
    type : Type[T]
        Type of the setting. One of `str`, `bool` or `int`
    default : T
        Default value for setting.
    doc : str
        Setting description string.
    """
    spec.append(config_slot(key, type, default, doc))


def settings():
    init()
    store = QSettings()
    settings = Settings(defaults=spec, store=store)
    return settings


def data_dir():
    """
    Return the application data directory. If the directory path
    does not yet exists then create it.
    """
    init()
    datadir = QStandardPaths.writableLocation(QStandardPaths.DataLocation)
    version = QCoreApplication.applicationVersion()
    datadir = os.path.join(datadir, version)
    if not os.path.isdir(datadir):
        try:
            os.makedirs(datadir, exist_ok=True)
        except OSError:
            pass
    return datadir


def cache_dir():
    """
    Return the application cache directory. If the directory path
    does not yet exists then create it.
    """
    init()
    cachedir = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
    version = QCoreApplication.applicationVersion()
    cachedir = os.path.join(cachedir, version)
    if not os.path.exists(cachedir):
        os.makedirs(cachedir)
    return cachedir


def log_dir():
    """
    Return the application log directory.
    """
    init()
    if sys.platform == "darwin":
        name = str(QCoreApplication.applicationName())
        logdir = os.path.join(os.path.expanduser("~/Library/Logs"), name)
    else:
        logdir = data_dir()

    if not os.path.exists(logdir):
        os.makedirs(logdir)
    return logdir


def widget_settings_dir():
    """
    Return the widget settings directory.
    """
    warnings.warn(
        "'widget_settings_dir' is deprecated.",
        DeprecationWarning, stacklevel=2
    )
    return os.path.join(data_dir(), 'widgets')


def open_config():
    warnings.warn(
        "open_config was never used and will be removed in the future",
        DeprecationWarning, stacklevel=2
    )
    return


def save_config():
    warnings.warn(
        "save_config was never used and will be removed in the future",
        DeprecationWarning, stacklevel=2
    )


def widgets_entry_points():
    """
    Return an `EntryPoint` iterator for all 'orange.widget' entry
    points plus the default Orange Widgets.

    """
    return default.widgets_entry_points()


def splash_screen():
    """
    """
    return default.splash_screen()


def application_icon():
    """
    Return the main application icon.
    """
    return default.application_icon()


def widget_discovery(*args, **kwargs):
    return default.widget_discovery(*args, **kwargs)


def workflow_constructor(*args, **kwargs):
    # type: (Any, Any) -> Scheme
    return default.workflow_constructor(*args, **kwargs)


def set_default(conf):
    global default
    default = conf

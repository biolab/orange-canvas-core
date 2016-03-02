"""
Orange Canvas Configuration

"""

import os
import sys
import logging
import pickle
import itertools

import pkg_resources
import six

from AnyQt.QtGui import (
    QPainter, QFont, QFontMetrics, QColor, QPixmap, QIcon
)

from AnyQt.QtCore import Qt, QCoreApplication, QPoint, QRect, QT_VERSION

if QT_VERSION < 0x50000:
    from AnyQt.QtGui import QDesktopServices
else:
    from AnyQt.QtCore import QStandardPaths

from .utils.settings import Settings, config_slot

# Import QSettings from qtcompat module (compatibility with PyQt < 4.8.3
from .utils.qtcompat import QSettings

log = logging.getLogger(__name__)

__version__ = "0.0"

# from . import __version__

#: Entry point by which widgets are registered.
WIDGETS_ENTRY = "orangecanvas.widgets"
#: Entry point by which add-ons register with pkg_resources.
ADDONS_ENTRY = "orangecanvas.addon"
#: Parameters for searching add-on packages in PyPi using xmlrpc api.
ADDON_PYPI_SEARCH_SPEC = {"keywords": "orange add-on"}

TUTORIALS_ENTRY = "orangecanvas.tutorials"

if QT_VERSION < 0x50000:
    def standard_location(type):
        return QDesktopServices.storageLocation(type)
    standard_location.DesktopLocation = QDesktopServices.DesktopLocation
    standard_location.DataLocation = QDesktopServices.DataLocation
    standard_location.CacheLocation = QDesktopServices.CacheLocation
else:
    def standard_location(type):
        return QStandardPaths.writableLocation(type)
    standard_location.DesktopLocation = QStandardPaths.DesktopLocation
    standard_location.DataLocation = QStandardPaths.DataLocation
    standard_location.CacheLocation = QStandardPaths.CacheLocation


class default(object):
    OrganizationDomain = "biolab.si"
    ApplicationName = "Orange Canvas Core"
    ApplicationVersion = __version__

    @classmethod
    def init(cls):
        QCoreApplication.setOrganizationDomain(cls.OrganizationDomain)
        QCoreApplication.setApplicationName(cls.ApplicationName)
        QCoreApplication.setApplicationVersion(cls.ApplicationVersion)

        QSettings.setDefaultFormat(QSettings.IniFormat)

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
        path = pkg_resources.resource_filename(
            __name__, "icons/orange-splash-screen.png")
        pm = QPixmap(path)

        version = QCoreApplication.applicationVersion()
        size = 21 if len(version) < 5 else 16
        font = QFont("Helvetica")
        font.setPixelSize(size)
        font.setBold(True)
        font.setItalic(True)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        metrics = QFontMetrics(font)
        br = metrics.boundingRect(version).adjusted(-5, 0, 5, 0)
        br.moveCenter(QPoint(436, 224))

        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setFont(font)
        p.setPen(QColor("#231F20"))
        p.drawText(br, Qt.AlignCenter, version)
        p.end()
        return pm, QRect(88, 193, 200, 20)

    @staticmethod
    def widgets_entry_points():
        return pkg_resources.iter_entry_points(WIDGETS_ENTRY)

    @staticmethod
    def addon_entry_points():
        return pkg_resources.iter_entry_points(ADDONS_ENTRY)

    @staticmethod
    def addon_pypi_search_spec():
        return dict(ADDON_PYPI_SEARCH_SPEC)

    @staticmethod
    def tutorials_entry_points():
        return pkg_resources.iter_entry_points(TUTORIALS_ENTRY)

    @staticmethod
    def widget_discovery(*args, **kwargs):
        from . import registry
        return registry.WidgetDiscovery(*args, **kwargs)

    @staticmethod
    def workflow_constructor(*args, **kwargs):
        from . import scheme
        return scheme.Scheme(*args, **kwargs)


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

rc = {}


spec = \
    [("startup/show-splash-screen", bool, True,
      "Show splash screen at startup"),

     ("startup/show-welcome-screen", bool, True,
      "Show Welcome screen at startup"),

     ("stylesheet", six.text_type, "orange",
      "QSS stylesheet to use"),

     ("schemeinfo/show-at-new-scheme", bool, True,
      "Show Workflow Properties when creating a new Workflow"),

     ("mainwindow/scheme-margins-enabled", bool, False,
      "Show margins around the workflow view"),

     ("mainwindow/show-scheme-shadow", bool, True,
      "Show shadow around the workflow view"),

     ("mainwindow/toolbox-dock-exclusive", bool, True,
      "Should the toolbox show only one expanded category at the time"),

     ("mainwindow/toolbox-dock-floatable", bool, False,
      "Is the canvas toolbox floatable (detachable from the main window)"),

     ("mainwindow/toolbox-dock-movable", bool, True,
      "Is the canvas toolbox movable (between left and right edge)"),

     ("mainwindow/toolbox-dock-use-popover-menu", bool, True,
      "Use a popover menu to select a widget when clicking on a category "
      "button"),

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

     ("logging/level", int, 1, "Logging level"),

     ("logging/show-on-error", bool, True, "Show log window on error"),

     ("logging/dockable", bool, True, "Allow log window to be docked"),

     ("help/open-in-external-browser", bool, False,
      "Open help in an external browser")
     ]

spec = [config_slot(*t) for t in spec]


def settings():
    init()
    store = QSettings()
    settings = Settings(defaults=spec, store=store)
    return settings


def data_dir():
    """Return the application data directory. If the directory path
    does not yet exists then create it.

    """
    init()

    datadir = standard_location(standard_location.DataLocation)
    datadir = six.text_type(datadir)
    version = six.text_type(QCoreApplication.applicationVersion())
    datadir = os.path.join(datadir, version)
    if not os.path.exists(datadir):
        os.makedirs(datadir)
    return datadir


def cache_dir():
    """Return the application cache directory. If the directory path
    does not yet exists then create it.

    """
    init()

    cachedir = standard_location(standard_location.CacheLocation)
    cachedir = six.text_type(cachedir)
    version = six.text_type(QCoreApplication.applicationVersion())
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
    return os.path.join(data_dir(), 'widgets')


def open_config():
    global rc
    app_dir = data_dir()
    filename = os.path.join(app_dir, "canvas-rc.pck")
    if os.path.exists(filename):
        with open(os.path.join(app_dir, "canvas-rc.pck"), "rb") as f:
            rc.update(pickle.load(f))


def save_config():
    app_dir = data_dir()
    with open(os.path.join(app_dir, "canvas-rc.pck"), "wb") as f:
        pickle.dump(rc, f)


def recent_schemes():
    """Return a list of recently accessed schemes.
    """
    app_dir = data_dir()
    recent_filename = os.path.join(app_dir, "recent.pck")
    recent = []
    if os.path.isdir(app_dir) and os.path.isfile(recent_filename):
        with open(recent_filename, "rb") as f:
            recent = pickle.load(f)

    # Filter out files not found on the file system
    recent = [(title, path) for title, path in recent \
              if os.path.exists(path)]
    return recent


def save_recent_scheme_list(scheme_list):
    """Save the list of recently accessed schemes
    """
    app_dir = data_dir()
    recent_filename = os.path.join(app_dir, "recent.pck")

    if os.path.isdir(app_dir):
        with open(recent_filename, "wb") as f:
            pickle.dump(scheme_list, f)


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
    return default.workflow_constructor(*args, **kwargs)


def set_default(conf):
    global default
    default = conf

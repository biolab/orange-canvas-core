"""
Orange Canvas Application

"""
import atexit
import sys
import os
import argparse
import logging
from typing import Optional, List, Sequence

import AnyQt
from AnyQt.QtWidgets import QApplication
from AnyQt.QtCore import (
    Qt, QUrl, QEvent, QSettings, QLibraryInfo, pyqtSignal as Signal
)

from orangecanvas.utils.after_exit import run_after_exit
from orangecanvas.utils.asyncutils import get_event_loop


def fix_qt_plugins_path():
    """
    Attempt to fix qt plugins path if it is invalid.

    https://www.riverbankcomputing.com/pipermail/pyqt/2018-November/041089.html
    """
    # PyQt5 loads a runtime generated qt.conf file into qt's resource system
    # but does not correctly (INI) encode non-latin1 characters in paths
    # (https://www.riverbankcomputing.com/pipermail/pyqt/2018-November/041089.html)
    # Need to be careful not to mess the plugins path when not installed as
    # a (delocated) wheel.
    s = QSettings(":qt/etc/qt.conf", QSettings.IniFormat)
    path = s.value("Paths/Prefix", type=str)
    # does the ':qt/etc/qt.conf' exist and has prefix path that does not exist
    if path and os.path.exists(path):
        return
    # Use QLibraryInfo.location to resolve the plugins dir
    pluginspath = QLibraryInfo.location(QLibraryInfo.PluginsPath)

    # Check effective library paths. Someone might already set the search
    # paths (including via QT_PLUGIN_PATH). QApplication.libraryPaths() returns
    # existing paths only.
    paths = QApplication.libraryPaths()
    if paths:
        return

    if AnyQt.USED_API == "pyqt5":
        import PyQt5.QtCore as qc
    elif AnyQt.USED_API == "pyside2":
        import PySide2.QtCore as qc
    else:
        return

    def normpath(path):
        return os.path.normcase(os.path.normpath(path))

    # guess the appropriate path relative to the installation dir based on the
    # PyQt5 installation dir and the 'recorded' plugins path. I.e. match the
    # 'PyQt5' directory name in the recorded path and replace the 'invalid'
    # prefix with the real PyQt5 install dir.
    def maybe_match_prefix(prefix: str, path: str) -> Optional[str]:
        """
        >>> maybe_match_prefix("aa/bb/cc", "/a/b/cc/a/b")
        "aa/bb/cc/a/b"
        >>> maybe_match_prefix("aa/bb/dd", "/a/b/cc/a/b")
        None
        """
        prefix = normpath(prefix)
        path = normpath(path)
        basename = os.path.basename(prefix)
        path_components = path.split(os.sep)
        # find the (rightmost) basename in the prefix_components
        idx = None
        try:
            start = 0
            while True:
                idx = path_components.index(basename, start)
                start = idx + 1
        except ValueError:
            pass
        if idx is None:
            return None
        return os.path.join(prefix, *path_components[idx + 1:])

    newpath = maybe_match_prefix(
        os.path.dirname(qc.__file__), pluginspath
    )
    if newpath is not None and os.path.exists(newpath):
        QApplication.addLibraryPath(newpath)


class CanvasApplication(QApplication):
    fileOpenRequest = Signal(QUrl)

    __args = None

    def __init__(self, argv):
        fix_qt_plugins_path()
        if hasattr(Qt, "AA_EnableHighDpiScaling"):
            # Turn on HighDPI support when available
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)

        CanvasApplication.__args, argv_ = self.parse_style_arguments(argv)
        if self.__args.style:
            argv_ = argv_ + ["-style", self.__args.style]
        super().__init__(argv_)
        # Make sure there is an asyncio event loop that runs on the
        # Qt event loop.
        _ = get_event_loop()
        argv[:] = argv_
        self.setAttribute(Qt.AA_DontShowIconsInMenus, True)
        if hasattr(self, "styleHints"):
            sh = self.styleHints()
            if hasattr(sh, 'setShowShortcutsInContextMenus'):
                # PyQt5.13 and up
                sh.setShowShortcutsInContextMenus(True)
        self.configureStyle()

    def event(self, event):
        if event.type() == QEvent.FileOpen:
            self.fileOpenRequest.emit(event.url())
        elif event.type() == QEvent.PolishRequest:
            self.configureStyle()
        return super().event(event)

    @staticmethod
    def parse_style_arguments(argv):
        parser = argparse.ArgumentParser()
        parser.add_argument("-style", type=str, default=None)
        parser.add_argument("-colortheme", type=str, default=None)
        ns, rest = parser.parse_known_args(argv)
        if ns.style is not None:
            if ":" in ns.style:
                ns.style, colortheme = ns.style.split(":", 1)
                if ns.colortheme is None:
                    ns.colortheme = colortheme
        return ns, rest

    @staticmethod
    def configureStyle():
        from orangecanvas import styles
        args = CanvasApplication.__args
        settings = QSettings()
        settings.beginGroup("application-style")
        name = settings.value("style-name", "", type=str)
        if args is not None and args.style:
            # command line params take precedence
            name = args.style

        if name != "":
            inst = QApplication.instance()
            if inst is not None:
                if inst.style().objectName().lower() != name.lower():
                    QApplication.setStyle(name)

        theme = settings.value("palette", "", type=str)
        if args is not None and args.colortheme:
            theme = args.colortheme

        if theme and theme in styles.colorthemes:
            palette = styles.colorthemes[theme]()
            QApplication.setPalette(palette)


__restart_command: Optional[List[str]] = None


def set_restart_command(cmd: Optional[Sequence[str]]):
    """
    Set or unset the restart command.

    This command will be run after this process exits.

    Pass cmd=None to unset the current command.
    """
    global __restart_command
    log = logging.getLogger(__name__)
    atexit.unregister(__restart)
    if cmd is None:
        __restart_command = None
        log.info("Disabling application restart")
    else:
        __restart_command = list(cmd)
        atexit.register(__restart)
        log.info("Enabling application restart with: %r", cmd)


def restart_command() -> Optional[List[str]]:
    """Return the current set restart command."""
    return __restart_command


def restart_cancel() -> None:
    set_restart_command(None)


def default_restart_command():
    """Return the default restart command."""
    return [sys.executable, sys.argv[0]]


def __restart():
    if __restart_command:
        run_after_exit(__restart_command)

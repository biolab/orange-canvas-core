"""
"""
import argparse

import os
import sys
import gc
import logging
import pickle
import shlex
import warnings
from typing import List, Optional, IO, Any

from urllib.request import getproxies
from contextlib import ExitStack, closing

from AnyQt.QtGui import QFont, QColor, QPalette
from AnyQt.QtCore import Qt, QSettings, QTimer, QUrl, QDir

from .utils.after_exit import run_after_exit
from .styles import style_sheet, breeze_dark as _breeze_dark
from .application.application import CanvasApplication
from .application.canvasmain import CanvasMainWindow
from .application.outputview import TextStream, ExceptHook, TerminalTextDocument

from . import utils, config
from .gui.splashscreen import SplashScreen
from .gui.utils import macos_set_nswindow_tabbing as _macos_set_nswindow_tabbing

from .registry import WidgetRegistry, set_global_registry
from .registry.qt import QtRegistryHandler
from .registry import cache

log = logging.getLogger(__name__)


class Main:
    """
    A helper 'main' runner class.
    """
    #: The default config namespace
    DefaultConfig: Optional[str] = None
    config: config.Config
    #: Arguments list (remaining after options parsing).
    arguments: List[str] = []
    #: Parsed option arguments
    options: argparse.Namespace = None
    registry: WidgetRegistry = None
    application: CanvasApplication = None

    def __init__(self):
        self.options = argparse.Namespace()
        self.arguments: List[str] = []

    def argument_parser(self) -> argparse.ArgumentParser:
        """
        Construct an return an `argparse.ArgumentParser` instance
        """
        return arg_parser()

    def parse_arguments(self, argv: List[str]):
        """
        Parse the `argv` argument list.

        Initialize the options
        """
        parser = self.argument_parser()
        options, argv_rest = parser.parse_known_args(argv[1:])
        # Handle the deprecated args (let QApplication handle this)
        if options.style is not None:
            argv_rest = ["-style", options.style] + argv_rest
        if options.qt is not None:
            argv_rest = shlex.split(options.qt) + argv_rest

        self.options = options
        self.arguments = argv_rest

    def activate_default_config(self):
        """
        Activate the default configuration (:mod:`config`)
        """
        config_ns = self.DefaultConfig
        if self.options.config is not None:
            config_ns = self.options.config
        cfg = None
        if config_ns is not None:
            try:
                cfg_class = utils.name_lookup(config_ns)
            except (ImportError, AttributeError):
                pass
            else:
                cfg = cfg_class()
        if cfg is None:
            cfg = config.Default()
        self.config = cfg
        config.set_default(cfg)
        # Init config
        config.init()

    def show_splash_message(self, message: str, color=QColor()):
        """Display splash screen message"""
        splash = self.splash_screen()
        if splash is not None:
            splash.show()
            splash.showMessage(message, color=color)

    def close_splash_screen(self):
        """Close splash screen."""
        splash = self.splash_screen()
        if splash is not None:
            splash.close()
            self.__splash_screen = None

    __splash_screen = None

    def splash_screen(self) -> SplashScreen:
        """Return the application splash screen"""
        if self.__splash_screen is not None:
            return self.__splash_screen[0]

        settings = QSettings()
        options = self.options
        want_splash = \
            settings.value("startup/show-splash-screen", True, type=bool) and \
            not options.no_splash

        if want_splash:
            pm, rect = self.config.splash_screen()
            splash_screen = SplashScreen(pixmap=pm, textRect=rect)
            splash_screen.setAttribute(Qt.WA_DeleteOnClose)
            splash_screen.setFont(QFont("Helvetica", 12))
            palette = splash_screen.palette()
            color = QColor("#FFD39F")
            palette.setColor(QPalette.Text, color)
            splash_screen.setPalette(palette)
        else:
            splash_screen = None
        self.__splash_screen = (splash_screen,)
        return splash_screen

    def run_discovery(self) -> WidgetRegistry:
        """
        Run the widget discovery and return the resulting registry.
        """
        options = self.options
        if not options.force_discovery:
            reg_cache = cache.registry_cache()
        else:
            reg_cache = None

        widget_registry = WidgetRegistry()
        handler = QtRegistryHandler(registry=widget_registry)
        handler.found_category.connect(
            lambda cd: self.show_splash_message(cd.name)
        )
        widget_discovery = self.config.widget_discovery(
            handler, cached_descriptions=reg_cache
        )
        cache_filename = os.path.join(config.cache_dir(), "widget-registry.pck")
        if options.no_discovery:
            with open(cache_filename, "rb") as f:
                widget_registry = pickle.load(f)
            widget_registry = WidgetRegistry(widget_registry)
        else:
            widget_discovery.run(self.config.widgets_entry_points())

            # Store cached descriptions
            cache.save_registry_cache(widget_discovery.cached_descriptions)
            with open(cache_filename, "wb") as f:
                pickle.dump(WidgetRegistry(widget_registry), f)
        self.registry = widget_registry
        self.close_splash_screen()
        return widget_registry

    def setup_application(self):
        # sys.argv[0] must be in QApplication's argv list.
        self.application = CanvasApplication(sys.argv[:1] + self.arguments)
        # Update the arguments
        self.arguments = self.application.arguments()[1:]
        fix_set_proxy_env()

    def tear_down_application(self):
        gc.collect()
        self.application.processEvents()
        del self.application

    #: An exit stack to run cleanup at application exit.
    stack: ExitStack

    def run(self, argv: List[str]) -> int:
        if argv is None:
            argv = sys.argv
        fix_win_pythonw_std_stream()
        self.parse_arguments(argv)
        self.activate_default_config()
        with ExitStack() as stack:
            self.stack = stack
            self.setup_application()
            stack.callback(self.tear_down_application)
            self.setup_sys_redirections()
            stack.callback(self.tear_down_sys_redirections)
            self.setup_logging()
            stack.callback(self.tear_down_logging)
            paths = self.arguments
            log.debug("Loading paths from argv: %s", " ,".join(paths))

            def record_path(url: QUrl):
                log.debug("Path from FileOpen event: %s", url.toLocalFile())
                paths.append(url.toLocalFile())

            self.application.fileOpenRequest.connect(record_path)

            registry = self.run_discovery()
            set_global_registry(registry)

            mainwindow = self.setup_main_window()
            mainwindow.show()

            if not paths:
                self.show_welcome_screen(mainwindow)
            else:
                self.open_files(paths)

            def open_request(url):
                path = url.toLocalFile()
                if os.path.exists(path) and not (
                    path.endswith("pydevd.py") or
                    path.endswith("run_profiler.py")
                ):
                    mainwindow.open_scheme_file(path)
            self.application.fileOpenRequest.connect(open_request)
            rv = self.application.exec()
            del mainwindow
        if rv == 96:
            log.info('Restarting via exit code 96.')
            run_after_exit([sys.executable, sys.argv[0]])
        return rv

    def open_files(self, paths):
        _windows = [self.window]

        def _window():
            if _windows:
                return _windows.pop(0)
            else:
                return self.window.create_new_window()

        for path in paths:
            w = _window()
            w.open_scheme_file(path)
            w.show()

    def setup_logging(self):
        level = self.options.log_level
        logformat = "%(asctime)s:%(levelname)s:%(name)s: %(message)s"

        # File handler should always be at least INFO level so we need
        # the application root level to be at least at INFO.
        root_level = min(level, logging.INFO)
        rootlogger = logging.getLogger()
        rootlogger.setLevel(root_level)

        # Standard output stream handler at the requested level
        stream_hander = make_stream_handler(
            level, fileobj=self.__stderr__, fmt=logformat
        )
        rootlogger.addHandler(stream_hander)
        # Setup log capture for MainWindow/Log
        log_stream = TextStream(objectName="-log-stream")
        self.output.connectStream(log_stream)
        self.stack.push(closing(log_stream))  # close on exit
        log_handler = make_stream_handler(
            level, fileobj=log_stream, fmt=logformat
        )
        rootlogger.addHandler(log_handler)

        # Also log to file
        file_handler = make_file_handler(
            root_level, os.path.join(config.log_dir(), "canvas.log"),
            mode="w",
        )
        rootlogger.addHandler(file_handler)

    def tear_down_logging(self):
        pass

    def create_main_window(self) -> CanvasMainWindow:
        """Create the (initial) main window."""
        return CanvasMainWindow()

    window: CanvasMainWindow

    def setup_main_window(self):
        stylesheet = self.main_window_stylesheet()
        self.window = window = self.create_main_window()
        if sys.platform != "darwin":  # on macOS transient document views do not have an icon.
            window.setWindowIcon(self.config.application_icon())
        window.setStyleSheet(stylesheet)
        window.output_view().setDocument(self.output)
        window.set_widget_registry(self.registry)
        return window

    def main_window_stylesheet(self):
        """Return the stylesheet for the main window."""
        options = self.options
        palette = self.application.palette()
        stylesheet = "orange.qss"
        if palette.color(QPalette.Window).value() < 127:
            log.info("Switching default stylesheet to darkorange")
            stylesheet = "darkorange.qss"

        if options.stylesheet is not None:
            stylesheet = options.stylesheet
        qss, paths = style_sheet(stylesheet)
        for prefix, path in paths:
            if path not in QDir.searchPaths(prefix):
                log.info("Adding search path %r for prefix, %r", path, prefix)
                QDir.addSearchPath(prefix, path)
        return qss

    def show_welcome_screen(self, parent: CanvasMainWindow):
        """Show the initial welcome screen."""
        settings = QSettings()
        options = self.options
        want_welcome = settings.value(
            "startup/show-welcome-screen", True, type=bool
        ) and not options.no_welcome

        def trigger():
            if not parent.is_transient():
                return
            swp_loaded = parent.ask_load_swp_if_exists()
            if not swp_loaded and want_welcome:
                parent.welcome_action.trigger()

        # On a timer to allow FileOpen events to be delivered. If so
        # then do not show the welcome screen.
        QTimer.singleShot(0, trigger)

    __stdout__: Optional[IO] = None
    __stderr__: Optional[IO] = None
    __excepthook__: Optional[Any] = None

    output: TerminalTextDocument

    def setup_sys_redirections(self):
        self.output = doc = TerminalTextDocument()

        stdout = TextStream(objectName="-stdout")
        stderr = TextStream(objectName="-stderr")
        doc.connectStream(stdout)
        doc.connectStream(stderr, color=Qt.red)

        if sys.stdout is not None:
            stdout.stream.connect(sys.stdout.write, Qt.DirectConnection)

        self.__stdout__ = sys.stdout
        sys.stdout = stdout

        if sys.stderr is not None:
            stderr.stream.connect(sys.stderr.write, Qt.DirectConnection)

        self.__stderr__ = sys.stderr
        sys.stderr = stderr
        self.__excepthook__ = sys.excepthook
        sys.excepthook = ExceptHook(stream=stderr)

        self.stack.push(closing(stdout))
        self.stack.push(closing(stderr))

    def tear_down_sys_redirections(self):
        if self.__excepthook__ is not None:
            sys.excepthook = self.__excepthook__
        if self.__stderr__ is not None:
            sys.stderr = self.__stderr__
        if self.__stdout__ is not None:
            sys.stdout = self.__stdout__


def fix_win_pythonw_std_stream():
    """
    On windows when running without a console (using pythonw.exe without I/O
    redirection) the std[err|out] file descriptors are invalid
    (`http://bugs.python.org/issue706263`_). We `fix` this by setting the
    stdout/stderr to `os.devnull`.
    """
    if sys.platform == "win32" and \
            os.path.basename(sys.executable) == "pythonw.exe":
        if sys.stdout is None or sys.stdout.fileno() < 0:
            sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="ignore")
        if sys.stderr is None or sys.stderr.fileno() < 0:
            sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="ignore")


default_proxies = None


# TODO: Remove this
def fix_set_proxy_env():
    """
    Set http_proxy/https_proxy environment variables (for requests, pip, ...)
    from user-specified settings or, if none, from system settings on OS X
    and from registry on Windos.
    """
    warnings.warn(
        "fix_set_proxy_env is deprecated", DeprecationWarning,
        stacklevel=2
    )
    # save default proxies so that setting can be reset
    global default_proxies
    if default_proxies is None:
        default_proxies = getproxies()  # can also read windows and macos settings

    settings = QSettings()
    proxies = getproxies()
    for scheme in set(["http", "https"]) | set(proxies):
        from_settings = settings.value("network/" + scheme + "-proxy", "", type=str)
        from_default = default_proxies.get(scheme, "")
        env_scheme = scheme + '_proxy'
        if from_settings:
            os.environ[env_scheme] = from_settings
        elif from_default:
            os.environ[env_scheme] = from_default  # crucial for windows/macos support
        else:
            os.environ.pop(env_scheme, "")


def fix_macos_nswindow_tabbing():
    warnings.warn(
        f"'{__name__}.fix_macos_nswindow_tabbing()' is deprecated. Use "
        "'orangecanvas.gui.utils.macos_set_nswindow_tabbing()' instead",
        DeprecationWarning, stacklevel=2
    )
    _macos_set_nswindow_tabbing()


# Used to be defined here now moved to styles.
def breeze_dark():
    warnings.warn(
        f"{__name__}'.breeze_dark()' has been moved to styles package.",
        DeprecationWarning, stacklevel=2
    )
    return _breeze_dark()


def make_stream_handler(level, fileobj=None, fmt=None):
    handler = logging.StreamHandler(fileobj)
    handler.setLevel(level)
    if fmt:
        handler.setFormatter(logging.Formatter(fmt))
    return handler


def make_file_handler(level, filename, mode="w", fmt=None):
    handler = logging.FileHandler(filename, mode=mode)
    handler.setLevel(level)
    if fmt:
        handler.setFormatter(logging.Formatter(fmt))
    return handler


LOG_LEVELS = [
    logging.CRITICAL + 10,
    logging.CRITICAL,
    logging.ERROR,
    logging.WARN,
    logging.INFO,
    logging.DEBUG
]


def arg_parser():
    def log_level(value):
        if value in ("0", "1", "2", "3", "4", "5"):
            return LOG_LEVELS[int(value)]
        elif hasattr(logging, value.upper()):
            return getattr(logging, value.upper())
        else:
            raise ValueError("Invalid log level {!r}".format(value))

    parser = argparse.ArgumentParser(
        usage="usage: %(prog)s [options] [workflow_file]"
    )
    parser.add_argument(
        "--no-discovery", action="store_true",
        help="Don't run widget discovery (use full cache instead)"
    )
    parser.add_argument(
        "--force-discovery", action="store_true",
        help="Force full widget discovery (invalidate cache)"
    )
    parser.add_argument(
        "--no-welcome", action="store_true",
        help="Don't show welcome dialog."
    )
    parser.add_argument(
        "--no-splash", action="store_true",
        help="Don't show splash screen."
    )
    parser.add_argument(
        "-l", "--log-level",
        help="Logging level (0, 1, 2, 3, 4)", type=log_level,
        default=logging.ERROR,
    )
    parser.add_argument(
        "--stylesheet",
        help="Application level CSS style sheet to use", type=str, default=None
    )
    parser.add_argument(
        "--config", help="Configuration namespace",
        type=str, default=None,
    )

    deprecated = parser.add_argument_group("Deprecated")
    deprecated.add_argument(
        "--qt", help="Additional arguments for QApplication.\nDeprecated. "
        "List all arguments as normally to pass it to QApplication.",
        type=str, default=None
    )
    deprecated.add_argument(
        "--style", help="QStyle to use (deprecated: use -style)",
        type=str, default=None
    )
    return parser


def main(argv=None):
    return Main().run(argv)


if __name__ == "__main__":
    sys.exit(main())

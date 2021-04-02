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

from urllib.request import getproxies
from contextlib import ExitStack, redirect_stdout, redirect_stderr, closing

from AnyQt.QtGui import QFont, QColor
from AnyQt.QtCore import Qt, QSettings


from .utils.after_exit import run_after_exit
from .styles import breeze_dark as _breeze_dark
from .application.application import CanvasApplication
from .application.canvasmain import CanvasMainWindow
from .application.outputview import TextStream, ExceptHook

from . import utils, config
from .gui.splashscreen import SplashScreen
from .gui.utils import macos_set_nswindow_tabbing as _macos_set_nswindow_tabbing

from .registry import WidgetDiscovery, WidgetRegistry, set_global_registry
from .registry import cache

log = logging.getLogger(__name__)


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


def setuplogging(
        level=logging.ERROR,
        filename='',
        config={},
):
    stream_handler = make_stream_handler(
        level
    )
    stream_handler.setLevel(level)


def parse_args(argv):
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
        type=str, default="orangecanvas.example"
    )
    grp = parser.add_argument_group("Theme")

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
    ns, rest = parser.parse_known_args(argv)
    if ns.style is not None:
        rest = ["-style", ns.style] + rest
    if ns.qt is not None:
        rest = shlex.split(ns.qt) + rest
    return ns, rest


def main(argv=None):
    if argv is None:
        argv = sys.argv

    options, argv_rest = parse_args(argv)

    # Fix streams before configuring logging (otherwise it will store
    # and write to the old file descriptors)
    fix_win_pythonw_std_stream()

    # Set http_proxy environment variable(s) for some clients
    fix_set_proxy_env()

    setuplogging(options.log_level,)

    # File handler should always be at least INFO level so we need
    # the application root level to be at least at INFO.
    root_level = min(options.log_level, logging.INFO)
    rootlogger = logging.getLogger(__package__)
    rootlogger.setLevel(root_level)

    # Standard output stream handler at the requested level
    stream_hander = logging.StreamHandler()
    stream_hander.setLevel(options.log_level)
    rootlogger.addHandler(stream_hander)

    if options.config is not None:
        try:
            cfg = utils.name_lookup(options.config)
        except (ImportError, AttributeError):
            pass
        else:
            config.set_default(cfg())

    config.init()

    qapp_argv = argv[:1] + argv_rest
    app = CanvasApplication(qapp_argv)
    argv = app.arguments()

    file_handler = logging.FileHandler(
        filename=os.path.join(config.log_dir(), "canvas.log"),
        mode="w"
    )
    file_handler.setLevel(root_level)
    rootlogger.addHandler(file_handler)

    settings = QSettings()

    if not options.force_discovery:
        reg_cache = cache.registry_cache()
    else:
        reg_cache = None

    widget_registry = WidgetRegistry()
    handler = WidgetDiscovery.RegistryHandler(widget_registry)
    widget_discovery = config.widget_discovery(
        handler, cached_descriptions=reg_cache
    )

    want_splash = \
        settings.value("startup/show-splash-screen", True, type=bool) and \
        not options.no_splash

    if want_splash:
        pm, rect = config.splash_screen()
        splash_screen = SplashScreen(pixmap=pm, textRect=rect)
        splash_screen.setAttribute(Qt.WA_DeleteOnClose)
        splash_screen.setFont(QFont("Helvetica", 12))
        color = QColor("#FFD39F")

        def show_message(message):
            splash_screen.showMessage(message, color=color)

        # widget_registry.category_added.connect(show_message)
        show_splash = splash_screen.show
        close_splash = splash_screen.close
    else:
        show_splash = close_splash = lambda: None

    log.info("Running widget discovery process.")

    cache_filename = os.path.join(config.cache_dir(), "widget-registry.pck")
    if options.no_discovery:
        with open(cache_filename, "rb") as f:
            widget_registry = pickle.load(f)
        widget_registry = WidgetRegistry(widget_registry)
    else:
        show_splash()
        widget_discovery.run(config.widgets_entry_points())
        close_splash()

        # Store cached descriptions
        cache.save_registry_cache(widget_discovery.cached_descriptions)
        with open(cache_filename, "wb") as f:
            pickle.dump(WidgetRegistry(widget_registry), f)

    set_global_registry(widget_registry)

    canvas_window = CanvasMainWindow()
    canvas_window.setAttribute(Qt.WA_DeleteOnClose)

    canvas_window.setWindowIcon(config.application_icon())
    canvas_window.set_widget_registry(widget_registry)
    canvas_window.show()
    canvas_window.raise_()

    want_welcome = \
        settings.value("startup/show-welcome-screen", True, type=bool) \
        and not options.no_welcome

    # TODO: Document manager...
    app.fileOpenRequest.connect(canvas_window.open_scheme_file)

    if want_welcome and not argv:
        # trigger the welcome dlg action.
        canvas_window.welcome_dialog()
    elif argv:
        # TODO: Could load multiple files
        log.info("Loading a workflow from the command line argument %r", argv[0])
        canvas_window.load_scheme(argv[0])

    # Tee stdout and stderr into Output dock
    output_view = canvas_window.output_view()
    output_doc = output_view.document()
    stdout = TextStream()
    stderr = TextStream()

    if sys.stdout:
        stdout.stream.connect(sys.stdout.write)
        stdout.flushed.connect(sys.stdout.flush)

    if sys.stderr:
        stderr.stream.connect(sys.stderr.write)
        stderr.flushed.connect(sys.stderr.flush)

    output_doc.connectStream(stdout)
    output_doc.connectStream(stderr, color=Qt.red)

    with ExitStack() as stack:
        stack.enter_context(closing(stderr))
        stack.enter_context(closing(stdout))
        stack.enter_context(redirect_stdout(stdout))
        stack.enter_context(redirect_stderr(stderr))
        log.info("Entering main event loop.")
        sys.excepthook = ExceptHook(stream=stderr)
        try:
            status = app.exec()
        finally:
            sys.excepthook = sys.__excepthook__

    del canvas_window

    app.processEvents()

    # Collect any cycles before deleting the QApplication instance
    gc.collect()

    del app

    if status == 96:
        log.info('Restarting via exit code 96.')
        run_after_exit([sys.executable, sys.argv[0]])

    return status


if __name__ == "__main__":
    sys.exit(main())

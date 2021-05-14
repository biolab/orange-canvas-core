import logging
import unittest
from contextlib import contextmanager
from functools import wraps
from typing import Iterable
from unittest.mock import patch, Mock

from orangecanvas import config
from orangecanvas.application.canvasmain import CanvasMainWindow
from orangecanvas.config import Config, EntryPoint
from orangecanvas.gui.test import QAppTestCase
from orangecanvas.main import Main
from orangecanvas.registry import WidgetDiscovery
from orangecanvas.registry.tests import set_up_modules, tear_down_modules
from orangecanvas.scheme import Scheme
from orangecanvas.utils.shtools import temp_named_file


class TestMain(unittest.TestCase):
    def test_params(self):
        m = Main()
        m.parse_arguments(["-", "--config", "foo.bar", "that"])
        self.assertEqual(m.arguments, ["that"])
        self.assertEqual(m.options.config, "foo.bar")
        m = Main()
        m.parse_arguments(["-", "-l3"])
        self.assertEqual(m.options.log_level, logging.WARNING)
        m = Main()
        m.parse_arguments(["-", "-l", "warn"])
        self.assertEqual(m.options.log_level, logging.WARNING)

    def test_style_param_compat(self):
        # test old '--style' parameter handling
        m = Main()
        m.parse_arguments(["-", "--style", "windows"])
        self.assertEqual(m.arguments, ["-style", "windows"])

        m = Main()
        m.parse_arguments(["-", "--qt", "-stylesheet path.qss"])
        self.assertEqual(m.arguments, ["-stylesheet", "path.qss"])

    def test_main_argument_parser(self):
        class Main2(Main):
            def argument_parser(self):
                p = super().argument_parser()
                p.add_argument("--foo", type=str, default=None)
                return p
        m = Main2()
        m.parse_arguments(["-", "-l", "warn", "--foo", "bar"])
        self.assertEqual(m.options.foo, "bar")


@contextmanager
def patch_main_application(app):
    def setup_application(self: Main):
        self.application = app
    with patch.object(Main, "setup_application",  setup_application):
        yield


def with_patched_main_application(f):
    @wraps(f)
    def wrapped(self: QAppTestCase, *args, **kwargs):
        with patch_main_application(self.app):
            return f(self, *args, **kwargs)
    return wrapped


class TestConfig(Config):
    def init(self):
        return

    def widget_discovery(self, *args, **kwargs):
        return WidgetDiscovery(*args, **kwargs)

    def widgets_entry_points(self):  # type: () -> Iterable[EntryPoint]
        pkg = "orangecanvas.registry.tests"
        return (
            EntryPoint.parse(f"add = {pkg}.operators.add"),
            EntryPoint.parse(f"sub = {pkg}.operators.sub")
        )

    def workflow_constructor(self, *args, **kwargs):
        return Scheme(*args, **kwargs)


class TestMainGuiCase(QAppTestCase):
    def setUp(self):
        super().setUp()
        self.app.fileOpenRequest = Mock()
        self._config = config.default
        set_up_modules()

    def tearDown(self):
        tear_down_modules()
        config.default = self._config
        del self.app.fileOpenRequest
        del self._config
        super().tearDown()

    @with_patched_main_application
    def test_main_show_splash_screen(self):
        m = Main()
        m.parse_arguments(["-", "--config", f"{__name__}.TestConfig"])
        m.activate_default_config()
        m.show_splash_message("aa")
        m.close_splash_screen()

    @with_patched_main_application
    def test_discovery(self):
        m = Main()
        m.parse_arguments(["-", "--config", f"{__name__}.TestConfig"])
        m.activate_default_config()
        m.run_discovery()
        self.assertTrue(bool(m.registry.widgets()))
        self.assertTrue(bool(m.registry.categories()))

    @with_patched_main_application
    def test_run(self):
        m = Main()
        with patch.object(self.app, "exec", lambda: 42):
            res = m.run(["-", "--no-welcome", "--no-splash"])
        self.assertEqual(res, 42)

    @with_patched_main_application
    def test_run(self):
        m = Main()
        with patch.object(self.app, "exec", lambda: 42), \
             patch.object(CanvasMainWindow, "open_scheme_file", Mock()), \
             temp_named_file('<scheme version="2.0"></scheme>') as fname:
            res = m.run(["-", "--no-welcome", "--no-splash", fname])
            CanvasMainWindow.open_scheme_file.assert_called_with(fname)
        self.assertEqual(res, 42)

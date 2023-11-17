"""
Test widget discovery

"""
import logging
import types

import unittest
from unittest.mock import patch

from ..discovery import WidgetDiscovery, widget_descriptions_from_package
from ..description import CategoryDescription, WidgetDescription
from ..utils import category_from_package_globals
from ...utils.pkgmeta import get_distribution


class TestDiscovery(unittest.TestCase):

    def setUp(self):
        logging.basicConfig()
        from . import set_up_modules, operators, constants
        set_up_modules()
        self.operators = operators
        self.constants = constants

    def tearDown(self):
        from . import tear_down_modules
        tear_down_modules()

    def discovery_class(self):
        return WidgetDiscovery()

    def test_handle(self):
        disc = self.discovery_class()

        desc = CategoryDescription(name="C", qualified_name="M.C")
        disc.handle_category(desc)

        desc = WidgetDescription(name="SomeWidget", id="some.widget",
                                 qualified_name="Some.Widget",
                                 category="C",)
        disc.handle_widget(desc)

    def test_process_module(self):
        disc = self.discovery_class()
        dist = get_distribution("orange-canvas-core")
        disc.process_category_package(self.operators.__name__, distribution=dist)
        disc.process_widget_module(self.constants.one.__name__, distribution=dist)

    def test_process_loader(self):
        disc = self.discovery_class()

        def callable(discovery):
            desc = CategoryDescription(
                name="Data", qualified_name="Data")

            discovery.handle_category(desc)

            desc = WidgetDescription(
                name="CSV", id="some.id", qualified_name="Some.widget",
                inputs=[], category="Data",
            )
            discovery.handle_widget(desc)

        disc.process_loader(callable)

    def test_process_iter(self):
        disc = self.discovery_class()
        cat_desc = category_from_package_globals(
            self.operators.__name__,
        )
        modules = [
            (None, self.operators.add.__name__, False)
        ]
        with patch("pkgutil.iter_modules", lambda *_, **__: modules):
            wid_desc = widget_descriptions_from_package(
                self.operators.__name__,
            )
            disc.process_iter([cat_desc] + wid_desc)

    def test_process_category_package(self):
        disc = self.discovery_class()
        dist = get_distribution("orange-canvas-core")
        modules = [
            (None, self.operators.add.__name__, False)
        ]
        self.operators.__path__ = ["aaa"]
        with patch("pkgutil.iter_modules", lambda *_, **__: modules):
            disc.process_category_package(self.operators, distribution=dist)

    def test_run(self):
        disc = self.discovery_class()
        disc.run("example.does.not.exist.but.it.does.not.matter.")

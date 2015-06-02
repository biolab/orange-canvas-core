"""
Test widget discovery

"""

import os
import logging

import unittest

from ..discovery import WidgetDiscovery, widget_descriptions_from_package

from ..description import CategoryDescription, WidgetDescription


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
        disc.process_category_package(self.operators.__name__)
        disc.process_widget_module(self.constants.one.__name__)

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
        cat_desc = CategoryDescription.from_package(
            self.operators.__name__,
        )
        # TODO: Fix (the widget_description_package does not iterate
        # over faked package (no valid operator.__path__)
        wid_desc = widget_descriptions_from_package(
            self.operators.__name__,
        )
        disc.process_iter([cat_desc] + wid_desc)

    def test_run(self):
        disc = self.discovery_class()
        disc.run("example.does.not.exist.but.it.does.not.matter.")

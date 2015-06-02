"""
Test WidgetRegistry.
"""
import logging
from operator import attrgetter

import unittest

from ..base import WidgetRegistry
from .. import description


class TestRegistry(unittest.TestCase):
    def setUp(self):
        logging.basicConfig()
        from . import set_up_modules
        set_up_modules()

        from . import constants
        from . import operators
        self.constants = constants
        self.operators = operators

    def tearDown(self):
        from . import tear_down_modules
        tear_down_modules()

    def test_registry_const(self):
        reg = WidgetRegistry()

        const_cat = description.CategoryDescription.from_package(
            self.constants.__name__)
        reg.register_category(const_cat)

        zero_desc = description.WidgetDescription.from_module(
            self.constants.zero.__name__)

        reg.register_widget(zero_desc)

        self.assertTrue(reg.has_widget(zero_desc.qualified_name))
        self.assertSequenceEqual(reg.widgets(self.constants.NAME), [zero_desc])
        self.assertIs(reg.widget(zero_desc.qualified_name), zero_desc)

        # ValueError adding a description with the same qualified name
        with self.assertRaises(ValueError):
            desc = description.WidgetDescription(
                name="A name",
                id=zero_desc.id,
                qualified_name=zero_desc.qualified_name
            )
            reg.register_widget(desc)

        one_desc = description.WidgetDescription.from_module(
            self.constants.one)
        reg.register_widget(one_desc)

        self.assertTrue(reg.has_widget(one_desc.qualified_name))
        self.assertIs(reg.widget(one_desc.qualified_name), one_desc)

        self.assertSetEqual(set(reg.widgets(self.constants.NAME)),
                            set([zero_desc, one_desc]))

        op_cat = description.CategoryDescription.from_package(
            self.operators.__name__)
        reg.register_category(op_cat)

        self.assertTrue(reg.has_category(op_cat.name))
        self.assertIs(reg.category(op_cat.name), op_cat)
        self.assertSetEqual(set(reg.categories()),
                            set([const_cat, op_cat]))

        add_desc = description.WidgetDescription.from_module(
            self.operators.add
        )
        reg.register_widget(add_desc)

        self.assertTrue(reg.has_widget(add_desc.qualified_name))
        self.assertIs(reg.widget(add_desc.qualified_name), add_desc)
        self.assertSequenceEqual(reg.widgets(self.operators.NAME), [add_desc])

        sub_desc = description.WidgetDescription.from_module(
            self.operators.sub)

        reg.register_widget(sub_desc)

        # Test copy constructor
        reg1 = WidgetRegistry(reg)
        self.assertTrue(reg1.has_category(const_cat.name))
        self.assertTrue(reg1.has_category(op_cat.name))
        self.assertSequenceEqual(reg.categories(), reg1.categories())

        # Test 'widgets()'
        self.assertSetEqual(set(reg1.widgets()),
                            set([zero_desc, one_desc, add_desc, sub_desc]))

        # Test ordering by priority
        self.assertSequenceEqual(
             reg.widgets(op_cat.name),
             sorted([add_desc, sub_desc],
                    key=attrgetter("priority"))
        )

        self.assertTrue(all(isinstance(desc.priority, int)
                            for desc in [one_desc, zero_desc, sub_desc,
                                         add_desc])
                        )

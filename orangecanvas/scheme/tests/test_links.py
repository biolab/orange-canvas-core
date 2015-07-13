"""
Tests for SchemeLink
"""

from ...gui import test
from ...registry.tests import small_testing_registry

from .. import SchemeNode, SchemeLink, IncompatibleChannelTypeError


class TestSchemeLink(test.QAppTestCase):
    def test_link(self):
        reg = small_testing_registry()
        one_desc = reg.widget("one")
        add_desc = reg.widget("add")
        unit_desc = reg.widget("unit")

        one_node = SchemeNode(one_desc)
        add_node = SchemeNode(add_desc)
        unit_node = SchemeNode(unit_desc)

        link1 = SchemeLink(one_node, one_node.output_channel("value"),
                           add_node,
                           add_node.input_channel("left"))

        self.assertTrue(link1.source_type() is int)
        self.assertTrue(link1.sink_type() is int)

        with self.assertRaises(ValueError):
            SchemeLink(add_node, "right", one_node, "$$$[")

        with self.assertRaises(IncompatibleChannelTypeError):
            SchemeLink(unit_node, "value", add_node, "right")

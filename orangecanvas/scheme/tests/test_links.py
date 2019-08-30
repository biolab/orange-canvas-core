"""
Tests for SchemeLink
"""
import warnings

from ...gui import test
from ...registry.tests import small_testing_registry

from ...registry.description import InputSignal, OutputSignal, Dynamic

from .. import SchemeNode, SchemeLink, IncompatibleChannelTypeError
from ..link import resolved_valid_types, _classify_connection


class A:
    pass


class B(A):
    pass


class C:
    pass


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

        self.assertEqual(link1.source_types(), (int, ))
        self.assertEqual(link1.sink_types(), (int, ))

        with self.assertRaises(ValueError):
            SchemeLink(add_node, "right", one_node, "$$$[")

        with self.assertRaises(IncompatibleChannelTypeError):
            SchemeLink(unit_node, "value", add_node, "right")

    def test_utils(self):
        with warnings.catch_warnings(record=True):
            self.assertTupleEqual(
                resolved_valid_types(("int", __name__ + ".NoSuchType", "str")),
                (int, str),
            )

        source = OutputSignal("A", (A,))
        source_d = OutputSignal("A", (A,), flags=Dynamic)
        source_ac_d = OutputSignal("A", (A, C), flags=Dynamic)
        source_ac = OutputSignal("A", (B, C))
        sink_a = InputSignal("A", (A,), "a")
        sink_b = InputSignal("B", (B,), "b")
        sink_c = InputSignal("C", (C,), "c")
        sink_bc = InputSignal("C", (B, C,), "c")

        t1, t2 = _classify_connection(source, sink_a)
        self.assertTrue(t1)
        self.assertFalse(t2)

        t1, t2 = _classify_connection(source, sink_b)
        self.assertFalse(t1)
        self.assertFalse(t2)

        t1, t2 = _classify_connection(source_d, sink_b)
        self.assertFalse(t1)
        self.assertTrue(t2)

        t1, t2 = _classify_connection(source_d, sink_a)
        self.assertTrue(t1)
        self.assertTrue(t2)

        t1, t2 = _classify_connection(source_d, sink_c)
        self.assertFalse(t1)
        self.assertFalse(t2)

        t1, t2 = _classify_connection(source_d, sink_bc)
        self.assertFalse(t1)
        self.assertTrue(t2)

        t1, t2 = _classify_connection(source_ac_d, sink_bc)
        self.assertFalse(t1)
        self.assertTrue(t2)

        t1, t2 = _classify_connection(source_ac, sink_bc)
        self.assertTrue(t1)
        self.assertFalse(t2)

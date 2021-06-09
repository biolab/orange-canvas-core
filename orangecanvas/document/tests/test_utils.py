import unittest

from ..utils import prepare_macro_patch
from ...registry.tests import small_testing_registry
from ...scheme import Workflow, SchemeNode, Link


class TestMacroUtils(unittest.TestCase):
    @staticmethod
    def setup_test_workflow():
        workflow = Workflow()
        reg = small_testing_registry()

        zero_desc = reg.widget("zero")
        one_desc = reg.widget("one")
        add_desc = reg.widget("add")
        negate = reg.widget("negate")

        zero_node = SchemeNode(zero_desc)
        one_node = SchemeNode(one_desc)
        add_node_1 = SchemeNode(add_desc)
        add_node_2 = SchemeNode(add_desc)
        negate_node_1 = SchemeNode(negate)
        negate_node_2 = SchemeNode(negate)

        workflow.add_node(zero_node)
        workflow.add_node(one_node)
        workflow.add_node(add_node_1)
        workflow.add_node(add_node_2)
        workflow.add_node(negate_node_1)
        workflow.add_node(negate_node_2)

        workflow.add_link(Link(zero_node, "value", add_node_1, "left"))
        workflow.add_link(Link(one_node, "value", add_node_1, "right"))
        workflow.add_link(Link(zero_node, "value", add_node_2, "left"))
        workflow.add_link(Link(add_node_1, "result", add_node_2, "right"))
        workflow.add_link(Link(add_node_1, "result", negate_node_1, "value"))
        workflow.add_link(Link(add_node_2, "result", negate_node_2, "value"))
        return workflow

    def test_prepare_macro_patch(self):
        workflow = self.setup_test_workflow()
        root = workflow.root()
        n1, n2, n3, n4, n5, n6 = root.nodes()
        l1, l2, l3, l4, l5, l6 = root.links()
        res = prepare_macro_patch(root, [n2, n3, n4])
        self.assertEqual(res.nodes, [n2, n3, n4])
        self.assertSetEqual(set(res.removed_links), {l1, l2, l3, l4, l5, l6})
        li1, li2 = res.input_links
        self.assertIs(li1.source_node, n1)
        self.assertIs(li2.source_node, n1)
        self.assertIsNotNone(li1.sink_channel, li2.sink_channel)
        self.assertEqual(li1.sink_channel.name, "left (1)")
        self.assertEqual(li2.sink_channel.name, "left (2)")

        lo1, lo2 = res.output_links
        self.assertIs(lo1.sink_node, n5)
        self.assertIs(lo2.sink_node, n6)
        self.assertEqual(lo1.source_channel.name, "result (1)")
        self.assertEqual(lo2.source_channel.name, "result (2)")

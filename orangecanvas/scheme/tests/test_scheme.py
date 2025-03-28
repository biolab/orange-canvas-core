"""
Tests for Scheme
"""
from AnyQt.QtTest import QSignalSpy

from ...gui import test
from ...registry.tests import small_testing_registry
from ...registry import InputSignal

from .. import (
    Scheme, SchemeNode, SchemeLink, SchemeTextAnnotation,
    SchemeArrowAnnotation, SchemeTopologyError, SinkChannelError,
    DuplicatedLinkError, IncompatibleChannelTypeError, MetaNode, Link, Text
)


class TestScheme(test.QCoreAppTestCase):
    def test_scheme(self):
        reg = small_testing_registry()
        one_desc = reg.widget("one")
        add_desc = reg.widget("add")
        cons_desc = reg.widget("cons")
        # Create the scheme
        scheme = Scheme()

        self.assertEqual(scheme.title, "")
        self.assertEqual(scheme.description, "")

        nodes_added = []
        links_added = []
        annotations_added = []

        scheme.node_added.connect(nodes_added.append)
        scheme.node_removed.connect(nodes_added.remove)

        scheme.link_added.connect(links_added.append)
        scheme.link_removed.connect(links_added.remove)

        scheme.annotation_added.connect(annotations_added.append)
        scheme.annotation_removed.connect(annotations_added.remove)

        w1 = scheme.new_node(one_desc)
        self.assertTrue(len(nodes_added) == 1)
        self.assertTrue(isinstance(nodes_added[-1], SchemeNode))
        self.assertTrue(nodes_added[-1] is w1)

        w2 = scheme.new_node(add_desc)
        self.assertTrue(len(nodes_added) == 2)
        self.assertTrue(isinstance(nodes_added[-1], SchemeNode))
        self.assertTrue(nodes_added[-1] is w2)

        w3 = scheme.new_node(cons_desc)
        self.assertTrue(len(nodes_added) == 3)
        self.assertTrue(isinstance(nodes_added[-1], SchemeNode))
        self.assertTrue(nodes_added[-1] is w3)

        self.assertTrue(len(links_added) == 0)
        l1 = SchemeLink(w1, "value", w2, "left")
        scheme.add_link(l1)
        self.assertTrue(len(links_added) == 1)
        self.assertTrue(isinstance(links_added[-1], SchemeLink))
        self.assertTrue(links_added[-1] is l1)

        l2 = SchemeLink(w1, "value", w3, "first")
        scheme.add_link(l2)
        self.assertTrue(len(links_added) == 2)
        self.assertTrue(isinstance(links_added[-1], SchemeLink))
        self.assertTrue(links_added[-1] is l2)

        # Test find_links.
        found = scheme.find_links(w1, None, w2, None)
        self.assertSequenceEqual(found, [l1])
        found = scheme.find_links(None, None, w3, None)
        self.assertSequenceEqual(found, [l2])

        scheme.remove_link(l2)
        self.assertTrue(l2 not in links_added)

        # Add a link to itself.
        self.assertRaises(SchemeTopologyError, scheme.new_link,
                          w2, "result", w2, "right")

        # Add an link with incompatible types
        self.assertRaises(IncompatibleChannelTypeError,
                          scheme.new_link, w3, "cons", w2, "right")

        # Add a link to a node with no input channels
        self.assertRaises(ValueError, scheme.new_link,
                          w2, "result", w1, "foo")

        # add back l2 for the following checks
        scheme.add_link(l2)

        # Add a duplicate link
        self.assertRaises(DuplicatedLinkError, scheme.new_link,
                          w1, "value", w3, "first")

        # Add a link to an already connected sink channel
        self.assertRaises(SinkChannelError, scheme.new_link,
                          w2, "result", w3, "first")

        text_annot = SchemeTextAnnotation((0, 0, 100, 20), "Text")
        scheme.add_annotation(text_annot)
        self.assertSequenceEqual(annotations_added, [text_annot])
        self.assertSequenceEqual(scheme.root().annotations(), annotations_added)

        arrow_annot = SchemeArrowAnnotation((0, 100), (100, 100))
        scheme.add_annotation(arrow_annot)
        self.assertSequenceEqual(annotations_added, [text_annot, arrow_annot])
        self.assertSequenceEqual(scheme.root().annotations(), annotations_added)

        scheme.remove_annotation(text_annot)
        self.assertSequenceEqual(annotations_added, [arrow_annot])
        self.assertSequenceEqual(scheme.root().annotations(), annotations_added)

    def test_insert_node(self):
        reg = small_testing_registry()
        one_desc = reg.widget("one")
        n1, n2 = SchemeNode(one_desc), SchemeNode(one_desc)
        w = Scheme()
        r = w.root()
        spy = QSignalSpy(w.node_inserted)
        w.add_node(n1)
        w.insert_node(0, n2)
        self.assertSequenceEqual(list(spy), [[0, n1, r], [0, n2, r]])
        self.assertSequenceEqual(w.root().nodes(), [n2, n1])

    def test_insert_link(self):
        reg = small_testing_registry()
        one_desc = reg.widget("one")
        add_desc = reg.widget("add")
        n1, n2, n3 = SchemeNode(one_desc), SchemeNode(one_desc), SchemeNode(add_desc)
        w = Scheme()
        r = w.root()
        spy = QSignalSpy(w.link_inserted)
        w.add_node(n1)
        w.add_node(n2)
        w.add_node(n3)
        l1 = SchemeLink(n1, "value", n3, "left")
        l2 = SchemeLink(n2, "value", n3, "right")
        w.add_link(l1)
        w.insert_link(0, l2)
        self.assertSequenceEqual(list(spy), [[0, l1, r], [0, l2, r]])
        self.assertSequenceEqual(w.root().links(), [l2, l1])

    def test_insert_annotation(self):
        w = Scheme()
        r = w.root()
        a1 = SchemeTextAnnotation((0, 0, 1, 1), "a1")
        a2 = SchemeTextAnnotation((0, 0, 1, 1), "a2")
        a3 = SchemeTextAnnotation((0, 0, 1, 1), "a3")
        spy = QSignalSpy(w.annotation_inserted)
        w.insert_annotation(0, a1)
        w.insert_annotation(1, a2)
        w.insert_annotation(0, a3)
        self.assertSequenceEqual(w.root().annotations(), [a3, a1, a2])
        self.assertSequenceEqual(list(spy), [[0, a1, r], [1, a2, r], [0, a3, r]])

    def test_meta_nodes(self):
        w = Scheme()
        reg = small_testing_registry()
        one_desc = reg.widget("one")
        add_desc = reg.widget("add")
        neg_desc = reg.widget("negate")
        n1, n2, n3 = SchemeNode(one_desc), SchemeNode(one_desc), SchemeNode(add_desc)
        macro = MetaNode("Plus One")
        w.add_node(macro)
        self.assertIs(macro.parent_node(), w.root())
        w.add_node(n1)
        macro.add_node(n2)
        macro.add_node(n3)
        macro.add_link(Link(n2, "value", n3, "right"))
        input = InputSignal("value", int, "-")
        nodein = macro.create_input_node(input)
        macro.add_link(Link(nodein, nodein.output_channels()[0], n3, "left"))
        nodeout = macro.create_output_node(add_desc.outputs[0])
        macro.add_link(Link(n3, n3.output_channels()[0],
                            nodeout, nodeout.input_channels()[0]))
        macro.add_annotation(Text((0, 0, 200, 200), "Add one"), )
        w.add_link(Link(n1, "value", macro, "value"))

        n4 = SchemeNode(neg_desc)
        w.add_node(n4)
        w.add_link(Link(macro, "result", n4, "value"))
        self.assertIn(n4, w.downstream_nodes(n1))
        self.assertIn(n3, w.downstream_nodes(n1))
        self.assertIn(n4, w.downstream_nodes(n2))

        self.assertIn(n2, w.upstream_nodes(n4))
        self.assertIn(n3, w.upstream_nodes(n4))
        self.assertIn(n1, w.upstream_nodes(n4))
        w.clear()

"""
Tests for Scheme
"""
from AnyQt.QtTest import QSignalSpy

from ...gui import test
from ...registry.tests import small_testing_registry

from .. import (
    Scheme, SchemeNode, SchemeLink, SchemeTextAnnotation,
    SchemeArrowAnnotation, SchemeTopologyError, SinkChannelError,
    DuplicatedLinkError, IncompatibleChannelTypeError
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
        self.assertSequenceEqual(scheme.annotations, annotations_added)

        arrow_annot = SchemeArrowAnnotation((0, 100), (100, 100))
        scheme.add_annotation(arrow_annot)
        self.assertSequenceEqual(annotations_added, [text_annot, arrow_annot])
        self.assertSequenceEqual(scheme.annotations, annotations_added)

        scheme.remove_annotation(text_annot)
        self.assertSequenceEqual(annotations_added, [arrow_annot])
        self.assertSequenceEqual(scheme.annotations, annotations_added)

    def test_insert_node(self):
        reg = small_testing_registry()
        one_desc = reg.widget("one")
        n1, n2 = SchemeNode(one_desc), SchemeNode(one_desc)
        w = Scheme()
        spy = QSignalSpy(w.node_inserted)
        w.add_node(n1)
        w.insert_node(0, n2)
        self.assertSequenceEqual(list(spy), [[0, n1], [0, n2]])
        self.assertSequenceEqual(w.nodes, [n2, n1])

    def test_insert_link(self):
        reg = small_testing_registry()
        one_desc = reg.widget("one")
        add_desc = reg.widget("add")
        n1, n2, n3 = SchemeNode(one_desc), SchemeNode(one_desc), SchemeNode(add_desc)
        w = Scheme()
        spy = QSignalSpy(w.link_inserted)
        w.add_node(n1)
        w.add_node(n2)
        w.add_node(n3)
        l1 = SchemeLink(n1, "value", n3, "left")
        l2 = SchemeLink(n2, "value", n3, "right")
        w.add_link(l1)
        w.insert_link(0, l2)
        self.assertSequenceEqual(list(spy), [[0, l1], [0, l2]])
        self.assertSequenceEqual(w.links, [l2, l1])

    def test_insert_annotation(self):
        w = Scheme()
        a1 = SchemeTextAnnotation((0, 0, 1, 1), "a1")
        a2 = SchemeTextAnnotation((0, 0, 1, 1), "a2")
        a3 = SchemeTextAnnotation((0, 0, 1, 1), "a3")
        spy = QSignalSpy(w.annotation_inserted)
        w.insert_annotation(0, a1)
        w.insert_annotation(1, a2)
        w.insert_annotation(0, a3)
        self.assertSequenceEqual(w.annotations, [a3, a1, a2])
        self.assertSequenceEqual(list(spy), [[0, a1], [1, a2], [0, a3]])

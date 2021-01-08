from AnyQt.QtWidgets import QGraphicsView
from AnyQt.QtGui import QPainter

from ..scene import CanvasScene
from .. import items
from ... import scheme
from ...registry.tests import small_testing_registry
from ...gui.test import QAppTestCase


class TestScene(QAppTestCase):
    def setUp(self):
        super().setUp()
        self.scene = CanvasScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(QPainter.Antialiasing |
                                 QPainter.TextAntialiasing)
        self.view.show()
        self.view.resize(400, 300)

    def tearDown(self):
        self.scene.clear()
        self.view.deleteLater()
        self.scene.deleteLater()
        del self.view
        del self.scene
        super().tearDown()

    def test_scene(self):
        """Test basic scene functionality.
        """
        one_desc, negate_desc, cons_desc = self.widget_desc()

        one_item = items.NodeItem(one_desc)
        negate_item = items.NodeItem(negate_desc)
        cons_item = items.NodeItem(cons_desc)

        one_item = self.scene.add_node_item(one_item)
        negate_item = self.scene.add_node_item(negate_item)
        cons_item = self.scene.add_node_item(cons_item)

        # Remove a node
        self.scene.remove_node_item(cons_item)
        self.assertSequenceEqual(self.scene.node_items(),
                                 [one_item, negate_item])

        # And add it again
        self.scene.add_node_item(cons_item)
        self.assertSequenceEqual(self.scene.node_items(),
                                 [one_item, negate_item, cons_item])

        # Adding the same item again should raise an exception
        with self.assertRaises(ValueError):
            self.scene.add_node_item(cons_item)

        a1 = one_desc.outputs[0]
        a2 = negate_desc.inputs[0]
        a3 = negate_desc.outputs[0]
        a4 = cons_desc.inputs[0]

        # Add links
        link1 = self.scene.new_link_item(
            one_item, a1, negate_item, a2)
        link2 = self.scene.new_link_item(
            negate_item, a3, cons_item, a4)

        link1a = self.scene.add_link_item(link1)
        link2a = self.scene.add_link_item(link2)
        self.assertEqual(link1, link1a)
        self.assertEqual(link2, link2a)
        self.assertSequenceEqual(self.scene.link_items(), [link1, link2])

        # Remove links
        self.scene.remove_link_item(link2)
        self.scene.remove_link_item(link1)
        self.assertSequenceEqual(self.scene.link_items(), [])

        self.assertTrue(link1.sourceItem is None and link1.sinkItem is None)
        self.assertTrue(link2.sourceItem is None and link2.sinkItem is None)

        self.assertSequenceEqual(one_item.outputAnchors(), [])
        self.assertSequenceEqual(negate_item.inputAnchors(), [])
        self.assertSequenceEqual(negate_item.outputAnchors(), [])
        self.assertSequenceEqual(cons_item.outputAnchors(), [])

        # And add one link again
        link1 = self.scene.new_link_item(
            one_item, a1, negate_item, a2)
        link1 = self.scene.add_link_item(link1)
        self.assertSequenceEqual(self.scene.link_items(), [link1])

        self.assertTrue(one_item.outputAnchors())
        self.assertTrue(negate_item.inputAnchors())

        self.qWait()

    def test_scene_with_scheme(self):
        """Test scene through modifying the scheme.
        """
        test_scheme = scheme.Scheme()
        self.scene.set_scheme(test_scheme)

        node_items = []
        link_items = []

        self.scene.node_item_added.connect(node_items.append)
        self.scene.node_item_removed.connect(node_items.remove)
        self.scene.link_item_added.connect(link_items.append)
        self.scene.link_item_removed.connect(link_items.remove)

        one_desc, negate_desc, cons_desc = self.widget_desc()
        one_node = scheme.SchemeNode(one_desc)
        negate_node = scheme.SchemeNode(negate_desc)
        cons_node = scheme.SchemeNode(cons_desc)

        nodes = [one_node, negate_node, cons_node]
        test_scheme.add_node(one_node)
        test_scheme.add_node(negate_node)
        test_scheme.add_node(cons_node)

        self.assertTrue(len(self.scene.node_items()) == 3)
        self.assertSequenceEqual(self.scene.node_items(), node_items)

        for node, item in zip(nodes, node_items):
            self.assertIs(item, self.scene.item_for_node(node))

        # Remove a widget
        test_scheme.remove_node(cons_node)
        self.assertTrue(len(self.scene.node_items()) == 2)
        self.assertSequenceEqual(self.scene.node_items(), node_items)

        # And add it again
        test_scheme.add_node(cons_node)
        self.assertTrue(len(self.scene.node_items()) == 3)
        self.assertSequenceEqual(self.scene.node_items(), node_items)

        # Add links
        link1 = test_scheme.new_link(one_node, "value", negate_node, "value")
        link2 = test_scheme.new_link(negate_node, "result", cons_node, "first")
        self.assertTrue(len(self.scene.link_items()) == 2)
        self.assertSequenceEqual(self.scene.link_items(), link_items)

        # Remove links
        test_scheme.remove_link(link1)
        test_scheme.remove_link(link2)
        self.assertTrue(len(self.scene.link_items()) == 0)
        self.assertSequenceEqual(self.scene.link_items(), link_items)

        # And add one link again
        test_scheme.add_link(link1)
        self.assertTrue(len(self.scene.link_items()) == 1)
        self.assertSequenceEqual(self.scene.link_items(), link_items)
        self.qWait()

    def test_scheme_construction(self):
        """Test construction (editing) of the scheme through the scene.
        """
        test_scheme = scheme.Scheme()
        self.scene.set_scheme(test_scheme)

        node_items = []
        link_items = []

        self.scene.node_item_added.connect(node_items.append)
        self.scene.node_item_removed.connect(node_items.remove)
        self.scene.link_item_added.connect(link_items.append)
        self.scene.link_item_removed.connect(link_items.remove)

        one_desc, negate_desc, cons_desc = self.widget_desc()
        one_node = scheme.SchemeNode(one_desc)

        one_item = self.scene.add_node(one_node)
        self.scene.commit_scheme_node(one_node)

        self.assertSequenceEqual(self.scene.node_items(), [one_item])
        self.assertSequenceEqual(node_items, [one_item])
        self.assertSequenceEqual(test_scheme.nodes, [one_node])

        negate_node = scheme.SchemeNode(negate_desc)
        cons_node = scheme.SchemeNode(cons_desc)

        negate_item = self.scene.add_node(negate_node)
        cons_item = self.scene.add_node(cons_node)

        self.assertSequenceEqual(self.scene.node_items(),
                                 [one_item, negate_item, cons_item])
        self.assertSequenceEqual(self.scene.node_items(), node_items)

        # The scheme is still the same.
        self.assertSequenceEqual(test_scheme.nodes, [one_node])

        # Remove items
        self.scene.remove_node(negate_node)
        self.scene.remove_node(cons_node)

        self.assertSequenceEqual(self.scene.node_items(), [one_item])
        self.assertSequenceEqual(node_items, [one_item])
        self.assertSequenceEqual(test_scheme.nodes, [one_node])

        # Add them again this time also in the scheme.
        negate_item = self.scene.add_node(negate_node)
        cons_item = self.scene.add_node(cons_node)

        self.scene.commit_scheme_node(negate_node)
        self.scene.commit_scheme_node(cons_node)

        self.assertSequenceEqual(self.scene.node_items(),
                                 [one_item, negate_item, cons_item])
        self.assertSequenceEqual(self.scene.node_items(), node_items)
        self.assertSequenceEqual(test_scheme.nodes,
                                 [one_node, negate_node, cons_node])

        link1 = scheme.SchemeLink(one_node, "value", negate_node, "value")
        link2 = scheme.SchemeLink(negate_node, "result", cons_node, "first")
        link_item1 = self.scene.add_link(link1)
        link_item2 = self.scene.add_link(link2)

        self.assertSequenceEqual(self.scene.link_items(),
                                 [link_item1, link_item2])
        self.assertSequenceEqual(self.scene.link_items(), link_items)
        self.assertSequenceEqual(test_scheme.links, [])

        # Commit the links
        self.scene.commit_scheme_link(link1)
        self.scene.commit_scheme_link(link2)

        self.assertSequenceEqual(self.scene.link_items(),
                                 [link_item1, link_item2])
        self.assertSequenceEqual(self.scene.link_items(), link_items)
        self.assertSequenceEqual(test_scheme.links,
                                 [link1, link2])

        self.qWait()

    def widget_desc(self):
        reg = small_testing_registry()
        one_desc = reg.widget("one")
        negate_desc = reg.widget("negate")
        cons_desc = reg.widget("cons")
        return one_desc, negate_desc, cons_desc

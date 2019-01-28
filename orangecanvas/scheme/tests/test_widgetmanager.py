import unittest

from AnyQt.QtWidgets import QWidget, QApplication
from AnyQt.QtTest import QSignalSpy

from orangecanvas.scheme import Scheme
from orangecanvas.scheme.widgetmanager import WidgetManager
from orangecanvas.registry import tests as registry_tests


class TestingWidgetManager(WidgetManager):
    def create_widget_for_node(self, node):
        return QWidget()

    def delete_widget_for_node(self, node, widget):
        widget.deleteLater()


class TestWidgetManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        cls.app = app

    @classmethod
    def tearDownClass(cls):
        cls.app = None

    def setUp(self):
        reg = registry_tests.small_testing_registry()
        scheme = Scheme()
        zero = scheme.new_node(reg.widget("zero"))
        one = scheme.new_node(reg.widget("one"))
        add = scheme.new_node(reg.widget("add"))
        scheme.new_link(zero, "value", add, "left")
        scheme.new_link(one, "value", add, "right")

        self.scheme = scheme

    def test_create_immediate(self):
        wm = TestingWidgetManager()
        wm.set_creation_policy(TestingWidgetManager.Immediate)
        spy = QSignalSpy(wm.widget_for_node_added)
        wm.set_workflow(self.scheme)
        nodes = self.scheme.nodes
        self.assertTrue(len(spy) == 3)
        self.assertSetEqual({n for n, _ in spy}, set(nodes))
        spy = QSignalSpy(wm.widget_for_node_removed)
        self.scheme.clear()
        self.assertTrue(len(spy) == 3)
        self.assertSetEqual({n for n, _ in spy}, set(nodes))

    def test_create_normal(self):
        workflow = self.scheme
        nodes = workflow.nodes
        wm = TestingWidgetManager()
        wm.set_creation_policy(TestingWidgetManager.Normal)
        spy = QSignalSpy(wm.widget_for_node_added)
        wm.set_workflow(workflow)
        self.assertEqual(len(spy), 0)

        w = wm.widget_for_node(nodes[0])
        self.assertEqual(list(spy), [[nodes[0], w]])

        w = wm.widget_for_node(nodes[2])
        self.assertEqual(list(spy)[1:], [[nodes[2], w]])

        spy = QSignalSpy(wm.widget_for_node_added)
        self.assertTrue(spy.wait())
        w = wm.widget_for_node(nodes[1])
        self.assertEqual(list(spy), [[nodes[1], w]])

        spy = QSignalSpy(wm.widget_for_node_removed)
        workflow.clear()
        self.assertEqual(len(spy), 3)
        self.assertSetEqual({n for n, _ in spy}, set(nodes))

    def test_mappings(self):
        workflow = self.scheme
        nodes = workflow.nodes
        wm = TestingWidgetManager()
        wm.set_workflow(workflow)
        w = wm.widget_for_node(nodes[0])
        n = wm.node_for_widget(w)
        self.assertIs(n, nodes[0])

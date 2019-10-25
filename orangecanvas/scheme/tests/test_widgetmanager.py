from PyQt5.QtCore import QEvent

import unittest

from AnyQt.QtWidgets import QWidget, QApplication, QAction
from AnyQt.QtTest import QSignalSpy

from orangecanvas.scheme import Scheme, NodeEvent, SchemeLink, LinkEvent
from orangecanvas.scheme.widgetmanager import WidgetManager
from orangecanvas.registry import tests as registry_tests
from orangecanvas.scheme.tests import EventSpy


class TestingWidgetManager(WidgetManager):
    def create_widget_for_node(self, node):
        return QWidget()

    def delete_widget_for_node(self, node, widget):
        widget.deleteLater()

    def save_widget_geometry(self, node, widget):
        return widget.saveGeometry()

    def restore_widget_geometry(self, node, widget, state):
        return widget.restoreGeometry(state)


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
        self.assertEqual(len(spy), 3)
        self.assertSetEqual({n for n, _ in spy}, set(nodes))
        spy = QSignalSpy(wm.widget_for_node_removed)
        self.scheme.clear()
        self.assertEqual(len(spy), 3)
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

    def test_create_on_demand(self):
        workflow = self.scheme
        nodes = workflow.nodes
        wm = TestingWidgetManager()
        wm.set_creation_policy(WidgetManager.OnDemand)
        spy = QSignalSpy(wm.widget_for_node_added)
        wm.set_workflow(workflow)
        self.assertEqual(len(spy), 0)
        self.assertFalse(spy.wait(30))
        self.assertEqual(len(spy), 0)
        w = wm.widget_for_node(nodes[0])
        self.assertEqual(list(spy), [[nodes[0], w]])
        # transition to normal
        spy = QSignalSpy(wm.widget_for_node_added)
        wm.set_creation_policy(WidgetManager.Normal)
        self.assertTrue(spy.wait())
        self.assertEqual(spy[0][0], nodes[1])

    def test_mappings(self):
        workflow = self.scheme
        nodes = workflow.nodes
        wm = TestingWidgetManager()
        wm.set_workflow(workflow)
        w = wm.widget_for_node(nodes[0])
        n = wm.node_for_widget(w)
        self.assertIs(n, nodes[0])

    def test_save_geometry(self):
        workflow = self.scheme
        nodes = workflow.nodes
        wm = TestingWidgetManager()
        wm.set_workflow(workflow)
        n = nodes[0]
        w = wm.widget_for_node(n)
        state = wm.save_widget_geometry(n, w)
        self.assertTrue(wm.restore_widget_geometry(n, w, state))
        wm.activate_widget_for_node(n, w)
        state = wm.save_window_state()

        self.assertEqual(len(state), 1)
        self.assertIs(state[0][0], n)
        self.assertEqual(state[0][1], wm.save_widget_geometry(n, w))
        QApplication.sendEvent(
            nodes[1], NodeEvent(NodeEvent.NodeActivateRequest, nodes[1])
        )
        wm.raise_widgets_to_front()

        wm.restore_window_state(state)

    def test_set_model(self):
        workflow = self.scheme
        wm = TestingWidgetManager()
        wm.set_workflow(workflow)
        wm.set_workflow(workflow)
        wm.set_creation_policy(WidgetManager.Immediate)
        wm.set_workflow(Scheme())

    def test_event_dispatch(self):
        workflow = self.scheme
        nodes = workflow.nodes
        links = workflow.links

        class Widget(QWidget):
            def __init__(self, *a):
                self._evt = []
                super().__init__(*a)

            def event(self, event):
                # record all event types
                self._evt.append(event.type())
                return super().event(event)

        class WidgetManager(TestingWidgetManager):
            def create_widget_for_node(self, node):
                w = Widget()
                w._evt = []
                return w

        wm = WidgetManager()
        wm.set_creation_policy(WidgetManager.OnDemand)
        wm.set_workflow(workflow)
        n1, n2, n3 = nodes[:3]
        l1, l2 = links[:2]
        w1 = wm.widget_for_node(n1)

        self.assertIn(NodeEvent.OutputLinkAdded, w1._evt)
        w1._evt.clear()
        workflow.remove_link(l1)

        self.assertIn(NodeEvent.OutputLinkRemoved, w1._evt)
        w3 = wm.widget_for_node(n3)
        w3._evt.clear()
        workflow.add_link(l1)
        self.assertIn(NodeEvent.OutputLinkAdded, w1._evt)
        self.assertIn(NodeEvent.InputLinkAdded, w3._evt)

        w1._evt.clear()
        workflow.set_runtime_env("tt", "aaa")
        self.assertIn(NodeEvent.WorkflowEnvironmentChange, w1._evt)

        w3._evt.clear()
        l1.set_runtime_state(SchemeLink.Pending)
        self.assertIn(LinkEvent.InputLinkStateChange, w3._evt)
        self.assertIn(LinkEvent.OutputLinkStateChange, w1._evt)

    def test_actions(self):
        workflow = self.scheme
        nodes = workflow.nodes
        wm = TestingWidgetManager()
        wm.set_creation_policy(WidgetManager.Immediate)
        wm.set_workflow(workflow)
        w = wm.widget_for_node(nodes[0])
        w2 = wm.widget_for_node(nodes[2])
        espy = EventSpy(w2, QEvent.WindowActivate)
        ac = w.findChild(QAction, "action-canvas-raise-descendants")
        ac.trigger()
        if not espy.events():
            self.assertTrue(espy.wait(1000))
        self.assertTrue(w2.isActiveWindow())

        ac = w2.findChild(QAction, "action-canvas-raise-ancestors")
        espy = EventSpy(w, QEvent.Show)
        ac.trigger()
        if not espy.events():
            self.assertTrue(espy.wait(1000))
        self.assertTrue(w.isVisible())

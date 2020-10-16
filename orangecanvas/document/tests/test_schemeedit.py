"""
Tests for scheme document.
"""
from typing import Iterable
from unittest import mock

from AnyQt.QtCore import Qt, QPoint
from AnyQt.QtGui import QPainterPath
from AnyQt.QtWidgets import QGraphicsWidget, QAction, QApplication
from AnyQt.QtTest import QSignalSpy, QTest

from ..schemeedit import SchemeEditWidget, SaveWindowGroup
from ...canvas import items
from ...scheme import Scheme, SchemeNode, SchemeLink, SchemeTextAnnotation, \
                      SchemeArrowAnnotation
from ...registry.tests import small_testing_registry
from ...gui.test import QAppTestCase, mouseMove
from ...utils import findf
from ...scheme.tests.test_widgetmanager import TestingWidgetManager


def action_by_name(actions, name):
    # type: (Iterable[QAction], str) -> QAction
    for a in actions:
        if a.objectName() == name:
            return a
    raise LookupError(name)


class TestSchemeEdit(QAppTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reg = small_testing_registry()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        del cls.reg

    def setUp(self):
        super().setUp()
        self.w = SchemeEditWidget()
        self.w.setScheme(Scheme())

    def tearDown(self):
        del self.w
        super().tearDown()

    def test_schemeedit(self):
        reg = self.reg
        w = self.w

        scheme = Scheme()
        w.setScheme(scheme)

        self.assertIs(w.scheme(), scheme)
        self.assertFalse(w.isModified())

        scheme = Scheme()
        w.setScheme(scheme)

        self.assertIs(w.scheme(), scheme)
        self.assertFalse(w.isModified())

        w.show()

        one_desc = reg.widget("one")
        negate_desc = reg.widget("negate")

        node_list = []
        link_list = []
        annot_list = []

        scheme.node_added.connect(node_list.append)
        scheme.node_removed.connect(node_list.remove)

        scheme.link_added.connect(link_list.append)
        scheme.link_removed.connect(link_list.remove)

        scheme.annotation_added.connect(annot_list.append)
        scheme.annotation_removed.connect(annot_list.remove)

        node = SchemeNode(one_desc, title="title1", position=(100, 100))
        w.addNode(node)

        self.assertSequenceEqual(node_list, [node])
        self.assertSequenceEqual(scheme.nodes, node_list)

        self.assertTrue(w.isModified())

        stack = w.undoStack()
        stack.undo()

        self.assertSequenceEqual(node_list, [])
        self.assertSequenceEqual(scheme.nodes, node_list)
        self.assertTrue(not w.isModified())

        stack.redo()

        node1 = SchemeNode(negate_desc, title="title2", position=(300, 100))
        w.addNode(node1)

        self.assertSequenceEqual(node_list, [node, node1])
        self.assertSequenceEqual(scheme.nodes, node_list)
        self.assertTrue(w.isModified())

        link = SchemeLink(node, "value", node1, "value")
        w.addLink(link)

        self.assertSequenceEqual(link_list, [link])

        stack.undo()
        stack.undo()

        stack.redo()
        stack.redo()

        w.removeNode(node1)

        self.assertSequenceEqual(link_list, [])
        self.assertSequenceEqual(node_list, [node])

        stack.undo()

        self.assertSequenceEqual(link_list, [link])
        self.assertSequenceEqual(node_list, [node, node1])

        spy = QSignalSpy(node.title_changed)
        w.renameNode(node, "foo bar")
        self.assertSequenceEqual(list(spy), [["foo bar"]])
        self.assertTrue(w.isModified())
        stack.undo()
        self.assertSequenceEqual(list(spy), [["foo bar"], ["title1"]])

        w.removeLink(link)

        self.assertSequenceEqual(link_list, [])

        stack.undo()

        self.assertSequenceEqual(link_list, [link])

        annotation = SchemeTextAnnotation((200, 300, 50, 20), "text")
        w.addAnnotation(annotation)
        self.assertSequenceEqual(annot_list, [annotation])

        stack.undo()
        self.assertSequenceEqual(annot_list, [])

        stack.redo()
        self.assertSequenceEqual(annot_list, [annotation])

        w.removeAnnotation(annotation)
        self.assertSequenceEqual(annot_list, [])
        stack.undo()
        self.assertSequenceEqual(annot_list, [annotation])

        self.assertTrue(w.isModified())
        self.assertFalse(stack.isClean())
        w.setModified(False)

        self.assertFalse(w.isModified())
        self.assertTrue(stack.isClean())
        w.setModified(True)
        self.assertTrue(w.isModified())

        w.resize(600, 400)

    def test_modified(self):
        node = SchemeNode(
            self.reg.widget("one"), title="title1", position=(100, 100))
        self.w.addNode(node)
        self.assertTrue(self.w.isModified())
        self.w.setModified(False)
        self.assertFalse(self.w.isModified())
        self.w.setTitle("Title")
        self.assertTrue(self.w.isModified())
        self.w.setDescription("AAA")
        self.assertTrue(self.w.isModified())
        undo = self.w.undoStack()
        undo.undo()
        undo.undo()
        self.assertFalse(self.w.isModified())

    def test_teardown(self):
        w = self.w
        w.undoStack().isClean()
        new = Scheme()
        w.setScheme(new)

    def test_actions(self):
        w = self.w
        actions = w.toolbarActions()

        action_by_name(actions, "action-zoom-in").trigger()
        action_by_name(actions, "action-zoom-out").trigger()
        action_by_name(actions, "action-zoom-reset").trigger()

    def test_arrow_annotation_action(self):
        w = self.w
        workflow = w.scheme()
        workflow.clear()
        view = w.view()
        w.resize(300, 300)
        actions = w.toolbarActions()
        action_by_name(actions, "new-arrow-action").trigger()
        QTest.mousePress(view.viewport(), Qt.LeftButton, pos=QPoint(50, 50))
        mouseMove(view.viewport(), Qt.LeftButton, pos=QPoint(100, 100))
        QTest.mouseRelease(view.viewport(), Qt.LeftButton, pos=QPoint(100, 100))
        self.assertEqual(len(workflow.annotations), 1)
        self.assertIsInstance(workflow.annotations[0], SchemeArrowAnnotation)

    def test_arrow_annotation_action_cancel(self):
        w = self.w
        workflow = w.scheme()
        view = w.view()
        w.resize(300, 300)
        actions = w.toolbarActions()
        action = action_by_name(actions, "new-arrow-action")
        action.trigger()
        self.assertTrue(action.isChecked())
        # cancel immediately after activating
        QTest.keyClick(view.viewport(), Qt.Key_Escape)
        self.assertFalse(action.isChecked())
        action.trigger()
        # cancel after mouse press and drag
        QTest.mousePress(view.viewport(), Qt.LeftButton, pos=QPoint(50, 50))
        mouseMove(view.viewport(), Qt.LeftButton, pos=QPoint(100, 100))
        QTest.keyClick(view.viewport(), Qt.Key_Escape)
        self.assertFalse(action.isChecked())
        self.assertEqual(workflow.annotations, [])

    def test_text_annotation_action(self):
        w = self.w
        workflow = w.scheme()
        workflow.clear()
        view = w.view()
        w.resize(300, 300)
        actions = w.toolbarActions()
        action_by_name(actions, "new-text-action").trigger()
        QTest.mousePress(view.viewport(), Qt.LeftButton, pos=QPoint(50, 50))
        mouseMove(view.viewport(), Qt.LeftButton, pos=QPoint(100, 100))
        QTest.mouseRelease(view.viewport(), Qt.LeftButton, pos=QPoint(100, 100))
        # need to steal focus from the item for it to be commited.
        w.scene().setFocusItem(None)

        self.assertEqual(len(workflow.annotations), 1)
        self.assertIsInstance(workflow.annotations[0], SchemeTextAnnotation)

    def test_text_annotation_action_cancel(self):
        w = self.w
        workflow = w.scheme()
        view = w.view()
        w.resize(300, 300)
        actions = w.toolbarActions()
        action = action_by_name(actions, "new-text-action")
        action.trigger()
        self.assertTrue(action.isChecked())
        # cancel immediately after activating
        QTest.keyClick(view.viewport(), Qt.Key_Escape)
        self.assertFalse(action.isChecked())
        action.trigger()
        # cancel after mouse press and drag
        QTest.mousePress(view.viewport(), Qt.LeftButton, pos=QPoint(50, 50))
        mouseMove(view.viewport(), Qt.LeftButton, pos=QPoint(100, 100))
        QTest.keyClick(view.viewport(), Qt.Key_Escape)
        self.assertFalse(action.isChecked())
        w.scene().setFocusItem(None)
        self.assertEqual(workflow.annotations, [])

    def test_path(self):
        w = self.w
        spy = QSignalSpy(w.pathChanged)
        self.w.setPath("/dev/null")
        self.assertSequenceEqual(list(spy), [["/dev/null"]])

    def test_ensure_visible(self):
        w = self.w
        node = SchemeNode(
            self.reg.widget("one"), title="title1", position=(10000, 100))
        self.w.addNode(node)
        w.setFixedSize(300, 300)
        w.show()
        assert QTest.qWaitForWindowExposed(w, 500)
        w.ensureVisible(node)
        view = w.view()
        viewrect = view.mapToScene(view.viewport().geometry()).boundingRect()
        self.assertTrue(viewrect.contains(10000., 100.))

    def test_select(self):
        w = self.w
        self.setup_test_workflow(w.scheme())
        w.selectAll()
        self.assertSequenceEqual(
            w.selectedNodes(), w.scheme().nodes)
        self.assertSequenceEqual(
            w.selectedAnnotations(), w.scheme().annotations)
        self.assertSequenceEqual(
            w.selectedLinks(), w.scheme().links)
        w.removeSelected()
        self.assertEqual(w.scheme().nodes, [])
        self.assertEqual(w.scheme().annotations, [])
        self.assertEqual(w.scheme().links, [])

    def test_select_remove_link(self):
        def link_curve(link: SchemeLink) -> QPainterPath:
            item = scene.item_for_link(link)  # type: items.LinkItem
            path = item.curveItem.curvePath()
            return item.mapToScene(path)
        w = self.w
        w.resize(300, 300)
        workflow = self.setup_test_workflow(w.scheme())
        w.alignToGrid()
        scene, view = w.scene(), w.view()
        link = workflow.links[0]
        path = link_curve(link)
        p = path.pointAtPercent(0.5)
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.mapFromScene(p))
        self.assertSequenceEqual(w.selectedLinks(), [link])
        w.removeSelected()
        self.assertSequenceEqual(w.selectedLinks(), [])
        self.assertTrue(link not in workflow.links)

    def test_open_selected(self):
        w = self.w
        w.setScheme(self.setup_test_workflow())
        w.selectAll()
        w.openSelected()

    def test_insert_node_on_link(self):
        w = self.w
        workflow = self.setup_test_workflow(w.scheme())
        neg = SchemeNode(self.reg.widget("negate"))
        target = workflow.links[0]
        spyrem = QSignalSpy(workflow.link_removed)
        spyadd = QSignalSpy(workflow.link_added)
        w.insertNode(neg, target)
        self.assertEqual(workflow.nodes[-1], neg)

        self.assertSequenceEqual(list(spyrem), [[target]])
        self.assertEqual(len(spyadd), 2)
        w.undoStack().undo()

    def test_align_to_grid(self):
        w = self.w
        self.setup_test_workflow(w.scheme())
        w.alignToGrid()

    def test_activate_node(self):
        w = self.w
        workflow = self.setup_test_workflow()
        w.setScheme(workflow)

        view, scene = w.view(), w.scene()
        item = scene.item_for_node(workflow.nodes[0])  # type: QGraphicsWidget
        item.setSelected(True)
        item.setFocus(Qt.OtherFocusReason)
        self.assertIs(w.focusNode(), workflow.nodes[0])
        item.activated.emit()

    def test_duplicate(self):
        w = self.w
        workflow = self.setup_test_workflow()
        w.setScheme(workflow)
        w.selectAll()
        nnodes, nlinks = len(workflow.nodes), len(workflow.links)
        a = action_by_name(w.actions(), "duplicate-action")
        a.trigger()
        self.assertEqual(len(workflow.nodes), 2 * nnodes)
        self.assertEqual(len(workflow.links), 2 * nlinks)

    def test_copy_paste(self):
        w = self.w
        workflow = self.setup_test_workflow()
        w.setRegistry(self.reg)
        w.setScheme(workflow)
        w.selectAll()
        nnodes, nlinks = len(workflow.nodes), len(workflow.links)
        ca = action_by_name(w.actions(), "copy-action")
        cp = action_by_name(w.actions(), "paste-action")
        cb = QApplication.clipboard()
        spy = QSignalSpy(cb.dataChanged)
        ca.trigger()
        if not len(spy):
            self.assertTrue(spy.wait())
        self.assertEqual(len(spy), 1)
        cp.trigger()
        self.assertEqual(len(workflow.nodes), 2 * nnodes)
        self.assertEqual(len(workflow.links), 2 * nlinks)

        w1 = SchemeEditWidget()
        w1.setRegistry(self.reg)
        w1.setScheme((Scheme()))
        cp = action_by_name(w1.actions(), "paste-action")
        self.assertTrue(cp.isEnabled())
        cp.trigger()
        wf1 = w1.scheme()
        self.assertEqual(len(wf1.nodes), nnodes)
        self.assertEqual(len(wf1.links), nlinks)

    def test_redo_remove_preserves_order(self):
        w = self.w
        workflow = self.setup_test_workflow()
        w.setRegistry(self.reg)
        w.setScheme(workflow)
        undo = w.undoStack()
        links = workflow.links
        nodes = workflow.nodes
        annotations = workflow.annotations
        assert len(links) > 2
        w.removeLink(links[1])
        self.assertSequenceEqual(links[:1] + links[2:], workflow.links)
        undo.undo()
        self.assertSequenceEqual(links, workflow.links)
        # find add node that has multiple in/out links
        node = findf(workflow.nodes, lambda n: n.title == "add")
        w.removeNode(node)
        undo.undo()
        self.assertSequenceEqual(links, workflow.links)
        self.assertSequenceEqual(nodes, workflow.nodes)

        w.removeAnnotation(annotations[0])
        self.assertSequenceEqual(annotations[1:], workflow.annotations)
        undo.undo()
        self.assertSequenceEqual(annotations, workflow.annotations)

    def test_window_groups(self):
        w = self.w
        workflow = self.setup_test_workflow()
        workflow.set_window_group_presets([
            Scheme.WindowGroup("G1", False, [(workflow.nodes[0], b'\xff\x00')]),
            Scheme.WindowGroup("G2", True, [(workflow.nodes[0], b'\xff\x00')]),
        ])
        manager = TestingWidgetManager()
        workflow.widget_manager = manager
        with mock.patch.object(manager, "activate_window_group") as m:
            w.setScheme(workflow)
            w.activateDefaultWindowGroup()
            m.assert_called_once_with(workflow.window_group_presets()[1])

        a = w.findChild(QAction, "window-groups-save-action")
        with mock.patch.object(
                workflow, "set_window_group_presets",
                wraps=workflow.set_window_group_presets
        ) as m:
            a.trigger()
            dlg = w.findChild(SaveWindowGroup)
            dlg.accept()
            m.assert_called_once()

        with mock.patch.object(
                workflow, "set_window_group_presets",
                wraps=workflow.set_window_group_presets
        ) as m:
            w.undoStack().undo()
            m.assert_called_once()

        with mock.patch.object(
                workflow, "set_window_group_presets",
                wraps=workflow.set_window_group_presets
        ) as m:
            a = w.findChild(QAction, "window-groups-clear-action")
            a.trigger()
            m.assert_called_once_with([])
        workflow.clear()

    @classmethod
    def setup_test_workflow(cls, scheme=None):
        # type: (Scheme) -> Scheme
        if scheme is None:
            scheme = Scheme()
        reg = cls.reg

        zero_desc = reg.widget("zero")
        one_desc = reg.widget("one")
        add_desc = reg.widget("add")
        negate = reg.widget("negate")

        zero_node = SchemeNode(zero_desc)
        one_node = SchemeNode(one_desc)
        add_node = SchemeNode(add_desc)
        negate_node = SchemeNode(negate)

        scheme.add_node(zero_node)
        scheme.add_node(one_node)
        scheme.add_node(add_node)
        scheme.add_node(negate_node)

        scheme.add_link(SchemeLink(zero_node, "value", add_node, "left"))
        scheme.add_link(SchemeLink(one_node, "value", add_node, "right"))
        scheme.add_link(SchemeLink(add_node, "result", negate_node, "value"))

        scheme.add_annotation(SchemeArrowAnnotation((0, 0), (10, 10)))
        scheme.add_annotation(SchemeTextAnnotation((0, 100, 200, 200), "$$"))
        return scheme

"""
Tests for scheme document.
"""
import re
import sys
import unittest
from unittest import mock
from typing import Iterable

from AnyQt.QtCore import Qt, QPoint, QMimeData
from AnyQt.QtGui import QPainterPath
from AnyQt.QtWidgets import (
    QGraphicsWidget, QAction, QApplication, QMenu, QWidget
)
from AnyQt.QtTest import QSignalSpy, QTest

from .. import commands
from ..schemeedit import SchemeEditWidget, SaveWindowGroup
from ..interactions import (
    DropHandler, PluginDropHandler, NodeFromMimeDataDropHandler, EntryPoint
)
from ...canvas import items
from ...scheme import Scheme, SchemeNode, SchemeLink, SchemeTextAnnotation, \
    SchemeArrowAnnotation, MetaNode
from ...registry.tests import small_testing_registry
from ...gui.test import QAppTestCase, mouseMove, dragDrop, dragEnterLeave, \
    contextMenu
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
        self.w.setRegistry(self.reg)
        self.w.resize(300, 300)

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
        root = scheme.root()
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
        self.assertSequenceEqual(root.nodes(), node_list)

        self.assertTrue(w.isModified())

        stack = w.undoStack()
        stack.undo()

        self.assertSequenceEqual(node_list, [])
        self.assertSequenceEqual(root.nodes(), node_list)
        self.assertTrue(not w.isModified())

        stack.redo()

        node1 = SchemeNode(negate_desc, title="title2", position=(300, 100))
        w.addNode(node1)

        self.assertSequenceEqual(node_list, [node, node1])
        self.assertSequenceEqual(root.nodes(), node_list)
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

    def test_node_rename(self):
        w = self.w
        view = w.view()
        node = SchemeNode(self.reg.widget("one"), title="A")
        w.addNode(node)
        w.editNodeTitle(node)
        # simulate editing
        QTest.keyClicks(view.viewport(), "BB")
        QTest.keyClick(view.viewport(), Qt.Key_Enter)
        self.assertEqual(node.title, "BB")
        # last undo command must be rename command
        undo = w.undoStack()
        command = undo.command(undo.count() - 1)
        self.assertIsInstance(command, commands.RenameNodeCommand)

    @unittest.skipUnless(sys.platform == "darwin", "macos only")
    def test_node_rename_click_selected(self):
        w = self.w
        scene = w.currentScene()
        view = w.view()
        w.show()
        w.raise_()
        w.activateWindow()
        node = SchemeNode(self.reg.widget("one"), title="A")
        w.addNode(node)
        w.selectAll()
        item = scene.item_for_node(node)
        assert isinstance(item, items.NodeItem)
        point = item.captionTextItem.boundingRect().center()
        point = item.captionTextItem.mapToScene(point)
        point = view.mapFromScene(point)
        QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, point)
        self.assertTrue(item.captionTextItem.isEditing())
        contextMenu(view.viewport(), point)

    def test_arrow_annotation_action(self):
        w = self.w
        workflow = w.scheme()
        workflow.clear()
        root = workflow.root()
        view = w.view()
        actions = w.toolbarActions()
        action_by_name(actions, "new-arrow-action").trigger()
        QTest.mousePress(view.viewport(), Qt.LeftButton, pos=QPoint(50, 50))
        mouseMove(view.viewport(), Qt.LeftButton, pos=QPoint(100, 100))
        QTest.mouseRelease(view.viewport(), Qt.LeftButton, pos=QPoint(100, 100))
        self.assertEqual(len(root.annotations()), 1)
        self.assertIsInstance(root.annotations()[0], SchemeArrowAnnotation)

    def test_arrow_annotation_action_cancel(self):
        w = self.w
        workflow = w.scheme()
        view = w.view()
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
        self.assertEqual(workflow.root().annotations(), [])

    def test_text_annotation_action(self):
        w = self.w
        workflow = w.scheme()
        workflow.clear()
        view = w.view()
        actions = w.toolbarActions()
        action_by_name(actions, "new-text-action").trigger()
        QTest.mousePress(view.viewport(), Qt.LeftButton, pos=QPoint(50, 50))
        mouseMove(view.viewport(), Qt.LeftButton, pos=QPoint(100, 100))
        QTest.mouseRelease(view.viewport(), Qt.LeftButton, pos=QPoint(100, 100))
        # need to steal focus from the item for it to be commited.
        w.currentScene().setFocusItem(None)

        self.assertEqual(len(workflow.root().annotations()), 1)
        self.assertIsInstance(workflow.root().annotations()[0], SchemeTextAnnotation)

    def test_text_annotation_action_cancel(self):
        w = self.w
        workflow = w.scheme()
        view = w.view()
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
        w.currentScene().setFocusItem(None)
        self.assertEqual(workflow.root().annotations(), [])

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
        root = w.root()
        self.assertSequenceEqual(w.selectedNodes(), root.nodes())
        self.assertSequenceEqual(w.selectedAnnotations(), root.annotations())
        self.assertSequenceEqual(w.selectedLinks(), root.links())
        w.removeSelected()
        self.assertEqual(root.nodes(), [])
        self.assertEqual(root.annotations(), [])
        self.assertEqual(root.links(), [])

    def test_select_remove_link(self):
        def link_curve(link: SchemeLink) -> QPainterPath:
            item = scene.item_for_link(link)  # type: items.LinkItem
            path = item.curveItem.curvePath()
            return item.mapToScene(path)
        w = self.w
        workflow = self.setup_test_workflow(w.scheme())
        root = workflow.root()
        w.alignToGrid()
        scene, view = w.currentScene(), w.view()
        link = root.links()[0]
        path = link_curve(link)
        p = path.pointAtPercent(0.5)
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=view.mapFromScene(p))
        self.assertSequenceEqual(w.selectedLinks(), [link])
        w.removeSelected()
        self.assertSequenceEqual(w.selectedLinks(), [])
        self.assertTrue(link not in root.links())

    def test_open_selected(self):
        w = self.w
        w.setScheme(self.setup_test_workflow())
        w.selectAll()
        w.openSelected()

    def test_insert_node_on_link(self):
        w = self.w
        workflow = self.setup_test_workflow(w.scheme())
        root = workflow.root()
        neg = SchemeNode(self.reg.widget("negate"))
        target = root.links()[0]
        spyrem = QSignalSpy(workflow.link_removed)
        spyadd = QSignalSpy(workflow.link_added)
        w.insertNode(neg, target)
        self.assertEqual(root.nodes()[-1], neg)

        self.assertSequenceEqual(list(spyrem), [[target, workflow.root()]])
        self.assertEqual(len(spyadd), 2)
        w.undoStack().undo()

    def test_align_to_grid(self):
        w = self.w
        self.setup_test_workflow(w.scheme())
        w.alignToGrid()

    def test_activate_node(self):
        w = self.w
        workflow = self.setup_test_workflow()
        root = workflow.root()
        w.setScheme(workflow)

        view, scene = w.view(), w.currentScene()
        item = scene.item_for_node(root.nodes()[0])  # type: QGraphicsWidget
        item.setSelected(True)
        item.setFocus(Qt.OtherFocusReason)
        self.assertIs(w.focusNode(), root.nodes()[0])
        item.activated.emit()

    def test_duplicate(self):
        w = self.w
        workflow = self.setup_test_workflow()
        root = workflow.root()
        w.setScheme(workflow)
        w.selectAll()
        nnodes, nlinks = len(root.nodes()), len(root.links())
        a = action_by_name(w.actions(), "duplicate-action")
        a.trigger()
        self.assertEqual(len(root.nodes()), 2 * nnodes)
        self.assertEqual(len(root.links()), 2 * nlinks)
        w.selectAll()
        a.trigger()
        self.assertEqual(len(root.nodes()), 4 * nnodes)
        self.assertEqual(len(root.links()), 4 * nlinks)
        self.assertEqual(len(root.nodes()),
                         len(set(n.title for n in root.nodes())))
        match = re.compile(r"\(\d+\)\s*\(\d+\)")
        self.assertFalse(any(match.search(n.title) for n in root.nodes()),
                         "Duplicated renumbering ('foo (2) (1)')")

    def test_copy_paste(self):
        w = self.w
        workflow = self.setup_test_workflow()
        root = workflow.root()
        w.setRegistry(self.reg)
        w.setScheme(workflow)
        w.selectAll()
        nnodes, nlinks = len(root.nodes()), len(root.links())
        ca = action_by_name(w.actions(), "copy-action")
        cp = action_by_name(w.actions(), "paste-action")
        cb = QApplication.clipboard()
        spy = QSignalSpy(cb.dataChanged)
        ca.trigger()
        if not len(spy):
            self.assertTrue(spy.wait())
        self.assertEqual(len(spy), 1)
        cp.trigger()
        self.assertEqual(len(root.nodes()), 2 * nnodes)
        self.assertEqual(len(root.links()), 2 * nlinks)

        w1 = SchemeEditWidget()
        w1.setRegistry(self.reg)
        w1.setScheme((Scheme()))
        cp = action_by_name(w1.actions(), "paste-action")
        self.assertTrue(cp.isEnabled())
        cp.trigger()
        wf1 = w1.scheme()
        root1 = wf1.root()
        self.assertEqual(len(root1.nodes()), nnodes)
        self.assertEqual(len(root1.links()), nlinks)

    def test_redo_remove_preserves_order(self):
        w = self.w
        workflow = self.setup_test_workflow()
        root = workflow.root()
        w.setRegistry(self.reg)
        w.setScheme(workflow)
        undo = w.undoStack()
        links = root.links()
        nodes = root.nodes()
        annotations = root.annotations()
        assert len(links) > 2
        w.removeLink(links[1])
        self.assertSequenceEqual(links[:1] + links[2:], root.links())
        undo.undo()
        self.assertSequenceEqual(links, root.links())
        # find add node that has multiple in/out links
        node = findf(root.nodes(), lambda n: n.title == "add")
        w.removeNode(node)
        undo.undo()
        self.assertSequenceEqual(links, root.links())
        self.assertSequenceEqual(nodes, root.nodes())

        w.removeAnnotation(annotations[0])
        self.assertSequenceEqual(annotations[1:], root.annotations())
        undo.undo()
        self.assertSequenceEqual(annotations, root.annotations())

    def test_create_macro(self):
        w = self.w
        workflow = self.setup_test_workflow()
        w.setRegistry(self.reg)
        w.setScheme(workflow)
        undo = w.undoStack()
        w.selectAll()
        w.createMacroFromSelection()
        undo.undo()
        self.assertTrue(len(workflow.root().nodes()), 1)
        undo.redo()

    def test_expand_macro(self):
        w = self.w
        workflow, node = self.setup_test_meta_node(w)
        w.expandMacro(node)
        self.assertEqual(len(workflow.root().nodes()), 4)
        undo = w.undoStack()
        undo.undo()
        self.assertEqual(len(workflow.root().nodes()), 3)
        undo.redo()

    def test_open_meta_node(self):
        w = self.w
        workflow, node = self.setup_test_meta_node(w)
        self.assertIs(w.root(), workflow.root())
        self.assertIs(w.currentScene().root, workflow.root())
        w.openMetaNode(node)
        self.assertIs(w.root(), node)
        self.assertIs(w.currentScene().root, node)
        undo = w.undoStack()
        # Undo/remove macro must update the current displayed root
        undo.undo()
        self.assertIs(w.root(), workflow.root())

    def test_window_groups(self):
        w = self.w
        workflow = self.setup_test_workflow()
        nodes = workflow.root().nodes()
        workflow.set_window_group_presets([
            Scheme.WindowGroup("G1", False, [(nodes[0], b'\xff\x00')]),
            Scheme.WindowGroup("G2", True, [(nodes[0], b'\xff\x00')]),
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

    def test_drop_event(self):
        w = self.w
        w.setRegistry(self.reg)
        workflow = w.scheme()
        root = workflow.root()
        desc = self.reg.widget("one")
        viewport = w.view().viewport()
        mime = QMimeData()
        mime.setData(
            "application/vnd.orange-canvas.registry.qualified-name",
            desc.qualified_name.encode("utf-8")
        )

        self.assertTrue(dragDrop(viewport, mime, QPoint(10, 10)))

        self.assertEqual(len(root.nodes()), 1)
        self.assertEqual(root.nodes()[0].description, desc)

        dragEnterLeave(viewport, mime)

        self.assertEqual(len(root.nodes()), 1)

    def test_drag_drop(self):
        w = self.w
        w.setRegistry(self.reg)
        handler = TestDropHandler()
        w.setDropHandlers([handler])
        viewport = w.view().viewport()
        mime = QMimeData()
        mime.setData(handler.format_, b'abc')

        dragDrop(viewport, mime, QPoint(10, 10))

        self.assertEqual(handler.doDrop_calls, 1)
        self.assertGreaterEqual(handler.accepts_calls, 1)
        self.assertIsNone(w._userInteractionHandler())

        handler.accepts_calls = 0
        handler.doDrop_calls = 0
        mime = QMimeData()
        mime.setData("application/prs.do-not-accept-this", b'abc')

        dragDrop(viewport, mime, QPoint(10, 10))

        self.assertGreaterEqual(handler.accepts_calls, 1)
        self.assertEqual(handler.doDrop_calls, 0)
        self.assertIsNone(w._userInteractionHandler())

        dragEnterLeave(viewport, mime, QPoint(10, 10))

        self.assertIsNone(w._userInteractionHandler())

    @mock.patch.object(
        PluginDropHandler, "iterEntryPoints",
        lambda _: [
            EntryPoint(
                "AA", f"{__name__}:TestDropHandler", "aa"
            ),
            EntryPoint(
                "BB", f"{__name__}:TestNodeFromMimeData", "aa"
            )
        ]
    )
    def test_plugin_drag_drop(self):
        handler = PluginDropHandler()
        w = self.w
        w.setRegistry(self.reg)
        w.setDropHandlers([handler])
        workflow = w.scheme()
        root = workflow.root()
        viewport = w.view().viewport()
        # Test empty handler
        mime = QMimeData()
        mime.setData(TestDropHandler.format_, b'abc')

        dragDrop(viewport, mime, QPoint(10, 10))

        self.assertIsNone(w._userInteractionHandler())

        # test create node handler
        mime = QMimeData()
        mime.setData(TestNodeFromMimeData.format_, b'abc')

        dragDrop(viewport, mime, QPoint(10, 10))

        self.assertIsNone(w._userInteractionHandler())
        self.assertEqual(len(root.nodes()), 1)
        self.assertEqual(root.nodes()[0].description.name, "one")
        self.assertEqual(root.nodes()[0].properties, {"a": "from drop"})

        workflow.clear()

        # Test both simultaneously (menu for selection)
        mime = QMimeData()
        mime.setData(TestDropHandler.format_, b'abc')
        mime.setData(TestNodeFromMimeData.format_, b'abc')

        def exec(self, *args):
            return action_by_name(self.actions(), "-pick-me")

        # intercept QMenu.exec, force select the TestNodeFromMimeData handler
        with mock.patch.object(QMenu, "exec", exec):
            dragDrop(viewport, mime, QPoint(10, 10))

        self.assertEqual(len(root.nodes()), 1)
        self.assertEqual(root.nodes()[0].description.name, "one")
        self.assertEqual(root.nodes()[0].properties, {"a": "from drop"})

    def test_activate_drop_node(self):
        class NodeFromMimeData(TestNodeFromMimeData):
            def shouldActivateNode(self) -> bool:
                self.shouldActivateNode_called += 1
                return True
            shouldActivateNode_called = 0

            def activateNode(self, document: 'SchemeEditWidget', node: 'Node',
                             widget: 'QWidget') -> None:
                self.activateNode_called += 1
                super().activateNode(document, node, widget)
                widget.didActivate = True
            activateNode_called = 0

        w = self.w
        viewport = w.view().viewport()
        workflow = Scheme()
        wm = workflow.widget_manager = TestingWidgetManager()
        wm.set_creation_policy(TestingWidgetManager.Immediate)
        wm.set_workflow(workflow)
        w.setScheme(workflow)
        handler = NodeFromMimeData()
        w.setDropHandlers([handler])
        mime = QMimeData()
        mime.setData(TestNodeFromMimeData.format_, b'abc')
        record = []
        wm.widget_for_node_added.connect(
            lambda obj, widget: record.append((obj, widget))
        )
        dragDrop(viewport, mime, QPoint(10, 10))
        self.assertEqual(len(record), 1)
        self.assertGreaterEqual(handler.shouldActivateNode_called, 1)
        self.assertGreaterEqual(handler.activateNode_called, 1)
        _, widget = record[0]
        self.assertTrue(widget.didActivate)
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

    @classmethod
    def setup_test_meta_node(cls, editor: SchemeEditWidget):
        workflow = cls.setup_test_workflow()
        editor.setRegistry(cls.reg)
        editor.setScheme(workflow)
        one, add = workflow.root().nodes()[1:3]
        editor.setSelection([one, add])
        editor.createMacroFromSelection()
        node = findf(workflow.root().nodes(), lambda n: isinstance(n, MetaNode))
        return workflow, node


class TestDropHandler(DropHandler):
    format_ = "application/prs.test"
    accepts_calls = 0
    doDrop_calls = 0

    def accepts(self, document, event) -> bool:
        self.accepts_calls += 1
        return event.mimeData().hasFormat(self.format_)

    def doDrop(self, document, event) -> bool:
        self.doDrop_calls += 1
        return event.mimeData().hasFormat(self.format_)


class TestNodeFromMimeData(NodeFromMimeDataDropHandler):
    format_ = "application/prs.one"

    def qualifiedName(self) -> str:
        return "one"

    def canDropMimeData(self, document, data: 'QMimeData') -> bool:
        return data.hasFormat(self.format_)

    def parametersFromMimeData(self, document, data: 'QMimeData') -> 'Dict[str, Any]':
        return {"a": "from drop"}

    def actionFromDropEvent(
            self, document: 'SchemeEditWidget', event: 'QGraphicsSceneDragDropEvent'
    ) -> QAction:
        a = super().actionFromDropEvent(document, event)
        a.setObjectName("-pick-me")
        return a

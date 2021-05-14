from typing import Optional
from unittest import skipUnless

from AnyQt.QtCore import QPointF, QPoint, Qt, QT_VERSION_INFO
from AnyQt.QtTest import QSignalSpy
from AnyQt.QtWidgets import (
    QGraphicsScene, QGraphicsView, QGraphicsItem, QMenu, QAction,
    QApplication, QWidget
)
from orangecanvas.gui.test import QAppTestCase, contextMenu
from orangecanvas.canvas.items.graphicstextitem import GraphicsTextItem
from orangecanvas.utils import findf


@skipUnless((5, 15, 1) <= QT_VERSION_INFO < (6, 0, 0),
            "contextMenuEvent is not reimplemented")
class TestGraphicsTextItem(QAppTestCase):
    def setUp(self):
        super().setUp()
        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.item = GraphicsTextItem()
        self.item.setPlainText("AAA")
        self.item.setTextInteractionFlags(Qt.TextEditable)
        self.scene.addItem(self.item)
        self.view.setFocus()

    def tearDown(self):
        self.scene.clear()
        self.view.deleteLater()
        del self.scene
        del self.view
        super().tearDown()

    def test_item_context_menu(self):
        item = self.item
        menu = self._context_menu()
        self.assertFalse(item.textCursor().hasSelection())
        ac = find_action(menu, "select-all")
        self.assertTrue(ac.isEnabled())
        ac.trigger()
        self.assertTrue(item.textCursor().hasSelection())

    def test_copy_cut_paste(self):
        item = self.item
        cb = QApplication.clipboard()

        c = item.textCursor()
        c.select(c.Document)
        item.setTextCursor(c)

        menu = self._context_menu()
        ac = find_action(menu, "edit-copy")
        spy = QSignalSpy(cb.dataChanged)
        ac.trigger()
        self.assertTrue(len(spy) or spy.wait())

        ac = find_action(menu, "edit-cut")
        spy = QSignalSpy(cb.dataChanged)
        ac.trigger()
        self.assertTrue(len(spy) or spy.wait())
        self.assertEqual(item.toPlainText(), "")

        ac = find_action(menu, "edit-paste")
        ac.trigger()
        self.assertEqual(item.toPlainText(), "AAA")

    def test_context_menu_delete(self):
        item = self.item
        c = item.textCursor()
        c.select(c.Document)
        item.setTextCursor(c)

        menu = self._context_menu()
        ac = find_action(menu, "edit-delete")
        ac.trigger()
        self.assertEqual(self.item.toPlainText(), "")

    def _context_menu(self):
        point = map_to_viewport(self.view, self.item, self.item.boundingRect().center())
        contextMenu(self.view.viewport(), point)
        return self._get_menu()

    def _get_menu(self) -> QMenu:
        menu = findf(
            self.app.topLevelWidgets(),
            lambda w: isinstance(w, QMenu) and w.parent() is self.view.viewport()
        )
        assert menu is not None
        return menu


def map_to_viewport(view: QGraphicsView, item: QGraphicsItem, point: QPointF) -> QPoint:
    point = item.mapToScene(point)
    return view.mapFromScene(point)


def find_action(widget, name):  # type: (QWidget, str) -> Optional[QAction]
    for a in widget.actions():
        if a.objectName() == name:
            return a
    return None

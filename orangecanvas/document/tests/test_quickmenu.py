from AnyQt.QtWidgets import QAction
from AnyQt.QtCore import QPoint, QStringListModel
from AnyQt.QtTest import QTest

from ..quickmenu import QuickMenu, SuggestMenuPage, FlattenedTreeItemModel, \
                        MenuPage

from ...gui.test import QAppTestCase
from ...registry.qt import QtWidgetRegistry
from ...registry.tests import small_testing_registry


class TestMenu(QAppTestCase):
    def test_menu(self):
        menu = QuickMenu()

        def triggered(action):
            print("Triggered", action.text())

        def hovered(action):
            print("Hover", action.text())

        menu.triggered.connect(triggered)
        menu.hovered.connect(hovered)

        items_page = MenuPage()
        model = QStringListModel(["one", "two", "file not found"])
        items_page.setModel(model)
        menu.addPage("w", items_page)

        page_c = MenuPage()
        menu.addPage("c", page_c)

        menu.popup(QPoint(200, 200))
        menu.activateWindow()

        self.app.exec_()

    def test_menu_with_registry(self):
        registry = QtWidgetRegistry(small_testing_registry())

        menu = QuickMenu()
        menu.setModel(registry.model())

        triggered_action = []

        def triggered(action):
            print("Triggered", action.text())
            self.assertIsInstance(action, QAction)
            triggered_action.append(action)

        def hovered(action):
            self.assertIsInstance(action, QAction)
            print("Hover", action.text())

        menu.triggered.connect(triggered)
        menu.hovered.connect(hovered)
        self.app.setActiveWindow(menu)

        rval = menu.exec_(QPoint(200, 200))

        if triggered_action:
            self.assertIs(triggered_action[0], rval)

    def test_search(self):
        registry = QtWidgetRegistry(small_testing_registry())

        menu = SuggestMenuPage()

        menu.setModel(registry.model())
        menu.show()
        menu.setFilterFixedString("o")
        QTest.qWait(10)
        menu.setFilterFixedString("z")
        QTest.qWait(10)
        menu.setFilterFixedString("m")
        QTest.qWait(10)

    def test_flattened_model(self):
        model = QStringListModel(["0", "1", "2", "3"])
        flat = FlattenedTreeItemModel()
        flat.setSourceModel(model)

        def get(row):
            return flat.index(row, 0).data()

        self.assertEqual(get(0), "0")
        self.assertEqual(get(1), "1")
        self.assertEqual(get(3), "3")
        self.assertEqual(flat.rowCount(), model.rowCount())
        self.assertEqual(flat.columnCount(), 1)

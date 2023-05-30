"""
Tests for WidgetsToolBox.

"""
from typing import cast

from AnyQt.QtWidgets import QWidget, QHBoxLayout
from AnyQt.QtGui import QStandardItemModel
from AnyQt.QtCore import QSize
from AnyQt.QtTest import QTest

from ...registry import tests as registry_tests
from ...registry.qt import QtWidgetRegistry


from ..widgettoolbox import WidgetToolBox, WidgetToolGrid, ToolGrid

from ...gui import test


class TestWidgetToolBox(test.QAppTestCase):
    def setUp(self):
        super().setUp()
        reg = registry_tests.small_testing_registry()
        self.reg = QtWidgetRegistry(reg)

    def test_widgettoolgrid(self):
        w = QWidget()
        layout = QHBoxLayout()

        triggered_actions1 = []
        triggered_actions2 = []

        model = self.reg.model()
        data_descriptions = self.reg.widgets("Constants")
        one_action = self.reg.action_for_widget("one")

        actions = list(map(self.reg.action_for_widget, data_descriptions))

        grid = ToolGrid(w)
        grid.setActions(actions)
        grid.actionTriggered.connect(triggered_actions1.append)
        layout.addWidget(grid)

        grid = WidgetToolGrid(w)

        # First category ("Data")
        grid.setModel(model, rootIndex=model.index(0, 0))

        self.assertIs(model, grid.model())

        # Test order of buttons
        grid_layout = grid.layout()
        for i in range(len(actions)):
            button = grid_layout.itemAtPosition(i // 4, i % 4).widget()
            self.assertIs(button.defaultAction(), actions[i])

        grid.actionTriggered.connect(triggered_actions2.append)

        layout.addWidget(grid)

        w.setLayout(layout)
        w.show()
        one_action.trigger()
        self.qWait()

    def test_toolbox(self):
        w = QWidget()
        layout = QHBoxLayout()
        triggered_actions = []

        model = self.reg.model()
        one_action = self.reg.action_for_widget("one")

        box = WidgetToolBox()
        box.setModel(model)
        box.triggered.connect(triggered_actions.append)
        layout.addWidget(box)

        box.setButtonSize(QSize(50, 80))

        w.setLayout(layout)
        w.show()

        one_action.trigger()

        box.setButtonSize(QSize(60, 80))
        box.setIconSize(QSize(35, 35))
        box.setTabButtonHeight(40)
        box.setTabIconSize(QSize(30, 30))

        box.setModel(QStandardItemModel())
        self.assertEqual(box.count(), 0)
        box.setModel(model)
        self.assertEqual(box.count(), model.rowCount())
        self.qWait()

    def test_filter(self):
        w = WidgetToolBox()
        w.setModel(self.reg.model())
        edit = w.filterLineEdit()
        g0 = cast(WidgetToolGrid, w.widget(0))
        self.assertEqual(g0.model().rowCount(g0.rootIndex()), 3)
        QTest.keyClicks(edit, "zero")
        self.assertEqual(g0.model().rowCount(g0.rootIndex()), 1)
        QTest.keyClicks(edit, "\b\b\b\b")
        self.assertEqual(g0.model().rowCount(g0.rootIndex()), 3)

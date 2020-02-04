from PyQt5.QtWidgets import QToolButton

from orangecanvas.application.tests.test_mainwindow import TestMainWindowBase
from orangecanvas.application.widgettoolbox import WidgetToolBox
from orangecanvas.document.usagestatistics import UsageStatistics, EventType


class TestUsageStatistics(TestMainWindowBase):
    def setUp(self):
        super().setUp()
        self.stats = self.w.current_document().usageStatistics()
        self.stats.set_enabled(True)

        reg = self.w.scheme_widget._SchemeEditWidget__registry

        first_cat = reg.categories()[0]
        data_descriptions = reg.widgets(first_cat)
        self.descs = [reg.action_for_widget(desc).data() for desc in data_descriptions]

        toolbox = self.w.findChild(WidgetToolBox)
        widget = toolbox.widget(0)
        self.buttons = widget.findChildren(QToolButton)

    def tearDown(self):
        super().tearDown()
        self.stats._clear_action()
        self.stats._actions = []
        self.stats.set_enabled(False)

    def test_node_add_toolbox_click(self):
        self.assertEqual(len(self.stats._actions), 0)

        w_desc = self.descs[0]
        button = self.buttons[0]

        # ToolboxClick
        button.click()

        self.assertEqual(len(self.stats._actions), 1)

        log = self.stats._actions[0]
        expected = {'Type': UsageStatistics.ToolboxClick,
                    'Events':
                        [
                            {
                                'Type': EventType.NodeAdd,
                                'Widget Name': w_desc.name,
                                'Widget': 0
                            }
                        ]
                    }
        self.assertEqual(expected, log)

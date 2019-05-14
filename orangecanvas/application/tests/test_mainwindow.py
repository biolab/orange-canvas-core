from unittest.mock import patch

from AnyQt.QtWidgets import QToolButton, QDialog

from ...gui.test import QAppTestCase
from ..canvasmain import CanvasMainWindow
from ..widgettoolbox import WidgetToolBox
from ...registry import tests as registry_tests


class MainWindow(CanvasMainWindow):
    pass


class TestMainWindow(QAppTestCase):
    def setUp(self):
        self.w = MainWindow()
        self.registry = registry_tests.small_testing_registry()
        self.w.set_widget_registry(self.registry)

    def tearDown(self):
        del self.w
        del self.registry

    def test_create_new_window(self):
        w = self.w
        new = w.create_new_window()
        self.assertIsInstance(new, MainWindow)
        r1 = new.widget_registry
        self.assertTrue(r1.widgets(), self.registry.widgets())

        w.show()
        new.show()

        w.set_scheme_margins_enabled(True)

    def test_new_window(self):
        w = self.w
        with patch(
            "orangecanvas.application.schemeinfo.SchemeInfoDialog.exec_",
        ):
            w.new_workflow_window()

    def test_examples_dialog(self):
        w = self.w
        with patch(
            "orangecanvas.preview.previewdialog.PreviewDialog.exec_",
            return_value=QDialog.Rejected,
        ):
            w.examples_dialog()

    def test_create_toolbox(self):
        w = self.w
        toolbox = w.findChild(WidgetToolBox)
        assert isinstance(toolbox, WidgetToolBox)
        wf = w.current_document().scheme()
        grid = toolbox.widget(0)

        button = grid.findChild(QToolButton)  # type: QToolButton
        self.assertEqual(len(wf.nodes), 0)
        button.click()
        self.assertEqual(len(wf.nodes), 1)

    def test_create_category_toolbar(self):
        w = self.w
        dock = w.dock_widget
        dock.setExpanded(False)
        a = w.quick_category.actions()[0]
        with patch(
            "orangecanvas.application.canvastooldock.CategoryPopupMenu.exec_",
            return_value=None,
        ):
            w.on_quick_category_action(a)


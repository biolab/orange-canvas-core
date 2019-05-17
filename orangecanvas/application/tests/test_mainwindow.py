import os
import tempfile
from unittest.mock import patch

from AnyQt.QtWidgets import QToolButton, QDialog

from ...gui.test import QAppTestCase
from ..canvasmain import CanvasMainWindow
from ..widgettoolbox import WidgetToolBox
from ...registry import tests as registry_tests


class MainWindow(CanvasMainWindow):
    pass


class TestMainWindowBase(QAppTestCase):
    def setUp(self):
        self.w = MainWindow()
        self.registry = registry_tests.small_testing_registry()
        self.w.set_widget_registry(self.registry)

    def tearDown(self):
        del self.w
        del self.registry


class TestMainWindow(TestMainWindowBase):
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

    def test_recent_list(self):
        w = self.w
        w.clear_recent_schemes()
        w.add_recent_scheme("This one", __file__)
        new = w.create_new_window()
        self.assertEqual(len(new.recent_schemes), 1)
        w.clear_recent_schemes()


class TestMainWindowLoad(TestMainWindowBase):
    filename = ""

    def setUp(self):
        super().setUp()
        fd, filename = tempfile.mkstemp()
        self.file = os.fdopen(fd, "w+b")
        self.filename = filename

    def tearDown(self):
        self.file.close()
        os.remove(self.filename)

    def test_open_example_scheme(self):
        self.file.write(TEST_OWS)
        self.file.flush()
        self.w.open_example_scheme(self.filename)

    def test_open_scheme_file(self):
        self.file.write(TEST_OWS)
        self.file.flush()
        self.w.open_scheme_file(self.filename)

    def test_save(self):
        w = self.w
        w.current_document().setPath(self.filename)
        with patch.object(w, "save_scheme_as") as f:
            w.save_scheme()
            f.assert_not_called()

        w.current_document().setPath("")
        with patch("AnyQt.QtWidgets.QFileDialog.getSaveFileName",
                   return_value=(self.filename, "")) as f:
            w.save_scheme()
            self.assertEqual(w.current_document().path(), self.filename)


TEST_OWS = b"""\
<?xml version='1.0' encoding='utf-8'?>
<scheme description="" title="" version="2.0">
    <nodes>
        <node id="0" name="zero" position="(0, 0)" qualified_name="zero" />
        <node id="1" name="one" position="(0, 0)" qualified_name="one" />
        <node id="2" name="add" position="(0, 0)" qualified_name="add" />
        <node id="3" name="negate" position="(0, 0)" qualified_name="negate" />
    </nodes>
    <links>
        <link enabled="true" id="0" sink_channel="left"
              sink_node_id="2" source_channel="value" source_node_id="0" />
        <link enabled="true" id="1" sink_channel="right" sink_node_id="2"
              source_channel="value" source_node_id="1" />
        <link enabled="true" id="2" sink_channel="value" sink_node_id="3"
              source_channel="result" source_node_id="2" />
    </links>
    <annotations>
        <arrow end="(10, 10)" fill="red" id="0" start="(0, 0)" />
        <text id="1" rect="(0, 100, 200, 200)" type="text/plain">$$</text>
    </annotations>
</scheme>
"""

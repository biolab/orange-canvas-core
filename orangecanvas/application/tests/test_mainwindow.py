import os
import tempfile
from unittest.mock import patch

from AnyQt.QtGui import QWhatsThisClickedEvent
from AnyQt.QtWidgets import QToolButton, QDialog, QMessageBox, QApplication

from .. import addons
from ..outputview import TextStream
from ...scheme import SchemeTextAnnotation, SchemeLink
from ...gui.quickhelp import QuickHelpTipEvent, QuickHelp
from ...utils.shtools import temp_named_file
from ...utils.pickle import swp_name
from ...gui.test import QAppTestCase
from ..canvasmain import CanvasMainWindow
from ..widgettoolbox import WidgetToolBox
from ...registry import tests as registry_tests


class MainWindow(CanvasMainWindow):
    _instances = []

    def create_new_window(self):  # type: () -> CanvasMainWindow
        inst = super().create_new_window()
        MainWindow._instances.append(inst)
        return inst


class TestMainWindowBase(QAppTestCase):
    def setUp(self):
        super().setUp()
        self.w = MainWindow()
        self.registry = registry_tests.small_testing_registry()
        self.w.set_widget_registry(self.registry)

    def tearDown(self):
        self.w.clear_swp()
        self.w.deleteLater()
        for w in MainWindow._instances:
            w.deleteLater()
        MainWindow._instances.clear()
        del self.w
        del self.registry
        self.qWait(1)
        super().tearDown()


class TestMainWindow(TestMainWindowBase):
    def test_create_new_window(self):
        w = self.w
        new = w.create_new_window()
        self.assertIsInstance(new, MainWindow)
        r1 = new.widget_registry
        self.assertEqual(r1.widgets(), self.registry.widgets())

        w.show()
        new.show()

        w.set_scheme_margins_enabled(True)
        new.deleteLater()
        stream = TextStream()
        w.connect_output_stream(stream)

    def test_connect_output_stream(self):
        w = self.w
        stream = TextStream()
        w.connect_output_stream(stream)
        stream.write("Hello")
        self.assertEqual(w.output_view().toPlainText(), "Hello")
        w.disconnect_output_stream(stream)
        stream.write("Bye")
        self.assertEqual(w.output_view().toPlainText(), "Hello")

    def test_create_new_window_streams(self):
        w = self.w
        stream = TextStream()
        w.connect_output_stream(stream)
        new = w.create_new_window()
        stream.write("Hello")
        self.assertEqual(w.output_view().toPlainText(), "Hello")
        self.assertEqual(new.output_view().toPlainText(), "Hello")

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

    def test_quick_help_events(self):
        w = self.w
        help: QuickHelp = w.dock_help
        html = "<h3>HELLO</h3>"
        ev = QuickHelpTipEvent("", html, priority=QuickHelpTipEvent.Normal)
        QApplication.sendEvent(w, ev)
        self.assertEqual(help.currentText(), "<h3>HELLO</h3>")

    def test_help_requests(self):
        w = self.w
        ev = QWhatsThisClickedEvent('help://search?id=one')
        QApplication.sendEvent(w, ev)


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
        super().tearDown()

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

    def test_save_swp(self):
        w = self.w
        swpname = swp_name(w)

        with patch.object(w, "save_swp_to") as f:
            w.save_swp()
            f.assert_not_called()

        desc = self.registry.widgets()[0]
        w.current_document().createNewNode(desc)

        w = self.w
        with patch.object(w, "save_swp_to") as f:
            w.save_swp()
            f.assert_called_with(swpname)

        w.clear_swp()

    def test_load_swp(self):
        w = self.w
        swpname = swp_name(w)

        w2 = MainWindow()
        w2.set_widget_registry(self.registry)

        with patch.object(w2, "load_swp_from") as f:
            w2.load_swp()
            f.assert_not_called()

        desc = self.registry.widgets()[0]
        w.current_document().createNewNode(desc)

        from orangecanvas.utils.pickle import canvas_scratch_name_memo as memo
        memo.clear()

        with patch.object(w2, "load_swp_from") as f:
            w2.load_swp()
            f.assert_called_with(swpname)

        w2.clear_swp()
        del w2

    def test_dont_load_swp_on_new_window(self):
        w = self.w
        desc = self.registry.widgets()[0]
        w.current_document().createNewNode(desc)

        with patch.object(CanvasMainWindow, 'ask_load_swp', self.fail):
            w.new_workflow_window()

    def test_swp_functionality(self):
        w = self.w
        w2 = MainWindow()
        w2.set_widget_registry(self.registry)

        def test(predicate):
            _, tf = tempfile.mkstemp()
            w.save_swp_to(tf)
            w2.load_swp_from(tf)
            predicate()
            w.scheme_widget.setModified(False)

        # test widget add
        desc = self.registry.widget('zero')
        node = w.current_document().createNewNode(desc)
        node.properties['dummy'] = 0

        test(lambda:
             self.assertEqual(w2.scheme_widget.scheme().nodes[0].properties['dummy'], 0))
        w2_node = w2.scheme_widget.scheme().nodes[0]

        # test widget change properties
        node.properties['dummy'] = 1
        test(lambda:
             self.assertEqual(w2_node.properties['dummy'], 1))

        desc = self.registry.widget('add')
        node2 = w.current_document().createNewNode(desc)
        link = SchemeLink(node, node.output_channels()[0], node2, node2.input_channels()[0])
        # test link add
        w.current_document().addLink(link)
        test(lambda:
             self.assertTrue(w2.scheme_widget.scheme().links))

        # test link remove
        w.current_document().removeLink(link)
        test(lambda:
             self.assertFalse(w2.scheme_widget.scheme().links))

        # test widget remove
        w.scheme_widget.removeNode(node)
        w.scheme_widget.removeNode(node2)
        test(lambda:
             self.assertFalse(w2.scheme_widget.scheme().nodes))

        # test annotation add
        a = SchemeTextAnnotation((200, 300, 50, 20), "text")
        w.current_document().addAnnotation(a)
        test(lambda:
             self.assertTrue(w2.scheme_widget.scheme().annotations))

        # test annotation remove
        w.current_document().removeAnnotation(a)
        test(lambda:
             self.assertFalse(w2.scheme_widget.scheme().annotations))

    def test_open_ows_req(self):
        w = self.w
        with temp_named_file(TEST_OWS_REQ.decode()) as f:
            with patch("AnyQt.QtWidgets.QMessageBox.exec",
                       return_value=QMessageBox.Ignore):
                w.load_scheme(f)
                self.assertEqual(w.current_document().path(), f)

            with patch("AnyQt.QtWidgets.QMessageBox.exec",
                       return_value=QMessageBox.Abort):
                w.load_scheme(f)
                self.assertEqual(w.current_document().path(), f)

    def test_install_requirements_dialog(self):
        def query(names):
            return [addons._QueryResult(
                        name, addons.Installable(name, "0.0", "", "", "", []))
                    for name in names]
        w = self.w
        with patch.object(addons, "query_pypi", query), \
             patch.object(addons.AddonManagerDialog, "exec",
                          return_value=QDialog.Rejected):
            w.install_requirements(["uber-package-shiny", "spasm"])


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

TEST_OWS_REQ = b"""\
<?xml version='1.0' encoding='utf-8'?>
<scheme description="" title="" version="2.0">
    <nodes>
        <node id="0" name="zero" position="(0, 0)" qualified_name="zero"
              project_name="foo" />
        <node id="1" name="one" position="(0, 0)" qualified_name="one"
              project_name="foo" />
        <node id="2" name="add" position="(0, 0)" qualified_name="add"
              project_name="foo" />
        <node id="3" name="negate" position="(0, 0)" qualified_name="negate"
              project_name="foo" />
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

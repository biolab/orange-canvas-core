from AnyQt.QtWidgets import QGraphicsScene, QGraphicsView
from AnyQt.QtCore import Qt

from ...registry.tests import small_testing_registry
from ...gui import test
from ..editlinksdialog import EditLinksDialog, EditLinksNode, \
                              GraphicsTextWidget
from ...scheme import SchemeNode


class TestLinksEditDialog(test.QAppTestCase):
    def test_links_edit(self):
        dlg = EditLinksDialog()
        reg = small_testing_registry()
        one_desc = reg.widget("one")
        negate_desc = reg.widget("negate")

        source_node = SchemeNode(one_desc, title="This is 1")
        sink_node = SchemeNode(negate_desc)

        source_channel = source_node.output_channel("value")
        sink_channel = sink_node.input_channel("value")
        links = [(source_channel, sink_channel)]

        dlg.setNodes(source_node, sink_node)

        dlg.show()
        dlg.setLinks(links)

        self.assertSequenceEqual(dlg.links(), links)
        self.singleShot(50, dlg.close)

        status = dlg.exec_()

        self.assertTrue(dlg.links() == [] or dlg.links() == links)

    def test_graphicstextwidget(self):
        scene = QGraphicsScene()
        view = QGraphicsView(scene)

        text = GraphicsTextWidget()
        text.setHtml("<center><b>a text</b></center><p>paragraph</p>")
        scene.addItem(text)
        view.show()
        view.resize(400, 300)

        self.qWait()

    def test_editlinksnode(self):
        reg = small_testing_registry()
        one_desc = reg.widget("one")
        negate_desc = reg.widget("negate")
        source_node = SchemeNode(one_desc, title="This is 1")
        sink_node = SchemeNode(negate_desc)

        scene = QGraphicsScene()
        view = QGraphicsView(scene)

        node = EditLinksNode(node=source_node)
        scene.addItem(node)

        node = EditLinksNode(direction=Qt.RightToLeft)
        node.setSchemeNode(sink_node)

        node.setPos(300, 0)
        scene.addItem(node)

        view.show()
        view.resize(800, 300)
        self.qWait()

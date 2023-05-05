from AnyQt.QtGui import QPalette
from AnyQt.QtWidgets import QGraphicsScene, QGraphicsView
from AnyQt.QtCore import Qt, QPoint

from ...utils import findf
from ...registry.tests import small_testing_registry
from ...gui import test
from ..editlinksdialog import EditLinksDialog, EditLinksNode, \
    GraphicsTextWidget, LinksEditWidget, LinkLineItem, ChannelAnchor
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

        status = dlg.exec()

        self.assertTrue(dlg.links() == [] or dlg.links() == links)

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

    def test_links_edit_widget(self):
        reg = small_testing_registry()
        one_desc = reg.widget("one")
        negate_desc = reg.widget("negate")
        source_node = SchemeNode(one_desc, title="This is 1")
        sink_node = SchemeNode(negate_desc)

        source_channel = source_node.output_channel("value")
        sink_channel = sink_node.input_channel("value")

        scene = QGraphicsScene()
        view = QGraphicsView(scene)
        view.resize(800, 600)
        widget = LinksEditWidget()
        scene.addItem(widget)
        widget.setNodes(source_node, sink_node)
        widget.addLink(source_channel, sink_channel)
        view.grab()
        linkitems = widget.childItems()
        link = findf(linkitems, lambda item: isinstance(item, LinkLineItem))
        center = link.line().center()
        pos = view.mapFromScene(link.mapToScene(center))
        test.mouseMove(view.viewport(), Qt.NoButton, pos=pos)  # hover over line
        view.grab()  # paint in hovered state
        test.mouseMove(view.viewport(), Qt.NoButton, pos=QPoint(0, 0)) # hover leave

        palette = QPalette()
        palette.setColor(QPalette.Text, Qt.red)
        widget.setPalette(palette)
        view.grab()

        anchor = findf(widget.sourceNodeWidget.childItems(),
                       lambda item: isinstance(item, ChannelAnchor))
        pos = view.mapFromScene(anchor.mapToScene(anchor.rect().center()))

        test.mouseMove(view.viewport(), Qt.NoButton, pos=pos)  # hover over anchor
        view.grab()  # paint in hovered state
        test.mouseMove(view.viewport(), Qt.NoButton, pos=QPoint(0, 0))  # hover leave

        anchor.setEnabled(False)
        view.grab()  # paint in disabled state


class TestGraphicsTextWidget(test.QAppTestCase):
    def test_graphicstextwidget(self):
        scene = QGraphicsScene()
        view = QGraphicsView(scene)
        view.resize(400, 300)

        text = GraphicsTextWidget()
        text.setHtml("<center><b>a text</b></center><p>paragraph</p>")
        scene.addItem(text)

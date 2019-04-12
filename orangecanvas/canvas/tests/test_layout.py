import time

from AnyQt.QtCore import QTimer
from AnyQt.QtWidgets import QGraphicsView
from AnyQt.QtGui import QPainter, QPainterPath

from ...gui.test import QAppTestCase

from ..layout import AnchorLayout
from ..scene import CanvasScene
from ..items import NodeItem, LinkItem
from ...registry.tests import small_testing_registry


class TestAnchorLayout(QAppTestCase):
    def setUp(self):
        super().setUp()
        self.scene = CanvasScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.show()
        self.view.resize(600, 400)

    def tearDown(self):
        self.scene.clear()
        self.view.deleteLater()
        self.scene.deleteLater()
        del self.scene
        del self.view
        super().tearDown()

    def test_layout(self):
        one_desc, negate_desc, cons_desc = self.widget_desc()
        one_item = NodeItem()
        one_item.setWidgetDescription(one_desc)
        one_item.setPos(0, 150)
        self.scene.add_node_item(one_item)

        cons_item = NodeItem()
        cons_item.setWidgetDescription(cons_desc)
        cons_item.setPos(200, 0)
        self.scene.add_node_item(cons_item)

        negate_item = NodeItem()
        negate_item.setWidgetDescription(negate_desc)
        negate_item.setPos(200, 300)
        self.scene.add_node_item(negate_item)

        link = LinkItem()
        link.setSourceItem(one_item)
        link.setSinkItem(negate_item)
        self.scene.add_link_item(link)

        link = LinkItem()
        link.setSourceItem(one_item)
        link.setSinkItem(cons_item)
        self.scene.add_link_item(link)

        layout = AnchorLayout()
        self.scene.addItem(layout)
        self.scene.set_anchor_layout(layout)

        layout.invalidateNode(one_item)
        layout.activate()

        p1, p2 = one_item.outputAnchorItem.anchorPositions()
        self.assertTrue(p1 > p2)

        self.scene.node_item_position_changed.connect(layout.invalidateNode)

        path = QPainterPath()
        path.addEllipse(125, 0, 50, 300)

        def advance():
            t = time.process_time()
            cons_item.setPos(path.pointAtPercent(t % 1.0))
            negate_item.setPos(path.pointAtPercent((t + 0.5) % 1.0))

        timer = QTimer(negate_item, interval=20)
        timer.start()
        timer.timeout.connect(advance)
        self.app.exec_()

    def widget_desc(self):
        reg = small_testing_registry()
        one_desc = reg.widget("one")
        negate_desc = reg.widget("negate")
        cons_desc = reg.widget("cons")
        return one_desc, negate_desc, cons_desc

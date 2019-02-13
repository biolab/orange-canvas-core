from AnyQt.QtCore import QTimer
from AnyQt.QtWidgets import QGraphicsEllipseItem
from AnyQt.QtGui import QPainterPath

from .. import NodeItem, AnchorPoint, NodeAnchorItem

from . import TestItems
from ....registry.tests import small_testing_registry


class TestNodeItem(TestItems):
    def setUp(self):
        super().setUp()
        self.reg = small_testing_registry()

        self.const_desc = self.reg.category("Constants")
        self.operator_desc = self.reg.category("Operators")

        self.one_desc = self.reg.widget("one")
        self.negate_desc = self.reg.widget("negate")
        self.add_desc = self.reg.widget("add")

    def test_nodeitem(self):
        one_item = NodeItem()
        one_item.setWidgetDescription(self.one_desc)
        one_item.setWidgetCategory(self.const_desc)

        one_item.setTitle("Neo")
        self.assertEqual(one_item.title(), "Neo")

        one_item.setProcessingState(True)
        self.assertEqual(one_item.processingState(), True)

        one_item.setProgress(50)
        self.assertEqual(one_item.progress(), 50)

        one_item.setProgress(100)
        self.assertEqual(one_item.progress(), 100)

        one_item.setProgress(101)
        self.assertEqual(one_item.progress(), 100, "Progress overshots")

        one_item.setProcessingState(False)
        self.assertEqual(one_item.processingState(), False)
        self.assertEqual(one_item.progress(), -1,
                         "setProcessingState does not clear the progress.")

        self.scene.addItem(one_item)
        one_item.setPos(100, 100)

        negate_item = NodeItem()
        negate_item.setWidgetDescription(self.negate_desc)
        negate_item.setWidgetCategory(self.const_desc)

        self.scene.addItem(negate_item)
        negate_item.setPos(300, 100)

        nb_item = NodeItem()
        nb_item.setWidgetDescription(self.add_desc)
        nb_item.setWidgetCategory(self.operator_desc)

        self.scene.addItem(nb_item)
        nb_item.setPos(500, 100)

        positions = []
        anchor = one_item.newOutputAnchor()
        anchor.scenePositionChanged.connect(positions.append)

        one_item.setPos(110, 100)
        self.assertTrue(len(positions) > 0)

        one_item.setErrorMessage("message")
        one_item.setWarningMessage("message")
        one_item.setInfoMessage("I am alive")

        one_item.setErrorMessage(None)
        one_item.setWarningMessage(None)
        one_item.setInfoMessage(None)

        one_item.setInfoMessage("I am back.")
        nb_item.setProcessingState(1)

        def progress():
            p = (nb_item.progress() + 1) % 100
            nb_item.setProgress(p)

            if p > 50:
                nb_item.setInfoMessage("Over 50%")
                one_item.setWarningMessage("Second")
            else:
                nb_item.setInfoMessage(None)
                one_item.setWarningMessage(None)

            negate_item.setAnchorRotation(50 - p)

        timer = QTimer(nb_item, interval=10)
        timer.start()
        timer.timeout.connect(progress)

        self.app.exec_()

    def test_nodeanchors(self):
        one_item = NodeItem()
        one_item.setWidgetDescription(self.one_desc)
        one_item.setWidgetCategory(self.const_desc)

        one_item.setTitle("File Node")

        self.scene.addItem(one_item)
        one_item.setPos(100, 100)

        negate_item = NodeItem()
        negate_item.setWidgetDescription(self.negate_desc)
        negate_item.setWidgetCategory(self.const_desc)

        self.scene.addItem(negate_item)
        negate_item.setPos(300, 100)

        nb_item = NodeItem()
        nb_item.setWidgetDescription(self.add_desc)
        nb_item.setWidgetCategory(self.operator_desc)

        with self.assertRaises(ValueError):
            one_item.newInputAnchor()

        anchor = one_item.newOutputAnchor()
        self.assertIsInstance(anchor, AnchorPoint)

        self.app.exec_()

    def test_anchoritem(self):
        anchoritem = NodeAnchorItem(None)
        self.scene.addItem(anchoritem)

        path = QPainterPath()
        path.addEllipse(0, 0, 100, 100)

        anchoritem.setAnchorPath(path)

        anchor = AnchorPoint()
        anchoritem.addAnchor(anchor)

        ellipse1 = QGraphicsEllipseItem(-3, -3, 6, 6)
        ellipse2 = QGraphicsEllipseItem(-3, -3, 6, 6)
        self.scene.addItem(ellipse1)
        self.scene.addItem(ellipse2)

        anchor.scenePositionChanged.connect(ellipse1.setPos)

        with self.assertRaises(ValueError):
            anchoritem.addAnchor(anchor)

        anchor1 = AnchorPoint()
        anchoritem.addAnchor(anchor1)

        anchor1.scenePositionChanged.connect(ellipse2.setPos)

        self.assertSequenceEqual(anchoritem.anchorPoints(), [anchor, anchor1])

        self.assertSequenceEqual(anchoritem.anchorPositions(), [0.5, 0.5])
        anchoritem.setAnchorPositions([0.5, 0.0])

        self.assertSequenceEqual(anchoritem.anchorPositions(), [0.5, 0.0])

        def advance():
            t = anchoritem.anchorPositions()
            t = [(t + 0.05) % 1.0 for t in t]
            anchoritem.setAnchorPositions(t)

        timer = QTimer(anchoritem, interval=20)
        timer.start()
        timer.timeout.connect(advance)

        self.app.exec_()

import time

from AnyQt.QtCore import QTimer

from ..linkitem import LinkItem

from .. import NodeItem, AnchorPoint

from ....registry.tests import small_testing_registry

from . import TestItems


class TestLinkItem(TestItems):
    def setUp(self):
        super().setUp()

        reg = small_testing_registry()

        const_desc = reg.category("Constants")

        one_desc = reg.widget("one")

        self.one_item = one_item = NodeItem()
        one_item.setWidgetDescription(one_desc)
        one_item.setWidgetCategory(const_desc)

        negate_desc = reg.widget("negate")

        self.negate_item = negate_item = NodeItem()
        negate_item.setWidgetDescription(negate_desc)
        negate_item.setWidgetCategory(const_desc)
        operator_desc = reg.category("Operators")

        add_desc = reg.widget("add")

        self.nb_item = nb_item = NodeItem()
        nb_item.setWidgetDescription(add_desc)
        nb_item.setWidgetCategory(operator_desc)

    def test_linkitem(self):
        one_item = self.one_item
        negate_item = self.negate_item
        nb_item = self.nb_item

        one_item.setPos(0, 100)
        negate_item.setPos(200, 100)
        nb_item.setPos(400, 100)

        self.scene.addItem(one_item)
        self.scene.addItem(negate_item)
        self.scene.addItem(nb_item)

        link = LinkItem()
        anchor1 = one_item.newOutputAnchor()
        anchor2 = negate_item.newInputAnchor()

        self.assertSequenceEqual(one_item.outputAnchors(), [anchor1])
        self.assertSequenceEqual(negate_item.inputAnchors(), [anchor2])

        link.setSourceItem(one_item, anchor=anchor1)
        link.setSinkItem(negate_item, anchor=anchor2)

        # Setting an item and an anchor not in the item's anchors raises
        # an error.
        with self.assertRaises(ValueError):
            link.setSourceItem(one_item, anchor=AnchorPoint())

        self.assertSequenceEqual(one_item.outputAnchors(), [anchor1])

        anchor2 = one_item.newOutputAnchor()

        link.setSourceItem(one_item, anchor=anchor2)
        self.assertSequenceEqual(one_item.outputAnchors(), [anchor1, anchor2])
        self.assertIs(link.sourceAnchor, anchor2)

        one_item.removeOutputAnchor(anchor1)

        self.scene.addItem(link)

        link = LinkItem()
        link.setSourceItem(negate_item)
        link.setSinkItem(nb_item)

        self.scene.addItem(link)

        self.assertTrue(len(nb_item.inputAnchors()) == 1)
        self.assertTrue(len(negate_item.outputAnchors()) == 1)
        self.assertTrue(len(negate_item.inputAnchors()) == 1)
        self.assertTrue(len(one_item.outputAnchors()) == 1)

        link.removeLink()

        self.assertTrue(len(nb_item.inputAnchors()) == 0)
        self.assertTrue(len(negate_item.outputAnchors()) == 0)
        self.assertTrue(len(negate_item.inputAnchors()) == 1)
        self.assertTrue(len(one_item.outputAnchors()) == 1)

        self.qWait()

    def test_dynamic_link(self):
        link = LinkItem()
        anchor1 = self.one_item.newOutputAnchor()
        anchor2 = self.nb_item.newInputAnchor()

        self.scene.addItem(link)
        self.scene.addItem(anchor1)
        self.scene.addItem(anchor2)

        link.setSourceItem(self.one_item, anchor=anchor1)
        link.setSinkItem(self.nb_item, anchor=anchor2)

        anchor2.setPos(100, 100)

        link.setSourceName("1")
        link.setSinkName("2")

        link.setDynamic(True)
        self.assertTrue(link.isDynamic())

        link.setDynamicEnabled(True)
        self.assertTrue(link.isDynamicEnabled())
        self.assertEqual(link.curveItem.toolTip(), "")

        link.setDynamicEnabled(False)
        self.assertIn("one", link.curveItem.toolTip())
        self.assertIn("add", link.curveItem.toolTip())

        self.one_item.setTitle("new name for source")
        self.one_item.titleEditingFinished.emit()
        self.assertIn("new name for source", link.curveItem.toolTip())
        self.assertIn("add", link.curveItem.toolTip())

        self.nb_item.setTitle("new name for sink")
        self.nb_item.titleEditingFinished.emit()
        self.assertIn("new name for source", link.curveItem.toolTip())
        self.assertIn("new name for sink", link.curveItem.toolTip())

        def advance():
            clock = time.process_time()
            link.setDynamic(clock > 1)
            link.setDynamicEnabled(int(clock) % 2 == 0)

        timer = QTimer(link, interval=0)
        timer.timeout.connect(advance)
        timer.start()
        self.qWait()
        timer.stop()

    def test_link_enabled(self):
        link = LinkItem()
        anchor1 = self.one_item.newOutputAnchor()
        anchor2 = self.nb_item.newInputAnchor()
        anchor2.setPos(100, 100)

        link.setSourceItem(self.one_item, anchor=anchor1)
        link.setSinkItem(self.nb_item, anchor=anchor2)

        link.setEnabled(False)
        self.assertFalse(link.isEnabled())
        link.setEnabled(True)
        self.assertTrue(link.isEnabled())

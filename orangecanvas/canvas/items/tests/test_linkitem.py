import time

from ..linkitem import LinkItem

from .. import NodeItem, AnchorPoint

from ....registry.tests import small_testing_registry

from . import TestItems


class TestLinkItem(TestItems):
    def test_linkitem(self):
        reg = small_testing_registry()

        const_desc = reg.category("Constants")

        one_desc = reg.widget("one")

        one_item = NodeItem()
        one_item.setWidgetDescription(one_desc)
        one_item.setWidgetCategory(const_desc)
        one_item.setPos(0, 100)

        negate_desc = reg.widget("negate")

        negate_item = NodeItem()
        negate_item.setWidgetDescription(negate_desc)
        negate_item.setWidgetCategory(const_desc)
        negate_item.setPos(200, 100)
        operator_desc = reg.category("Operators")

        add_desc = reg.widget("add")

        nb_item = NodeItem()
        nb_item.setWidgetDescription(add_desc)
        nb_item.setWidgetCategory(operator_desc)
        nb_item.setPos(400, 100)

        self.scene.addItem(one_item)
        self.scene.addItem(negate_item)
        self.scene.addItem(nb_item)

        link = LinkItem()
        anchor1 = one_item.newOutputAnchor()
        anchor2 = negate_item.newInputAnchor()

        self.assertSequenceEqual(one_item.outputAnchors(), [anchor1])
        self.assertSequenceEqual(negate_item.inputAnchors(), [anchor2])

        link.setSourceItem(one_item, anchor1)
        link.setSinkItem(negate_item, anchor2)

        # Setting an item and an anchor not in the item's anchors raises
        # an error.
        with self.assertRaises(ValueError):
            link.setSourceItem(one_item, AnchorPoint())

        self.assertSequenceEqual(one_item.outputAnchors(), [anchor1])

        anchor2 = one_item.newOutputAnchor()

        link.setSourceItem(one_item, anchor2)
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

        self.app.exec_()

    def test_dynamic_link(self):
        link = LinkItem()
        anchor1 = AnchorPoint()
        anchor2 = AnchorPoint()

        self.scene.addItem(link)
        self.scene.addItem(anchor1)
        self.scene.addItem(anchor2)

        link.setSourceItem(None, anchor1)
        link.setSinkItem(None, anchor2)

        anchor2.setPos(100, 100)

        link.setSourceName("1")
        link.setSinkName("2")

        link.setDynamic(True)
        self.assertTrue(link.isDynamic())

        link.setDynamicEnabled(True)
        self.assertTrue(link.isDynamicEnabled())

        def advance():
            clock = time.clock()
            link.setDynamic(clock > 3)
            link.setDynamicEnabled(int(clock) % 2 == 0)
            self.singleShot(0, advance)

        advance()

        self.app.exec_()

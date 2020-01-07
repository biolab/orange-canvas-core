"""
Tests for ToolBox widget.

"""

from .. import test
from .. import toolbox

from AnyQt.QtWidgets import QLabel, QListView, QSpinBox, QAbstractButton
from AnyQt.QtGui import QIcon


class TestToolBox(test.QAppTestCase):
    def test_tool_box(self):
        w = toolbox.ToolBox()
        style = self.app.style()
        icon = QIcon(style.standardIcon(style.SP_FileIcon))
        p1 = QLabel("A Label")
        p2 = QListView()
        p3 = QLabel("Another\nlabel")
        p4 = QSpinBox()

        i1 = w.addItem(p1, "T1", icon)
        i2 = w.addItem(p2, "Tab " * 10, icon, "a tab")
        i3 = w.addItem(p3, "t3")
        i4 = w.addItem(p4, "t4")

        self.assertSequenceEqual([i1, i2, i3, i4], range(4))
        self.assertEqual(w.count(), 4)

        for i, item in enumerate([p1, p2, p3, p4]):
            self.assertIs(item, w.widget(i))
            b = w.tabButton(i)
            a = w.tabAction(i)
            self.assertIsInstance(b,  QAbstractButton)
            self.assertIs(b.defaultAction(), a)

        w.show()
        w.removeItem(2)

        self.assertEqual(w.count(), 3)
        self.assertIs(w.widget(2), p4)

        p3 = QLabel("Once More Unto the Breach")

        w.insertItem(2, p3, "Dear friend")

        self.assertEqual(w.count(), 4)

        self.assertIs(w.widget(1), p2)
        self.assertIs(w.widget(2), p3)
        self.assertIs(w.widget(3), p4)

        self.qWait()

    def test_tool_box_exclusive(self):
        w = toolbox.ToolBox()
        w.setExclusive(True)
        w.addItem(QLabel(), "A")
        w.addItem(QLabel(), "B")
        w.addItem(QLabel(), "C")
        a0, a1 = w.tabAction(0), w.tabAction(1)
        self.assertTrue(a0.isChecked())
        a1.toggle()
        self.assertFalse(a0.isChecked())
        self.assertFalse(w.widget(0).isVisibleTo(w))
        self.assertTrue(w.widget(1).isVisibleTo(w))

        w.setExclusive(False)
        a0.toggle()
        self.assertTrue(a0.isChecked() and a1.isChecked())
        self.assertTrue(w.widget(0).isVisibleTo(w))
        self.assertTrue(w.widget(1).isVisibleTo(w))

        w.setExclusive(True)
        self.assertEqual(
            sum([w.widget(i).isVisibleTo(w) for i in range(w.count())]), 1
        )

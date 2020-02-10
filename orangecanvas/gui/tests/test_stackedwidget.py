"""
Test for StackedWidget

"""
from AnyQt.QtWidgets import QWidget, QLabel, QGroupBox, QListView, QVBoxLayout
from AnyQt.QtCore import QTimer

from .. import test
from .. import stackedwidget


class TestStackedWidget(test.QAppTestCase):
    def test(self):
        window = QWidget()
        layout = QVBoxLayout()
        window.setLayout(layout)

        stack = stackedwidget.AnimatedStackedWidget(animationEnabled=False)

        layout.addStretch(2)
        layout.addWidget(stack)
        layout.addStretch(2)
        window.show()

        widget1 = QLabel("A label " * 10)
        widget1.setWordWrap(True)

        widget2 = QGroupBox("Group")

        widget3 = QListView()
        self.assertEqual(stack.count(), 0)
        self.assertEqual(stack.currentIndex(), -1)

        stack.addWidget(widget1)
        self.assertEqual(stack.count(), 1)
        self.assertEqual(stack.currentIndex(), 0)

        stack.addWidget(widget2)
        stack.addWidget(widget3)
        self.assertEqual(stack.count(), 3)
        self.assertEqual(stack.currentIndex(), 0)

        def widgets():
            return [stack.widget(i) for i in range(stack.count())]

        self.assertSequenceEqual([widget1, widget2, widget3],
                                 widgets())
        stack.show()

        stack.removeWidget(widget2)
        self.assertEqual(stack.count(), 2)
        self.assertEqual(stack.currentIndex(), 0)
        self.assertSequenceEqual([widget1, widget3],
                                 widgets())

        stack.setCurrentIndex(1)
        self.qWait()

        self.assertEqual(stack.currentIndex(), 1)

        widget2 = QGroupBox("Group")
        stack.insertWidget(1, widget2)
        self.assertEqual(stack.count(), 3)
        self.assertEqual(stack.currentIndex(), 2)
        self.assertSequenceEqual([widget1, widget2, widget3],
                                 widgets())

        def toogle():
            idx = stack.currentIndex()
            stack.setCurrentIndex((idx + 1) % stack.count())

        timer = QTimer(stack, interval=100)
        timer.timeout.connect(toogle)
        timer.start()
        self.qWait(200)
        timer.stop()
        window.deleteLater()

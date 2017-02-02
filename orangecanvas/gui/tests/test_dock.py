"""
Tests for the DockWidget.

"""

from AnyQt.QtWidgets import (
    QWidget, QMainWindow, QListView, QTextEdit, QToolButton,
    QHBoxLayout, QLabel
)
from AnyQt.QtCore import Qt, QTimer, QStringListModel

from .. import test
from ..dock import CollapsibleDockWidget


class TestDock(test.QAppTestCase):
    def test_dock_standalone(self):
        widget = QWidget()
        layout = QHBoxLayout()
        widget.setLayout(layout)
        layout.addStretch(1)
        widget.show()

        dock = CollapsibleDockWidget()
        layout.addWidget(dock)
        list_view = QListView()
        list_view.setModel(QStringListModel(["a", "b"], list_view))

        label = QLabel("A label. ")
        label.setWordWrap(True)

        dock.setExpandedWidget(label)
        dock.setCollapsedWidget(list_view)
        dock.setExpanded(True)
        dock.setExpanded(False)

        timer = QTimer(dock, interval=200)
        timer.timeout.connect(lambda: dock.setExpanded(not dock.expanded()))
        timer.start()

        # self.app.exec_()

    def test_dock_mainwinow(self):
        mw = QMainWindow()
        dock = CollapsibleDockWidget()
        w1 = QTextEdit()

        w2 = QToolButton()
        w2.setFixedSize(38, 200)

        dock.setExpandedWidget(w1)
        dock.setCollapsedWidget(w2)

        mw.addDockWidget(Qt.LeftDockWidgetArea, dock)
        mw.setCentralWidget(QTextEdit())
        mw.show()

        timer = QTimer(dock, interval=200)
        timer.timeout.connect(lambda: dock.setExpanded(not dock.expanded()))
        timer.start()

        # self.app.exec_()

import sys
from AnyQt.QtCore import Qt
from AnyQt.QtGui import QKeySequence
from AnyQt.QtWidgets import (
    QApplication, QAction, QMainWindow, QTextEdit, QToolButton,
    QTreeView
)
from orangecanvas.gui.dock import CollapsibleDockWidget


def main(argv):
    app = QApplication(argv)
    mw = QMainWindow()
    dock = CollapsibleDockWidget()

    w1 = QTreeView()
    w1.header().hide()

    w2 = QToolButton()
    w2.setFixedSize(38, 200)

    dock.setExpandedWidget(w1)
    dock.setCollapsedWidget(w2)

    mw.addDockWidget(Qt.LeftDockWidgetArea, dock)
    mw.setCentralWidget(QTextEdit())
    mw.show()

    a = QAction(
        "Expand", mw, checkable=True,
        shortcut=QKeySequence(Qt.ControlModifier | Qt.Key_D)
    )
    a.triggered[bool].connect(dock.setExpanded)
    mw.addAction(a)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv))

import sys

from AnyQt.QtGui import QIcon
from AnyQt.QtWidgets import (
    QApplication, QLabel, QListView, QSpinBox, QTextBrowser, QStyle
)

from orangecanvas.gui.toolbox import ToolBox


def main(argv=[]):
    app = QApplication(argv)
    w = ToolBox()

    style = app.style()
    icon = QIcon(style.standardIcon(QStyle.SP_FileIcon))

    p1 = QLabel("A Label")
    p2 = QListView()
    p3 = QLabel("Another\nlabel")
    p4 = QSpinBox()

    i1 = w.addItem(p1, "Tab 1", icon)
    i2 = w.addItem(p2, "Tab 2", icon, "The second tab")
    i3 = w.addItem(p3, "Tab 3")
    i4 = w.addItem(p4, "Tab 4")

    p6 = QTextBrowser()
    p6.setHtml(
        "<h1>Hello Visitor</h1>"
        "<p>Are you interested in some of our wares?</p>"
    )
    w.insertItem(2, p6, "Dear friend")
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main(sys.argv))

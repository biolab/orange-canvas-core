"""
Application about dialog.
-------------------------

"""

import sys
from xml.sax.saxutils import escape

from AnyQt.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QLabel, QApplication
)
from AnyQt.QtCore import Qt

from .. import config

ABOUT_TEMPLATE = """\
<center>
<h4>{name}</h4>
<p>Version: {version}</p>
</center>
"""


class AboutDialog(QDialog):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)

        if sys.platform == "darwin":
            self.setAttribute(Qt.WA_MacSmallSize, True)

        self.__setupUi()

    def __setupUi(self):
        layout = QVBoxLayout()
        label = QLabel(self)

        pixmap, _ = config.splash_screen()

        label.setPixmap(pixmap)

        layout.addWidget(label, Qt.AlignCenter)

        name = QApplication.applicationName()
        version = QApplication.applicationVersion()

        text = ABOUT_TEMPLATE.format(
            name=escape(name),
            version=escape(version),
        )
        # TODO: Also list all known add-on versions??.
        text_label = QLabel(text)
        layout.addWidget(text_label, Qt.AlignCenter)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Close, Qt.Horizontal, self)
        layout.addWidget(buttons)
        buttons.rejected.connect(self.accept)
        layout.setSizeConstraint(QVBoxLayout.SetFixedSize)
        self.setLayout(layout)

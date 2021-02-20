from AnyQt.QtCore import Qt
from AnyQt.QtGui import QColor

from orangecanvas.gui.test import QAppTestCase
from orangecanvas.gui.utils import foreground_for_background


class TestUtils(QAppTestCase):
    def test_fg_for_bg(self):
        w = QColor(Qt.white)
        self.assertEqual(
            foreground_for_background(w).name(),
            '#000000'
        )
        b = QColor(Qt.black)
        self.assertEqual(
            foreground_for_background(b).name(),
            '#ffffff'
        )

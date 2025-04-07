from AnyQt.QtCore import QRectF
from AnyQt.QtWidgets import QGraphicsScene

from orangecanvas.canvas.utils import grab_svg
from orangecanvas.gui.test import QAppTestCase


class TestUtils(QAppTestCase):
    def test_grab_svg(self):
        scene = QGraphicsScene()
        scene.addRect(QRectF(0, 0, 10, 10))
        svg = grab_svg(scene)
        self.assertIn("<svg ", svg)
        self.assertIn("<rect", svg)

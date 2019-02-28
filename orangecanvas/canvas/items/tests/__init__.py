"""
Tests for items
"""
from AnyQt.QtWidgets import QGraphicsScene, QGraphicsView
from AnyQt.QtGui import QPainter

from orangecanvas.gui.test import QAppTestCase


class TestItems(QAppTestCase):
    def setUp(self):
        super().setUp()

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(
            QPainter.Antialiasing |
            QPainter.SmoothPixmapTransform |
            QPainter.TextAntialiasing
        )
        self.view.resize(500, 300)
        self.view.show()

    def tearDown(self):
        self.scene.clear()
        self.scene.deleteLater()
        self.view.deleteLater()
        del self.scene
        del self.view
        super().tearDown()

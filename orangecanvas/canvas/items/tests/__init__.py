"""
Tests for items
"""
import sys
import traceback

from AnyQt.QtWidgets import QGraphicsScene, QGraphicsView
from AnyQt.QtGui import QPainter

from orangecanvas.gui.test import QAppTestCase


class TestItems(QAppTestCase):
    def setUp(self):
        super(TestItems, self).setUp()

        self.scene = QGraphicsScene()
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(
            QPainter.Antialiasing |
            QPainter.SmoothPixmapTransform |
            QPainter.TextAntialiasing
        )
        self.view.resize(500, 300)
        self.view.show()

        def my_excepthook(etype, value, tb):
            sys.setrecursionlimit(1010)
            traceback.print_exception(etype, value, tb)

        self._orig_excepthook = sys.excepthook
        sys.excepthook = my_excepthook

    def tearDown(self):
        self.scene.clear()
        self.scene.deleteLater()
        self.view.deleteLater()
        del self.scene
        del self.view
        self.app.processEvents()
        sys.excepthook = self._orig_excepthook
        super().tearDown()

from AnyQt.QtCore import QPointF, QRect

from orangecanvas.gui.test import QAppTestCase
from orangecanvas.canvas import view, scene


class TestView(QAppTestCase):
    def setUp(self):
        super().setUp()
        self.scene = scene.CanvasScene()
        self.view = view.CanvasView(self.scene)
        self.view.resize(420, 420)
        self.scene.setSceneRect(0, 0, 400, 400)

    def tearDown(self):
        self.scene.clear()
        del self.view
        del self.scene
        super().tearDown()

    def test_view_pinch_zoom(self):
        # Missing QTest.touchEvent in PyQt; cannot properly simulate touch
        # events so test this the ugly way.
        anchor = QPointF(350, 350)
        self.view._CanvasView__setZoomLevel(5.0, anchor)
        mapped = self.view.mapFromScene(anchor)
        self.assertTrue(self.view.viewport().rect().contains(mapped))

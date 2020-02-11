import unittest
import os

from orangecanvas import resources
from orangecanvas.resources import icon_loader


class TestIconLoader(unittest.TestCase):
    def setUp(self):
        from AnyQt.QtWidgets import QApplication
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])

    def test_loader(self):
        loader = icon_loader()
        self.assertEqual(loader.search_paths(), resources.DEFAULT_SEARCH_PATHS)
        icon = loader.get("icons/CanvasIcon.png")
        self.assertTrue(not icon.isNull())

        path = loader.find(":icons/Arrow.svg")
        self.assertTrue(os.path.isfile(path))
        icon = loader.get(":icons/CanvasIcon.png")
        self.assertTrue(not icon.isNull())

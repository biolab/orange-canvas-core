from AnyQt.QtCore import QSize, Qt
from AnyQt.QtGui import QIcon, QPixmap, QColor, QPalette

from ..iconengine import SymbolIconEngine

from ..test import QAppTestCase


class TestSymbolIconEngine(QAppTestCase):
    def test(self):
        pm = QPixmap(10, 10)
        pm.fill(QColor(0, 0, 0))
        base = QIcon()
        base.addPixmap(pm)
        engine = SymbolIconEngine(base)
        palette = QPalette()
        palette.setColor(QPalette.Text, QColor(200, 200, 200))
        palette.setColor(QPalette.Base, QColor(Qt.black))
        with SymbolIconEngine.setOverridePalette(palette):
            img = engine.pixmap(QSize(10, 10), QIcon.Active, QIcon.Off).toImage()
        pixel = QColor(img.pixel(5, 5))
        self.assertEqual(QColor(pixel).name(), palette.text().color().name())

        palette.setColor(QPalette.Text, QColor(Qt.black))
        palette.setColor(QPalette.Base, QColor(Qt.white))
        with SymbolIconEngine.setOverridePalette(palette):
            img = engine.pixmap(QSize(10, 10), QIcon.Active, QIcon.Off).toImage()
        pixel = QColor(img.pixel(5, 5))
        self.assertEqual(QColor(pixel).name(), QColor(0, 0, 0).name())

from AnyQt.QtCore import Qt
from AnyQt.QtTest import QTest, QSignalSpy

from ..breadcrumbs import Breadcrumbs
from ..test import QAppTestCase


class TestBreadcrumbs(QAppTestCase):
    def test(self):
        w = Breadcrumbs()
        w.grab()
        w.setBreadcrumbs([])
        w.setBreadcrumbs(["A"])
        w.setBreadcrumbs([])
        w.setBreadcrumbs(["A" * 10, "B" * 10, "c" * 10])
        w.adjustSize()
        w.grab()

    def test_activated(self):
        w = Breadcrumbs()
        w.setBreadcrumbs(["AA" * 5, "BB" * 5, "CC" * 5])
        w.adjustSize()
        rect = w.rect()
        spy = QSignalSpy(w.activated)
        QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, rect.center())
        self.assertSequenceEqual(list(spy), [[1]])

"""
Basic Qt testing framework
==========================
"""
import unittest

import gc

from AnyQt.QtWidgets import QApplication
from AnyQt.QtCore import QCoreApplication, QTimer
from AnyQt.QtTest import QTest


class QCoreAppTestCase(unittest.TestCase):
    _AppClass = QCoreApplication

    @classmethod
    def setUpClass(cls):
        super(QCoreAppTestCase, cls).setUpClass()
        app = cls._AppClass.instance()
        if app is None:
            app = cls._AppClass([])
        cls.app = app

    def setUp(self):
        super(QCoreAppTestCase, self).setUp()
        self._quittimer = QTimer(singleShot=True, interval=10000)
        self._quittimer.timeout.connect(self.app.quit)
        self._quittimer.start()

    def tearDown(self):
        self._quittimer.stop()
        self._quittimer.timeout.disconnect(self.app.quit)
        self._quittimer = None
        super(QCoreAppTestCase, self).tearDown()

    @classmethod
    def tearDownClass(cls):
        gc.collect()
        cls.app = None

    # def singleShot(self, *args):
    #     QTimer.singleShot(*args)


class QAppTestCase(QCoreAppTestCase):
    _AppClass = QApplication

    def tearDown(self):
        if hasattr(self, "scene"):
            self.scene.clear()
            self.scene.deleteLater()
            del self.scene

    # def singleShot(self, *args):
    #     QTimer.singleShot(*args)

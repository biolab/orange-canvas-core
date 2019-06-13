"""
Basic Qt testing framework
==========================
"""
import unittest

import gc

from AnyQt.QtWidgets import QApplication, QWidget
from AnyQt.QtCore import QCoreApplication, QTimer, QStandardPaths, QPoint, Qt
from AnyQt.QtGui import QMouseEvent
from AnyQt.QtTest import QTest


class QCoreAppTestCase(unittest.TestCase):
    _AppClass = QCoreApplication

    __appdomain = ""
    __appname = ""

    @classmethod
    def setUpClass(cls):
        super(QCoreAppTestCase, cls).setUpClass()
        QStandardPaths.setTestModeEnabled(True)
        app = cls._AppClass.instance()
        if app is None:
            app = cls._AppClass([])
        cls.app = app
        cls.__appname = cls.app.applicationName()
        cls.__appdomain = cls.app.organizationDomain()
        cls.app.setApplicationName("orangecanvas.testing")
        cls.app.setOrganizationDomain("biolab.si")

    def setUp(self):
        super(QCoreAppTestCase, self).setUp()
        self._quittimer = QTimer(interval=100)
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
        cls.app.setApplicationName(cls.__appname)
        cls.app.setOrganizationDomain(cls.__appdomain)
        cls.app = None
        super(QCoreAppTestCase, cls).tearDownClass()
        QStandardPaths.setTestModeEnabled(False)


class QAppTestCase(QCoreAppTestCase):
    _AppClass = QApplication

    def tearDown(self):
        QTest.qWait(10)
        super(QAppTestCase, self).tearDown()


def mouseMove(widget, buttons, modifier=Qt.NoModifier, pos=QPoint(), delay=-1):
    # type: (QWidget, Qt.MouseButtons, Qt.KeyboardModifier, QPoint, int) -> None
    """
    Like QTest.mouseMove, but with `buttons` and `modifier` parameters.

    Parameters
    ----------
    widget : QWidget
    buttons: Qt.MouseButtons
    modifier : Qt.KeyboardModifiers
    pos : QPoint
    delay : int
    """
    if pos.isNull():
        pos = widget.rect().center()
    me = QMouseEvent(
        QMouseEvent.MouseMove, pos, widget.mapToGlobal(pos), Qt.NoButton,
        buttons, modifier
    )
    if delay > 0:
        QTest.qWait(delay)

    QCoreApplication.sendEvent(widget, me)

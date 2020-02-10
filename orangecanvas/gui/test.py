"""
Basic Qt testing framework
==========================
"""
import unittest
import gc
from typing import Callable, Any

from AnyQt.QtWidgets import QApplication, QWidget
from AnyQt.QtCore import QCoreApplication, QTimer, QStandardPaths, QPoint, Qt
from AnyQt.QtGui import QMouseEvent
from AnyQt.QtTest import QTest
from AnyQt.QtCore import PYQT_VERSION

DEFAULT_TIMEOUT = 50


class QCoreAppTestCase(unittest.TestCase):
    _AppClass = QCoreApplication
    app = None  # type: QCoreApplication

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

    def tearDown(self):
        super(QCoreAppTestCase, self).tearDown()

    @classmethod
    def tearDownClass(cls):
        gc.collect()
        cls.app.setApplicationName(cls.__appname)
        cls.app.setOrganizationDomain(cls.__appdomain)
        cls.app.sendPostedEvents(None, 0)
        # Keep app instance alive between tests with PyQt5 5.14.0 and later
        if PYQT_VERSION <= 0x050e00:
            cls.app = None
        super(QCoreAppTestCase, cls).tearDownClass()
        QStandardPaths.setTestModeEnabled(False)

    @classmethod
    def qWait(cls, timeout=DEFAULT_TIMEOUT):
        QTest.qWait(timeout)

    @classmethod
    def singleShot(cls, timeout: int, slot: 'Callable[[], Any]'):
        QTimer.singleShot(timeout, slot)


class QAppTestCase(QCoreAppTestCase):
    _AppClass = QApplication
    app = None  # type: QApplication


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

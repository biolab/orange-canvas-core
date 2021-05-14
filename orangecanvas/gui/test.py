"""
Basic Qt testing framework
==========================
"""
import unittest
import gc
from typing import Callable, Any

from AnyQt.QtWidgets import QApplication, QWidget
from AnyQt.QtCore import (
    QCoreApplication, QTimer, QStandardPaths, QPoint, Qt, QMimeData, QPointF
)
from AnyQt.QtGui import (
    QMouseEvent, QDragEnterEvent, QDropEvent, QDragMoveEvent, QDragLeaveEvent,
    QContextMenuEvent
)
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
        QMouseEvent.MouseMove, QPointF(pos), QPointF(widget.mapToGlobal(pos)),
        Qt.NoButton, buttons, modifier
    )
    if delay > 0:
        QTest.qWait(delay)

    QCoreApplication.sendEvent(widget, me)


def contextMenu(widget: QWidget, pos: QPoint, delay=-1) -> None:
    """
    Simulates a contextMenuEvent on the widget.
    """
    ev = QContextMenuEvent(
        QContextMenuEvent.Mouse, pos, widget.mapToGlobal(pos)
    )
    if delay > 0:
        QTest.qWait(delay)
    QCoreApplication.sendEvent(widget, ev)


def dragDrop(
        widget: QWidget, mime: QMimeData, pos: QPoint = QPoint(),
        action=Qt.CopyAction, buttons=Qt.LeftButton, modifiers=Qt.NoModifier
) -> bool:
    """
    Simulate a drag/drop interaction on the `widget`.

    A `QDragEnterEvent`, `QDragMoveEvent` and `QDropEvent` are created and
    dispatched to the `widget`. However if any of the `QDragEnterEvent` or
    `QDragMoveEvent` are not accepted, a `QDragLeaveEvent` is dispatched
    to 'reset' the widget state before this function returns `False`

    Parameters
    ----------
    widget: QWidget
        The target widget.
    mime: QMimeData
        The mime data associated with the drag/drop.
    pos: QPoint
        Position of the drop
    action: Qt.DropActions
        Type of acceptable drop actions
    buttons: Qt.MouseButtons:
        Pressed mouse buttons.
    modifiers: Qt.KeyboardModifiers
        Pressed keyboard modifiers.

    Returns
    -------
    state: bool
        Were the events accepted.

    See Also
    --------
    QDragEnterEvent, QDropEvent
    """
    if pos.isNull():
        pos = widget.rect().center()

    ev = QDragEnterEvent(pos, action, mime, buttons, modifiers)
    ev.setAccepted(False)
    QApplication.sendEvent(widget, ev)

    ev = QDragMoveEvent(pos, action, mime, buttons, modifiers)
    ev.setAccepted(False)
    QApplication.sendEvent(widget, ev)

    if not ev.isAccepted():
        QApplication.sendEvent(widget, QDragLeaveEvent())
        return False

    ev = QDropEvent(QPointF(pos), action, mime, buttons, modifiers)
    ev.setAccepted(False)
    QApplication.sendEvent(widget, ev)
    return ev.isAccepted()


def dragEnterLeave(
        widget: QWidget, mime: QMimeData, pos=QPoint(),
        action=Qt.CopyAction, buttons=Qt.LeftButton, modifiers=Qt.NoModifier
) -> None:
    """
    Simulate a drag/move/leave interaction on the `widget`.

    A QDragEnterEvent, QDragMoveEvent and a QDragLeaveEvent are created
    and dispatched to the widget.
    """
    if pos.isNull():
        pos = widget.rect().center()

    ev = QDragEnterEvent(pos, action, mime, buttons, modifiers)
    ev.setAccepted(False)
    QApplication.sendEvent(widget, ev)

    ev = QDragMoveEvent(
        pos, action, mime, buttons, modifiers, QDragMoveEvent.DragMove
    )
    ev.setAccepted(False)
    QApplication.sendEvent(widget, ev)

    ev = QDragLeaveEvent()
    ev.setAccepted(False)
    QApplication.sendEvent(widget, ev)
    return

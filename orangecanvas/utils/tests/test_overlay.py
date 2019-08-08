# pylint: disable=protected-access

import unittest.mock

from AnyQt.QtCore import Qt, QEvent
from AnyQt.QtTest import QTest
from AnyQt.QtWidgets import QWidget, QApplication

from orangecanvas.gui.test import QAppTestCase
from orangecanvas.utils.overlay import NotificationWidget, NotificationOverlay, Notification, \
    NotificationServer


class TestOverlay(QAppTestCase):
    def setUp(self) -> None:
        self.container = QWidget()
        self.overlay = NotificationOverlay(self.container)
        self.server = NotificationServer()

        self.server.newNotification.connect(self.overlay.addNotification)
        self.server.nextNotification.connect(self.overlay.nextWidget)

        self.notif = Notification(title="Hello world!",
                                  text="Welcome to the testing grounds – this is where your resolve"
                                       "and stability will be tried and tested.",
                                  accept_button_label="Ok")

    def tearDown(self) -> None:
        self.container = None
        self.overlay = None
        self.notif = None
        self.server = None

    def test_notification_widget(self):
        stdb = NotificationWidget.Ok | NotificationWidget.Close
        notifw = NotificationWidget(self.overlay,
                                    title="Titl",
                                    text="Tixt",
                                    standardButtons=stdb)

        QApplication.sendPostedEvents(notifw, QEvent.LayoutRequest)
        self.assertTrue(notifw.geometry().isValid())

        button_ok = notifw.button(NotificationWidget.Ok)
        button_close = notifw.button(NotificationWidget.Close)

        self.assertTrue(all([button_ok, button_close]))

        button = notifw.button(NotificationWidget.Ok)
        self.assertIsNot(button, None)
        self.assertEqual(notifw.buttonRole(button),
                         NotificationWidget.AcceptRole)

    def test_notification_dismiss(self):
        mock = unittest.mock.MagicMock()
        self.notif.clicked.connect(mock)
        self.server.registerNotification(self.notif)

        notifw = self.overlay.currentWidget()
        QTest.mouseClick(notifw.dismissButton, Qt.LeftButton)
        mock.assert_called_once_with(self.notif.DismissRole)

    def test_notification_accept(self):
        mock = unittest.mock.MagicMock()
        self.notif.clicked.connect(mock)
        self.server.registerNotification(self.notif)

        notifw = self.overlay.currentWidget()
        b = notifw._msgWidget.button(NotificationWidget.Ok)
        QTest.mouseClick(b, Qt.LeftButton)
        mock.assert_called_once_with(self.notif.AcceptRole)

    def test_two_overlays(self):
        container2 = QWidget()
        overlay2 = NotificationOverlay(container2)

        self.server.newNotification.connect(overlay2.addNotification)
        self.server.nextNotification.connect(overlay2.nextWidget)

        mock = unittest.mock.MagicMock()
        self.notif.accepted.connect(mock)

        self.server.registerNotification(self.notif)

        self.container.show()
        container2.show()

        w1 = self.overlay.currentWidget()
        w2 = overlay2.currentWidget()

        self.assertTrue(w1.isVisible())
        self.assertTrue(w2.isVisible())

        button = w2.button(NotificationWidget.Ok)
        QTest.mouseClick(button, Qt.LeftButton)

        mock.assert_called_once_with()

        self.assertFalse(w1.isVisible())
        self.assertFalse(w2.isVisible())

    def test_queued_notifications(self):
        notif2 = Notification(title="Hello universe!",
                              text="I'm another notif! I'm about to queue behind my older brother.")

        def handle_click(role):
            self.assertEqual(role, Notification.DismissRole)

        self.notif.clicked.connect(handle_click)

        self.server.registerNotification(self.notif)
        notif1 = self.overlay.currentWidget()
        button = notif1.dismissButton

        self.server.registerNotification(notif2)
        notif2 = self.overlay._widgets[1]

        self.container.show()

        self.assertTrue(notif1.isVisible())
        self.assertFalse(notif2.isVisible())

        QTest.mouseClick(button, Qt.LeftButton)

        self.assertFalse(notif1.isVisible())
        self.assertTrue(notif2.isVisible())

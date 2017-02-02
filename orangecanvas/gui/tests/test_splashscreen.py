"""
Test for splashscreen
"""

from datetime import datetime

import pkg_resources

from AnyQt.QtGui import QPixmap
from AnyQt.QtCore import Qt, QRect, QTimer

from ..splashscreen import SplashScreen

from ..test import QAppTestCase
from ... import config


class TestSplashScreen(QAppTestCase):
    def test_splashscreen(self):
        splash = pkg_resources.resource_filename(
                     config.__package__,
                     "icons/orange-splash-screen.png"
                 )
        w = SplashScreen()
        w.setPixmap(QPixmap(splash))
        w.setTextRect(QRect(100, 100, 400, 50))
        w.show()

        def advance_time():
            now = datetime.now()
            time = now.strftime("%c : %f")
            w.showMessage(time, alignment=Qt.AlignCenter)
            i = now.second % 3
            rect = QRect(100, 100 + i * 20, 400, 50)
            w.setTextRect(rect)
            self.assertEqual(w.textRect(), rect)

        timer = QTimer(w, interval=1)
        timer.timeout.connect(advance_time)
        timer.start()

        self.app.exec_()

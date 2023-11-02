"""
Test for splashscreen
"""
import pkgutil
from datetime import datetime

from AnyQt.QtGui import QPixmap, QImage
from AnyQt.QtCore import Qt, QRect, QTimer

from ..splashscreen import SplashScreen

from ..test import QAppTestCase
from ... import config


class TestSplashScreen(QAppTestCase):
    def test_splashscreen(self):
        contents = pkgutil.get_data(
            config.__package__, "icons/orange-canvas-core-splash.svg"
        )
        img = QImage.fromData(contents)
        w = SplashScreen()
        w.setPixmap(QPixmap.fromImage(img))
        w.setTextRect(QRect(100, 100, 400, 50))
        w.show()

        def advance_time():
            now = datetime.now()
            time = now.strftime("%c : %f")
            i = now.second % 3
            if i == 2:
                w.setTextFormat(Qt.RichText)
                time = "<i>" + time + "</i>"
            else:
                w.setTextFormat(Qt.PlainText)

            w.showMessage(time, alignment=Qt.AlignCenter)

            rect = QRect(100, 100 + i * 20, 400, 50)
            w.setTextRect(rect)

            self.assertEqual(w.textRect(), rect)

        timer = QTimer(w, interval=1)
        timer.timeout.connect(advance_time)
        timer.start()
        self.qWait()
        timer.stop()
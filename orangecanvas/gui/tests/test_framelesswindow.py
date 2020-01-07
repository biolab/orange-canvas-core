from AnyQt.QtCore import QTimer
from ..framelesswindow import FramelessWindow

from ..test import QAppTestCase


class TestFramelessWindow(QAppTestCase):
    def test_framelesswindow(self):
        window = FramelessWindow()
        window.show()
        window.setRadius(5)

        def cycle():
            window.setRadius((window.radius() + 3) % 30)

        timer = QTimer(window, interval=50)
        timer.timeout.connect(cycle)
        timer.start()
        self.qWait()
        timer.stop()

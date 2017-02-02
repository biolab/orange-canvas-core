from AnyQt.QtCore import QTimer
from ..framelesswindow import FramelessWindow

from ..test import QAppTestCase


class TestFramelessWindow(QAppTestCase):
    def test_framelesswindow(self):
        window = FramelessWindow()
        window.show()

        def cycle():
            window.setRadius((window.radius() + 3) % 30)

        timer = QTimer(window, interval=250)
        timer.timeout.connect(cycle)
        timer.start()
        self.app.exec_()

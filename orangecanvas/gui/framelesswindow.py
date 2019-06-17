"""
A frameless window widget
"""
from typing import Optional, Any

from AnyQt.QtWidgets import QWidget, QStyleOption
from AnyQt.QtGui import QPalette, QPainter, QBitmap, QPaintEvent
from AnyQt.QtCore import Qt, pyqtProperty as Property

from .utils import is_transparency_supported, StyledWidget_paintEvent


class FramelessWindow(QWidget):
    """
    A basic frameless window widget with rounded corners (if supported by
    the windowing system).
    """
    def __init__(self, parent=None, radius=6, **kwargs):
        # type: (Optional[QWidget], int, Any) -> None
        super().__init__(parent, **kwargs)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

        self.__radius = radius
        self.__isTransparencySupported = is_transparency_supported()
        self.setAttribute(Qt.WA_TranslucentBackground,
                          self.__isTransparencySupported)

    def setRadius(self, radius):
        # type: (int) -> None
        """
        Set the window rounded border radius.
        """
        if self.__radius != radius:
            self.__radius = radius
            if not self.__isTransparencySupported:
                self.__updateMask()
            self.update()

    def radius(self):
        # type: () -> int
        """
        Return the border radius.
        """
        return self.__radius

    radius_ = Property(int, fget=radius, fset=setRadius,
                       designable=True,
                       doc="Window border radius")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.__isTransparencySupported:
            self.__updateMask()

    def __updateMask(self):
        # type: () -> None
        opt = QStyleOption()
        opt.initFrom(self)
        rect = opt.rect

        size = rect.size()
        mask = QBitmap(size)

        p = QPainter(mask)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(Qt.black)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(rect, self.__radius, self.__radius)
        p.end()

        self.setMask(mask)

    def paintEvent(self, event):
        # type: (QPaintEvent) -> None
        if self.__isTransparencySupported:
            opt = QStyleOption()
            opt.initFrom(self)
            rect = opt.rect

            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setBrush(opt.palette.brush(QPalette.Window))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect, self.__radius, self.__radius)
            p.end()
        else:
            StyledWidget_paintEvent(self, event)

"""
A splash screen widget with support for positioning of the message text.

"""
from typing import Union

from AnyQt.QtWidgets import QSplashScreen, QWidget
from AnyQt.QtGui import (
    QPixmap, QPainter, QTextDocument, QTextBlockFormat, QTextCursor, QColor
)
from AnyQt.QtCore import Qt, QRect, QEvent

from .utils import is_transparency_supported

if hasattr(Qt, "mightBeRichText"):
    mightBeRichText = Qt.mightBeRichText
else:
    def mightBeRichText(text):
        return False


class SplashScreen(QSplashScreen):
    """
    Splash screen widget.

    Parameters
    ----------
    parent : :class:`QWidget`
        Parent widget

    pixmap : :class:`QPixmap`
        Splash window pixmap.

    textRect : :class:`QRect`
        Bounding rectangle of the shown message on the widget.

    textFormat : Qt.TextFormat
        How message text format should be interpreted.
    """
    def __init__(self, parent=None, pixmap=None, textRect=None,
                 textFormat=Qt.PlainText, **kwargs):
        super().__init__(parent, **kwargs)
        self.__textRect = textRect or QRect()
        self.__message = ""
        self.__color = Qt.black
        self.__alignment = Qt.AlignLeft
        self.__textFormat = textFormat
        self.__pixmap = QPixmap()

        if pixmap is None:
            pixmap = QPixmap()

        self.setPixmap(pixmap)

        self.setAutoFillBackground(False)
        # Also set FramelessWindowHint (if not already set)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)

    def setTextRect(self, rect):
        # type: (QRect) -> None
        """
        Set the rectangle (:class:`QRect`) in which to show the message text.
        """
        if self.__textRect != rect:
            self.__textRect = QRect(rect)
            self.update()

    def textRect(self):
        # type: () -> QRect
        """
        Return the text message rectangle.
        """
        return QRect(self.__textRect)

    def textFormat(self):
        # type: () -> Qt.TextFormat
        return self.__textFormat

    def setTextFormat(self, format):
        # type: (Qt.TextFormat) -> None
        if format != self.__textFormat:
            self.__textFormat = format
            self.update()

    def showEvent(self, event):
        super().showEvent(event)
        # Raise to top on show.
        self.raise_()

    def drawContents(self, painter):
        # type: (QPainter) -> None
        """
        Reimplementation of drawContents to limit the drawing inside
        `textRect`.
        """
        painter.setPen(self.__color)
        painter.setFont(self.font())

        if self.__textRect.isValid():
            rect = self.__textRect
        else:
            rect = self.rect().adjusted(5, 5, -5, -5)

        tformat = self.__textFormat

        if tformat == Qt.AutoText:
            if mightBeRichText(self.__message):
                tformat = Qt.RichText
            else:
                tformat = Qt.PlainText

        if tformat == Qt.RichText:
            doc = QTextDocument()
            doc.setHtml(self.__message)
            doc.setTextWidth(rect.width())
            cursor = QTextCursor(doc)
            cursor.select(QTextCursor.Document)
            fmt = QTextBlockFormat()
            fmt.setAlignment(self.__alignment)
            cursor.mergeBlockFormat(fmt)
            painter.save()
            painter.translate(rect.topLeft())
            doc.drawContents(painter)
            painter.restore()
        else:
            painter.drawText(rect, self.__alignment, self.__message)

    def showMessage(self, message, alignment=Qt.AlignLeft, color=Qt.black):
        # type: (str, int, Union[QColor, Qt.GlobalColor]) -> None
        """
        Show the `message` with `color` and `alignment`.
        """
        # Need to store all this arguments for drawContents (no access
        # methods)
        self.__alignment = alignment
        self.__color = QColor(color)
        self.__message = message
        super().showMessage(message, alignment, color)

    # Reimplemented to allow graceful fall back if the windowing system
    # does not support transparency.
    def setPixmap(self, pixmap):
        # type: (QPixmap) -> None
        self.setAttribute(Qt.WA_TranslucentBackground,
                          pixmap.hasAlpha() and is_transparency_supported())

        self.__pixmap = QPixmap(pixmap)
        super().setPixmap(pixmap)
        if pixmap.hasAlpha() and not is_transparency_supported():
            self.setMask(pixmap.createHeuristicMask())

    def event(self, event):
        # type: (QEvent) -> bool
        if event.type() == QEvent.Paint:
            pixmap = self.__pixmap
            painter = QPainter(self)
            if not pixmap.isNull():
                painter.drawPixmap(0, 0, pixmap)
            self.drawContents(painter)
            return True
        return super().event(event)

from AnyQt.QtCore import Qt, QSize, QEvent
from AnyQt.QtGui import QPaintEvent
from AnyQt.QtWidgets import QWidget, QSizePolicy, QStyleOption, QStylePainter


class TextLabel(QWidget):
    """A plain text label widget with support for elided text.
    """
    def __init__(self, *args, text="", alignment=Qt.AlignLeft | Qt.AlignVCenter,
                 textElideMode=Qt.ElideMiddle, **kwargs):
        super().__init__(*args, **kwargs)
        self.setSizePolicy(QSizePolicy.Expanding,
                           QSizePolicy.Preferred)
        self.setAttribute(Qt.WA_WState_OwnSizePolicy, True)

        self.__text = text
        self.__textElideMode = textElideMode
        self.__alignment = alignment
        self.__sizeHint = None

    def setText(self, text):  # type: (str) -> None
        """Set the `text` string to display."""
        if self.__text != text:
            self.__text = text
            self.__update()

    def text(self):  # type: () -> str
        """Return the text."""
        return self.__text

    def setTextElideMode(self, mode):  # type: (Qt.TextElideMode ) -> None
        """Set text elide mode (`Qt.TextElideMode`)"""
        if self.__textElideMode != mode:
            self.__textElideMode = mode
            self.__update()

    def elideMode(self):  # type: () -> Qt.TextElideMode
        """Return the text elide mode."""
        return self.__elideMode

    def setAlignment(self, align):  # type: (Qt.Alignment) -> None
        """Set text alignment (`Qt.Alignment`)."""
        if self.__alignment != align:
            self.__alignment = align
            self.__update()

    def alignment(self):  # type: () -> Qt.Alignment
        """Return text alignment."""
        return Qt.Alignment(self.__alignment)

    def sizeHint(self):  # type: () -> QSize
        """Reimplemented."""
        if self.__sizeHint is None:
            option = QStyleOption()
            option.initFrom(self)
            metrics = option.fontMetrics

            self.__sizeHint = QSize(200, metrics.height())

        return self.__sizeHint

    def paintEvent(self, event):  # type: (QPaintEvent) -> None
        """Reimplemented."""
        painter = QStylePainter(self)
        option = QStyleOption()
        option.initFrom(self)

        rect = option.rect
        metrics = option.fontMetrics
        text = metrics.elidedText(self.__text, self.__textElideMode,
                                  rect.width())
        painter.drawItemText(rect, self.__alignment,
                             option.palette, self.isEnabled(), text,
                             self.foregroundRole())
        painter.end()

    def changeEvent(self, event):  # type: (QEvent) -> None
        """Reimplemented."""
        if event.type() == QEvent.FontChange:
            self.__update()
        super().changeEvent(event)

    def __update(self) -> None:
        self.__sizeHint = None
        self.updateGeometry()
        self.update()

"""
"""
import sys
import warnings
import traceback
from types import TracebackType
from typing import Any, Optional, List, Type

from AnyQt.QtWidgets import QWidget, QPlainTextEdit, QVBoxLayout, QSizePolicy
from AnyQt.QtGui import (
    QTextCursor, QTextCharFormat, QFont, QTextOption, QFontDatabase
)
from AnyQt.QtCore import Qt, QObject, QCoreApplication, QThread, QSize
from AnyQt.QtCore import pyqtSignal as Signal, pyqtSlot as Slot


class TerminalView(QPlainTextEdit):
    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None
        super().__init__(*args, **kwargs)
        self.setFrameStyle(QPlainTextEdit.NoFrame)
        self.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)

        try:
            # Since Qt 5.2
            font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        except AttributeError:
            font = self.font()
            font.setStyleHint(QFont.Monospace)
            font.setFamily("Monospace")

        self.setFont(font)
        self.setAttribute(Qt.WA_SetFont, False)

    def sizeHint(self):
        # type: () -> QSize
        metrics = self.fontMetrics()
        width = metrics.boundingRect("X" * 81).width()
        height = metrics.lineSpacing()
        scroll_width = self.verticalScrollBar().width()
        size = QSize(width + scroll_width, height * 25)
        return size


class OutputView(QWidget):
    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QWidget], Any) -> None
        super().__init__(parent, **kwargs)

        self.__lines = 5000

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.__text = TerminalView()
        self.__text.setWordWrapMode(QTextOption.NoWrap)

        self.__currentCharFormat = self.__text.currentCharFormat()

        self.layout().addWidget(self.__text)

    def setMaximumLines(self, lines):
        # type: (int) -> None
        """
        Set the maximum number of lines to keep displayed.
        """
        if self.__lines != lines:
            self.__lines = lines
            self.__text.setMaximumBlockCount(lines)

    def maximumLines(self):
        # type: () -> int
        """
        Return the maximum number of lines in the display.
        """
        return self.__lines

    def clear(self):
        # type: () -> None
        """
        Clear the displayed text.
        """
        assert QThread.currentThread() is self.thread()
        self.__text.clear()

    def setCurrentCharFormat(self, charformat):
        # type: (QTextCharFormat) -> None
        """Set the QTextCharFormat to be used when writing.
        """
        assert QThread.currentThread() is self.thread()
        if self.__currentCharFormat != charformat:
            self.__currentCharFormat = QTextCharFormat(charformat)

    def currentCharFormat(self):
        # type: () -> QTextCharFormat
        return QTextCharFormat(self.__currentCharFormat)

    def toPlainText(self):
        # type: () -> str
        """
        Return the full contents of the output view.
        """
        return self.__text.toPlainText()

    # A file like interface.
    @Slot(str)
    def write(self, string):
        # type: (str) -> None
        assert QThread.currentThread() is self.thread()
        self.__text.moveCursor(QTextCursor.End, QTextCursor.MoveAnchor)
        self.__text.setCurrentCharFormat(self.__currentCharFormat)

        self.__text.insertPlainText(string)

    @Slot(object)
    def writelines(self, lines):
        # type: (List[str]) -> None
        assert QThread.currentThread() is self.thread()
        self.write("".join(lines))

    @Slot()
    def flush(self):
        # type: () -> None
        assert QThread.currentThread() is self.thread()

    def writeWithFormat(self, string, charformat):
        # type: (str, QTextCharFormat) -> None
        assert QThread.currentThread() is self.thread()
        self.__text.moveCursor(QTextCursor.End, QTextCursor.MoveAnchor)
        self.__text.setCurrentCharFormat(charformat)
        self.__text.insertPlainText(string)

    def writelinesWithFormat(self, lines, charformat):
        # type: (List[str], QTextCharFormat) -> None
        assert QThread.currentThread() is self.thread()
        self.writeWithFormat("".join(lines), charformat)

    def formatted(self, color=None, background=None, weight=None,
                  italic=None, underline=None, font=None):
        # type: (...) -> Formatter
        """
        Return a formatted file like object proxy.
        """
        charformat = update_char_format(
            self.currentCharFormat(), color, background, weight,
            italic, underline, font
        )
        return Formatter(self, charformat)

    def formated(self, *args, **kwargs):
        warnings.warn(
            "'Use 'formatted'", DeprecationWarning, stacklevel=2
        )
        return self.formatted(*args, **kwargs)


def update_char_format(baseformat, color=None, background=None, weight=None,
                       italic=None, underline=None, font=None):
    """
    Return a copy of `baseformat` :class:`QTextCharFormat` with
    updated color, weight, background and font properties.

    """
    charformat = QTextCharFormat(baseformat)

    if color is not None:
        charformat.setForeground(color)

    if background is not None:
        charformat.setBackground(background)

    if font is not None:
        charformat.setFont(font)
    else:
        font = update_font(baseformat.font(), weight, italic, underline)
        charformat.setFont(font)

    return charformat


def update_font(basefont, weight=None, italic=None, underline=None,
                pixelSize=None, pointSize=None):
    """
    Return a copy of `basefont` :class:`QFont` with updated properties.
    """
    font = QFont(basefont)

    if weight is not None:
        font.setWeight(weight)

    if italic is not None:
        font.setItalic(italic)

    if underline is not None:
        font.setUnderline(underline)

    if pixelSize is not None:
        font.setPixelSize(pixelSize)

    if pointSize is not None:
        font.setPointSize(pointSize)

    return font


class Formatter(QObject):
    def __init__(self, outputview, charformat):
        # type: (OutputView, QTextCharFormat) -> None
        # Parent to the output view. Ensure the formatter does not outlive it.
        super().__init__(outputview)
        self.outputview = outputview
        self.charformat = charformat

    @Slot(str)
    def write(self, string):
        # type: (str) -> None
        self.outputview.writeWithFormat(string, self.charformat)

    @Slot(object)
    def writelines(self, lines):
        # type: (List[str]) -> None
        self.outputview.writelinesWithFormat(lines, self.charformat)

    @Slot()
    def flush(self):
        # type: () -> None
        self.outputview.flush()

    def formatted(self, color=None, background=None, weight=None,
                  italic=None, underline=None, font=None):
        # type: (...) -> Formatter
        charformat = update_char_format(self.charformat, color, background,
                                        weight, italic, underline, font)
        return Formatter(self.outputview, charformat)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.outputview = None
        self.charformat = None
        self.setParent(None)

    def formated(self, *args, **kwargs):
        warnings.warn(
            "Use 'formatted'", DeprecationWarning, stacklevel=2
        )
        return self.formatted(*args, **kwargs)


class formater(Formatter):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "Deprecated: Renamed to Formatter.",
            DeprecationWarning, stacklevel=2
        )
        super().__init__(*args, **kwargs)


class TextStream(QObject):
    stream = Signal(str)
    flushed = Signal()
    __closed = False

    def close(self):
        # type: () -> None
        self.__closed = True

    def closed(self):
        # type: () -> bool
        return self.__closed

    def isatty(self):
        # type: () -> bool
        return False

    def write(self, string):
        # type: (str) -> None
        if self.__closed:
            raise ValueError("write operation on a closed stream.")
        self.stream.emit(string)

    def writelines(self, lines):
        # type: (List[str]) -> None
        if self.__closed:
            raise ValueError("write operation on a closed stream.")
        self.stream.emit("".join(lines))

    def flush(self):
        # type: () -> None
        if self.__closed:
            raise ValueError("write operation on a closed stream.")
        self.flushed.emit()

    def writeable(self):
        # type: () -> bool
        return True

    def readable(self):
        # type: () -> bool
        return False


class ExceptHook(QObject):
    # Signal emitted with the `sys.exc_info` tuple.
    handledException = Signal(tuple)

    def __init__(self, parent=None, stream=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.stream = stream

    def __call__(self, exc_type, exc_value, tb):
        # type: (Type[BaseException], BaseException, TracebackType) -> None
        if self.stream is None:
            stream = sys.stderr
        else:
            stream = self.stream
        if stream is not None:
            header = exc_type.__name__ + ' Exception'
            if QThread.currentThread() != QCoreApplication.instance().thread():
                header += " (in non-GUI thread)"
            text = traceback.format_exception(exc_type, exc_value, tb)
            text.insert(0, '{:-^79}\n'.format(' ' + header + ' '))
            text.append('-' * 79 + '\n')
            try:
                stream.writelines(text)
                stream.flush()
            except Exception:
                pass

        self.handledException.emit((exc_type, exc_value, tb))

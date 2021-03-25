"""
"""
import io
import sys
import warnings
import traceback
from types import TracebackType
from typing import Any, Optional, List, Type, Iterable, Tuple, Union, Mapping

from AnyQt.QtWidgets import (
    QWidget, QPlainTextEdit, QVBoxLayout, QSizePolicy, QPlainTextDocumentLayout
)
from AnyQt.QtGui import (
    QTextCursor, QTextCharFormat, QTextOption, QFontDatabase, QTextDocument,
    QTextDocumentFragment
)
from AnyQt.QtCore import Qt, QObject, QCoreApplication, QThread, QSize
from AnyQt.QtCore import pyqtSignal as Signal, pyqtSlot as Slot

from orangecanvas.gui.utils import update_char_format
from orangecanvas.utils import findf


class TerminalView(QPlainTextEdit):
    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None
        super().__init__(*args, **kwargs)
        self.setFrameStyle(QPlainTextEdit.NoFrame)
        self.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
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


class TerminalTextDocument(QTextDocument):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.setDocumentLayout(QPlainTextDocumentLayout(self))
        self.__currentCharFormat = QTextCharFormat()
        if 'defaultFont' not in kwargs:
            defaultFont = QFontDatabase.systemFont(QFontDatabase.FixedFont)
            self.setDefaultFont(defaultFont)
        self.__streams = []

    def setCurrentCharFormat(self, charformat: QTextCharFormat) -> None:
        """Set the QTextCharFormat to be used when writing."""
        assert QThread.currentThread() is self.thread()
        if self.__currentCharFormat != charformat:
            self.__currentCharFormat = QTextCharFormat(charformat)

    def currentCharFormat(self) -> QTextCharFormat:
        """Return the current char format."""
        return QTextCharFormat(self.__currentCharFormat)

    def textCursor(self) -> QTextCursor:
        """Return a text cursor positioned at the end of the document."""
        cursor = QTextCursor(self)
        cursor.movePosition(QTextCursor.End, QTextCursor.MoveAnchor)
        cursor.setCharFormat(self.__currentCharFormat)
        return cursor

    # ----------------------
    # A file like interface.
    # ----------------------

    @Slot(str)
    def write(self, string: str) -> None:
        assert QThread.currentThread() is self.thread()
        cursor = self.textCursor()
        cursor.insertText(string)

    @Slot(object)
    def writelines(self, lines: Iterable[str]) -> None:
        assert QThread.currentThread() is self.thread()
        self.write("".join(lines))

    @Slot()
    def flush(self) -> None:
        assert QThread.currentThread() is self.thread()

    def writeWithFormat(self, string: str, charformat: QTextCharFormat) -> None:
        assert QThread.currentThread() is self.thread()
        cursor = self.textCursor()
        cursor.setCharFormat(charformat)
        cursor.insertText(string)

    def writelinesWithFormat(self, lines, charformat):
        # type: (List[str], QTextCharFormat) -> None
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

    __streams: List[Tuple['TextStream', Optional['Formatter']]]

    def connectedStreams(self) -> List['TextStream']:
        """Return all streams connected using `connectStream`."""
        return [s for s, _ in self.__streams]

    def connectStream(
            self, stream: 'TextStream',
            charformat: Optional[QTextCharFormat] = None,
            **kwargs
    ) -> None:
        """
        Connect a :class:`TextStream` instance to this document.

        The `stream` connection will be 'inherited' by `clone()`
        """
        if kwargs and charformat is not None:
            raise TypeError("'charformat' and kwargs cannot be used together")
        if kwargs:
            charformat = update_char_format(QTextCharFormat(), **kwargs)
        writer: Optional[Formatter] = None
        if charformat is not None:
            writer = Formatter(self, charformat)
        self.__streams.append((stream, writer))
        if writer is not None:
            stream.stream.connect(writer.write)
        else:
            stream.stream.connect(self.write)

    def disconnectStream(self, stream: 'TextStream'):
        """
        Disconnect a :class:`TextStream` instance from this document.
        """
        item = findf(self.__streams, lambda t: t[0] is stream)
        if item is not None:
            self.__streams.remove(item)
            _, writer = item
            if writer is not None:
                stream.stream.disconnect(writer.write)
            else:
                stream.stream.disconnect(self.write)

    def clone(self, parent=None) -> 'TerminalTextDocument':
        """Create a new TerminalTextDocument that is a copy of this document."""
        clone = type(self)()
        clone.setParent(parent)
        clone.setDocumentLayout(QPlainTextDocumentLayout(clone))
        cursor = QTextCursor(clone)
        cursor.insertFragment(QTextDocumentFragment(self))
        clone.rootFrame().setFrameFormat(self.rootFrame().frameFormat())
        clone.setDefaultStyleSheet(self.defaultStyleSheet())
        clone.setDefaultFont(self.defaultFont())
        clone.setDefaultTextOption(self.defaultTextOption())
        clone.setCurrentCharFormat(self.currentCharFormat())
        for s, w in self.__streams:
            clone.connectStream(s, w.charformat if w is not None else None)
        return clone


class OutputView(QWidget):
    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QWidget], Any) -> None
        super().__init__(parent, **kwargs)

        self.__lines = 5000

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.__text = TerminalView()
        self.__text.setDocument(TerminalTextDocument(self.__text))
        self.__text.setWordWrapMode(QTextOption.NoWrap)
        self.__text.setMaximumBlockCount(self.__lines)

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
        self.document().setCurrentCharFormat(charformat)

    def currentCharFormat(self):
        # type: () -> QTextCharFormat
        return QTextCharFormat(self.document().currentCharFormat())

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
        doc = self.document()
        doc.write(string)

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
        doc = self.document()
        doc.writeWithFormat(string, charformat)

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

    def document(self) -> TerminalTextDocument:
        return self.__text.document()

    def setDocument(self, document: TerminalTextDocument) -> None:
        document.setMaximumBlockCount(self.__lines)
        document.setDefaultFont(self.__text.font())
        self.__text.setDocument(document)

    def formated(self, *args, **kwargs):
        warnings.warn(
            "'Use 'formatted'", DeprecationWarning, stacklevel=2
        )
        return self.formatted(*args, **kwargs)


class Formatter(QObject):
    def __init__(self, outputview, charformat):
        # type: (Union[TerminalTextDocument, OutputView], QTextCharFormat) -> None
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

    def seekable(self):
        # type: () -> bool
        return False

    encoding = None
    errors = None
    newlines = None
    buffer = None

    def detach(self):
        raise io.UnsupportedOperation("detach")

    def read(self, size=-1):
        raise io.UnsupportedOperation("read")

    def readline(self, size=-1):
        raise io.UnsupportedOperation("readline")

    def readlines(self):
        raise io.UnsupportedOperation("readlines")

    def fileno(self):
        raise io.UnsupportedOperation("fileno")

    def seek(self, offset, whence=io.SEEK_SET):
        raise io.UnsupportedOperation("seek")

    def tell(self):
        raise io.UnsupportedOperation("tell")


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

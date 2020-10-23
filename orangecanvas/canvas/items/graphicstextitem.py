from typing import Optional, Iterable

from AnyQt.QtCore import Qt, QEvent
from AnyQt.QtGui import (
    QTextDocument, QTextBlock, QTextLine, QPalette, QPainter, QPen, QPainterPath
)
from AnyQt.QtWidgets import (
    QGraphicsTextItem, QStyleOptionGraphicsItem, QStyle, QWidget, QApplication,
)

from orangecanvas.utils import set_flag


class GraphicsTextItem(QGraphicsTextItem):
    """
    A graphics text item displaying the text highlighted when selected.
    """
    def __init__(self, *args, **kwargs):
        self.__selected = False
        self.__palette = QPalette()
        self.__content = ""
        #: The cached text background shape when this item is selected
        self.__cachedBackgroundPath = None  # type: Optional[QPainterPath]
        self.__styleState = QStyle.State(0)
        super().__init__(*args, **kwargs)
        layout = self.document().documentLayout()
        layout.update.connect(self.__onLayoutChanged)

    def __onLayoutChanged(self):
        self.__cachedBackgroundPath = None
        self.update()

    def setStyleState(self, flags):
        if self.__styleState != flags:
            self.__styleState = flags
            self.__updateDefaultTextColor()
            self.update()

    def styleState(self):
        return self.__styleState

    def paint(self, painter, option, widget=None):
        # type: (QPainter, QStyleOptionGraphicsItem, Optional[QWidget]) -> None
        state = option.state | self.__styleState
        if state & (QStyle.State_Selected | QStyle.State_HasFocus):
            path = self.__textBackgroundPath()
            palette = self.palette()
            if state & QStyle.State_Enabled:
                cg = QPalette.Active
            else:
                cg = QPalette.Inactive
            if widget is not None:
                window = widget.window()
                if not window.isActiveWindow():
                    cg = QPalette.Inactive

            color = palette.color(
                cg,
                QPalette.Highlight if state & QStyle.State_Selected
                else QPalette.Light
            )

            painter.save()
            painter.setPen(QPen(Qt.NoPen))
            painter.setBrush(color)
            painter.drawPath(path)
            painter.restore()

        super().paint(painter, option, widget)

    def __textBackgroundPath(self) -> QPainterPath:
        # return a path outlining all the text lines.
        if self.__cachedBackgroundPath is None:
            self.__cachedBackgroundPath = text_outline_path(self.document())
        return self.__cachedBackgroundPath

    def setSelectionState(self, state):
        # type: (bool) -> None
        state = set_flag(self.__styleState, QStyle.State_Selected, state)
        if self.__styleState != state:
            self.__styleState = state
            self.__updateDefaultTextColor()
            self.update()

    def setPalette(self, palette):
        # type: (QPalette) -> None
        if self.__palette != palette:
            self.__palette = QPalette(palette)
            QApplication.sendEvent(self, QEvent(QEvent.PaletteChange))

    def palette(self):
        # type: () -> QPalette
        palette = QPalette(self.__palette)
        parent = self.parentWidget()
        scene = self.scene()
        if parent is not None:
            return parent.palette().resolve(palette)
        elif scene is not None:
            return scene.palette().resolve(palette)
        else:
            return palette

    def __updateDefaultTextColor(self):
        # type: () -> None
        if self.__styleState & QStyle.State_Selected:
            role = QPalette.HighlightedText
        else:
            role = QPalette.WindowText
        self.setDefaultTextColor(self.palette().color(role))

    def setHtml(self, contents):
        # type: (str) -> None
        if contents != self.__content:
            self.__content = contents
            self.__cachedBackgroundPath = None
            super().setHtml(contents)

    def event(self, event) -> bool:
        if event.type() == QEvent.PaletteChange:
            self.__updateDefaultTextColor()
            self.update()
        return super().event(event)


def iter_blocks(doc):
    # type: (QTextDocument) -> Iterable[QTextBlock]
    block = doc.begin()
    while block != doc.end():
        yield block
        block = block.next()


def iter_lines(doc):
    # type: (QTextDocument) -> Iterable[QTextLine]
    for block in iter_blocks(doc):
        blocklayout = block.layout()
        for i in range(blocklayout.lineCount()):
            yield blocklayout.lineAt(i)


def text_outline_path(doc: QTextDocument) -> QPainterPath:
    # return a path outlining all the text lines.
    margin = doc.documentMargin()
    path = QPainterPath()
    offset = min(margin, 2)
    for line in iter_lines(doc):
        rect = line.naturalTextRect()
        rect.translate(margin, margin)
        rect = rect.adjusted(-offset, -offset, offset, offset)
        p = QPainterPath()
        p.addRoundedRect(rect, 3, 3)
        path = path.united(p)
    return path

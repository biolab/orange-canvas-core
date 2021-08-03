from dataclasses import dataclass, field
from typing import Sequence, List

from AnyQt.QtCore import Qt, Signal, QSize, QRect, QEvent, QMargins, QPoint
from AnyQt.QtGui import (
    QPainter, QIcon, QPaintEvent, QPalette, QResizeEvent, QMouseEvent
)
from AnyQt.QtWidgets import (
    QFrame, QSizePolicy, QStyleOption, QStyle, QHBoxLayout, QSpacerItem,

)


class Breadcrumbs(QFrame):
    @dataclass
    class Item:
        text: str
        rect: QRect = field(default_factory=QRect)

    activated = Signal(int)

    def __init__(self, *args, **kwargs) -> None:
        sp = kwargs.pop("sizePolicy", None)
        super().__init__(*args, **kwargs)
        if sp is None:
            sp = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
            self.setSizePolicy(sp)
            self.setAttribute(Qt.WA_WState_OwnSizePolicy, True)
        self.__items: List[Breadcrumbs.Item] = []
        self.__layout = QHBoxLayout()
        self.__layout.setContentsMargins(0, 0, 0, 0)
        self.__layout.setSpacing(0)
        self.__separator_symbol = "▸"
        self.__text_margins = QMargins(3, 0, 3, 0)
        self.__pressed = -1

    def setBreadcrumbs(self, items: Sequence[str]) -> None:
        self.__items = [Breadcrumbs.Item(text, QIcon(), ) for text in items]
        layout = self.__layout
        for i in reversed(range(self.__layout.count())):
            layout.takeAt(i)
        for i in range(len(self.__items)):
            layout.addSpacerItem(
                QSpacerItem(0, 0, QSizePolicy.Preferred, QSizePolicy.Minimum)
            )
        layout.addSpacerItem(
            QSpacerItem(0, 0, QSizePolicy.Expanding, QSizePolicy.Minimum)
        )
        self.update()
        self.updateGeometry()
        self.__do_layout()

    def breadcrumbs(self) -> Sequence[str]:
        return [it.text for it in self.__items]

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.__do_layout()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() in (
                QEvent.ContentsRectChange,
                QEvent.FontChange,
                QEvent.StyleChange,
        ):
            self.__do_layout()
        super().changeEvent(event)

    def sizeHint(self) -> QSize:
        margins = self.contentsMargins()
        option = QStyleOption()
        option.initFrom(self)
        fm = option.fontMetrics
        width = 0
        separator_width = fm.horizontalAdvance(self.__separator_symbol)
        text_margins = self.__text_margins.left() + self.__text_margins.right()
        N = len(self.__items)
        for item in self.__items:
            width += fm.horizontalAdvance(item.text) + text_margins
        width += max(0, N - 1) * separator_width
        height = fm.height()
        sh = QSize(width + margins.left() + margins.right(),
                   height + margins.top() + margins.bottom())
        return sh

    def __do_layout(self):
        layout = self.__layout
        fm = self.fontMetrics()
        height = fm.height()
        N = len(self.__items)
        separator_width = fm.horizontalAdvance(self.__separator_symbol)
        margins = self.__text_margins.left() + self.__text_margins.right()
        for i, item in enumerate(self.__items):
            if N > 1 and (i == 0 or i == N - 1):
                hpolicy = QSizePolicy.Minimum
            else:
                hpolicy = QSizePolicy.Preferred
            spacing_adjust = separator_width if N > 1 and i != N - 1 else 0
            spacer = layout.itemAt(i).spacerItem()
            spacer.changeSize(
                fm.horizontalAdvance(item.text, ) + margins + spacing_adjust,
                height, hpolicy, QSizePolicy.Minimum
            )
        self.__layout.setGeometry(self.contentsRect())
        self.__layout.activate()
        for i, item in enumerate(self.__items):
            item.rect = layout.itemAt(i).geometry()

    def __componentAt(self, pos: QPoint) -> int:
        for i, item in enumerate(self.__items):
            if item.rect.contains(pos):
                return i
        return -1

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.LeftButton:
            self.__pressed = self.__componentAt(event.pos())
            self.update()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.LeftButton:
            event.ignore()
            return
        pressed = self.__componentAt(event.pos())
        if pressed == self.__pressed and pressed >= 0:
            self.activated.emit(pressed)
        self.__pressed = -1
        super().mouseReleaseEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setClipRect(event.rect())
        style = self.style()
        option = QStyleOption()
        option.initFrom(self)
        fm = option.fontMetrics
        separator_symbol = self.__separator_symbol
        separator_width = fm.horizontalAdvance(separator_symbol)
        N = len(self.__items)
        margins = self.__text_margins
        for i, item in enumerate(self.__items):
            arrow_symbol = separator_symbol if i < N - 1 else None
            is_last = i == N - 1
            if is_last:
                margins_ = margins
            else:
                margins_ = margins + QMargins(0, 0, separator_width, 0)
            paint_item(
                painter, item, option.palette, option.state, style, margins_,
                arrow_symbol
            )


def paint_item(
        painter: QPainter, item: Breadcrumbs.Item, palette: QPalette,
        state: QStyle.State, style: QStyle, margins: QMargins, arrow=None
) -> None:
    rect = item.rect
    text = item.text
    align = Qt.AlignVCenter | Qt.AlignLeft
    rect_text = rect.marginsRemoved(margins)
    style.drawItemText(
        painter, rect_text, align, palette, bool(state & QStyle.State_Enabled),
        text
    )
    if arrow:
        rect_arrow = QRect(rect)
        rect_arrow.setLeft(rect.right() - margins.right() - 1)
        painter.drawText(rect_arrow, Qt.AlignRight, arrow)

import enum
import sys
from typing import Optional, Iterable, Union

from AnyQt.QtCore import Qt, QEvent, Signal, QSize, QRect
from AnyQt.QtGui import (
    QTextDocument, QTextBlock, QTextLine, QPalette, QPainter, QPen,
    QPainterPath, QFocusEvent, QKeyEvent, QTextBlockFormat, QTextCursor, QImage
)
from AnyQt.QtWidgets import (
    QGraphicsTextItem, QStyleOptionGraphicsItem, QStyle, QWidget, QApplication,
    QGraphicsSceneHoverEvent, QGraphicsSceneMouseEvent, QStyleOptionButton,
    QGraphicsItem,
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
        if state & (QStyle.State_Selected | QStyle.State_HasFocus) \
                and not state & QStyle.State_Editing:
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
        if self.__styleState & QStyle.State_Selected \
                and not self.__styleState & QStyle.State_Editing:
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


class EditTriggers(enum.IntEnum):
    NoEditTriggers = 0
    CurrentChanged = 1
    DoubleClicked = 2
    SelectedClicked = 4
    EditKeyPressed = 8
    AnyKeyPressed = 16


class GraphicsTextEdit(GraphicsTextItem):
    EditTriggers = EditTriggers
    NoEditTriggers = EditTriggers.NoEditTriggers
    CurrentChanged = EditTriggers.CurrentChanged
    DoubleClicked = EditTriggers.DoubleClicked
    SelectedClicked = EditTriggers.SelectedClicked
    EditKeyPressed = EditTriggers.EditKeyPressed
    AnyKeyPressed = EditTriggers.AnyKeyPressed

    #: Signal emitted when editing operation starts (the item receives edit
    #: focus)
    editingStarted = Signal()
    #: Signal emitted when editing operation ends (the item loses edit focus)
    editingFinished = Signal()

    documentSizeChanged = Signal()

    def __init__(self, *args, **kwargs):
        self.__editTriggers = kwargs.pop(
            "editTriggers", GraphicsTextEdit.DoubleClicked
        )
        alignment = kwargs.pop("alignment", None)
        self.__returnKeyEndsEditing = kwargs.pop("returnKeyEndsEditing", False)
        super().__init__(*args, **kwargs)
        self.__editing = False
        self.__textInteractionFlags = self.textInteractionFlags()

        if sys.platform == "darwin":
            self.__editKeys = (Qt.Key_Enter, Qt.Key_Return)
        else:
            self.__editKeys = (Qt.Key_F2,)

        self.document().documentLayout().documentSizeChanged.connect(
            self.documentSizeChanged
        )
        if alignment is not None:
            self.setAlignment(alignment)

    def setAlignment(self, alignment: Qt.Alignment) -> None:
        """Set alignment for the current text block."""
        block = QTextBlockFormat()
        block.setAlignment(alignment)
        cursor = self.textCursor()
        cursor.mergeBlockFormat(block)
        self.setTextCursor(cursor)

    def alignment(self) -> Qt.Alignment:
        return self.textCursor().blockFormat().alignment()

    def selectAll(self) -> None:
        """Select all text."""
        cursor = self.textCursor()
        cursor.select(QTextCursor.Document)
        self.setTextCursor(cursor)

    def clearSelection(self) -> None:
        """Clear current selection."""
        cursor = self.textCursor()
        cursor.clearSelection()
        self.setTextCursor(cursor)

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        layout = self.document().documentLayout()
        if layout.anchorAt(event.pos()):
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        flags = self.textInteractionFlags()
        if flags & Qt.LinksAccessibleByMouse \
                and not flags & Qt.TextSelectableByMouse \
                and self.document().documentLayout().anchorAt(event.pos()):
            # QGraphicsTextItem ignores the press event without
            # Qt.TextSelectableByMouse flag set. This causes the
            # corresponding mouse release to never get to this item
            # and therefore no linkActivated/openUrl ...
            super().mousePressEvent(event)
            if not event.isAccepted():
                event.accept()
        else:
            super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        editing = self.__editing
        if self.__editTriggers & EditTriggers.EditKeyPressed \
                and not editing:
            if event.key() in self.__editKeys:
                self.__startEdit(Qt.ShortcutFocusReason)
                event.accept()
                return
        elif self.__editTriggers & EditTriggers.AnyKeyPressed \
                and not editing:
            self.__startEdit(Qt.OtherFocusReason)
            event.accept()
            return
        if editing and self.__returnKeyEndsEditing \
                and event.key() in (Qt.Key_Enter, Qt.Key_Return):
            self.__endEdit()
            event.accept()
            return
        super().keyPressEvent(event)

    def setTextInteractionFlags(
            self, flags: Union[Qt.TextInteractionFlag, Qt.TextInteractionFlags]
    ) -> None:
        super().setTextInteractionFlags(flags)
        if self.hasFocus() and flags & Qt.TextEditable and not self.__editing:
            self.__startEdit(EditTriggers.NoEditTriggers)

    def isEditing(self) -> bool:
        """Is editing currently active."""
        return self.__editing

    def edit(self) -> None:
        """Start editing"""
        if not self.__editing:
            self.__startEdit(Qt.OtherFocusReason)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseDoubleClickEvent(event)
        if self.__editTriggers & GraphicsTextEdit.DoubleClicked:
            self.__startEdit(Qt.MouseFocusReason)

    def focusInEvent(self, event: QFocusEvent)  -> None:
        super().focusInEvent(event)
        if self.textInteractionFlags() & Qt.TextEditable \
                and not self.__editing \
                and self.__editTriggers & EditTriggers.CurrentChanged:
            self.__startEdit(event.reason())

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        if self.__editing and event.reason() not in {
            Qt.ActiveWindowFocusReason,
            Qt.PopupFocusReason
        }:
            self.__endEdit()

    def paint(self, painter, option, widget=None):
        if self.__editing:
            option.state |= QStyle.State_Editing
        # Disable base QGraphicsItem selected/focused outline
        state = option.state
        option = QStyleOptionGraphicsItem(option)
        option.palette = self.palette().resolve(option.palette)
        option.state &= ~(QStyle.State_Selected | QStyle.State_HasFocus)
        super().paint(painter, option, widget)
        if state & QStyle.State_Editing:
            brect = self.boundingRect()
            width = 3.
            color = qgraphicsitem_accent_color(self, option.palette)
            color.setAlpha(230)
            pen = QPen(color, width, Qt.SolidLine)
            painter.setPen(pen)
            adjust = width / 2.
            pen.setJoinStyle(Qt.RoundJoin)
            painter.drawRect(
                brect.adjusted(adjust, adjust, -adjust, -adjust),
            )

    def __startEdit(self, focusReason=Qt.OtherFocusReason) -> None:
        if self.__editing:
            return
        self.__editing = True
        self.__textInteractionFlags = self.textInteractionFlags()
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.setStyleState(self.styleState() | QStyle.State_Editing)
        self.setFocus(focusReason)
        self.editingStarted.emit()

    def __endEdit(self) -> None:
        self.__editing = False
        self.clearSelection()
        self.setTextInteractionFlags(self.__textInteractionFlags)
        self.setStyleState(self.styleState() & ~QStyle.State_Editing)
        self.editingFinished.emit()


def qgraphicsitem_style(item: QGraphicsItem) -> QStyle:
    if item.isWidget():
        return item.style()
    parent = item.parentWidget()
    if parent is not None:
        return parent.style()
    scene = item.scene()
    if scene is not None:
        return scene.style()
    return QApplication.style()


def qmacstyle_accent_color(style: QStyle):
    option = QStyleOptionButton()
    option.state |= (QStyle.State_Active | QStyle.State_Enabled
                     | QStyle.State_Raised)
    option.features |= QStyleOptionButton.DefaultButton
    option.text = ""
    size = style.sizeFromContents(
        QStyle.CT_PushButton, option, QSize(20, 10), None
    )
    option.rect = QRect(0, 0, size.width(), size.height())
    img = QImage(
        size.width(), size.height(), QImage.Format_ARGB32_Premultiplied
    )
    img.fill(Qt.transparent)
    painter = QPainter(img)
    try:
        style.drawControl(QStyle.CE_PushButton, option, painter, None)
    finally:
        painter.end()
    color = img.pixelColor(size.width() // 2, size.height() // 2)
    return color


def qgraphicsitem_accent_color(item: 'QGraphicsItem', palette: QPalette):
    style = qgraphicsitem_style(item)
    mo = style.metaObject()
    if mo.className() == 'QMacStyle':
        return qmacstyle_accent_color(style)
    else:
        return palette.highlight().color()

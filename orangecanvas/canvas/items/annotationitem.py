from typing import Optional, Union, Any, Tuple

from AnyQt.QtWidgets import (
    QGraphicsItem, QGraphicsPathItem, QGraphicsWidget, QGraphicsTextItem,
    QGraphicsDropShadowEffect, QMenu, QAction, QActionGroup,
    QStyleOptionGraphicsItem, QWidget, QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent, QGraphicsSceneResizeEvent,
    QGraphicsSceneContextMenuEvent
)
from AnyQt.QtGui import (
    QPainterPath, QPainterPathStroker, QPolygonF, QColor, QPen, QBrush,
    QPalette, QPainter, QTextDocument, QTextCursor, QFocusEvent
)
from AnyQt.QtCore import (
    Qt, QPointF, QSizeF, QRectF, QLineF, QEvent, QMetaObject, QObject
)
from AnyQt.QtCore import (
    pyqtSignal as Signal, pyqtProperty as Property, pyqtSlot as Slot
)

from orangecanvas.utils import markup
from .graphicspathobject import GraphicsPathObject


class Annotation(QGraphicsWidget):
    """
    Base class for annotations in the canvas scheme.
    """


class GraphicsTextEdit(QGraphicsTextItem):
    """
    QGraphicsTextItem subclass defining an additional placeholderText
    property (text displayed when no text is set).

    """
    #: Signal emitted when editing operation starts (the item receives edit
    #: focus)
    editingStarted = Signal()
    #: Signal emitted when editing operation ends (the item loses edit focus)
    editingFinished = Signal()

    def __init__(self, *args, placeholderText="", **kwargs):
        # type: (Any, str, Any) -> None
        super().__init__(*args, **kwargs)
        self.setAcceptHoverEvents(True)
        self.__placeholderText = placeholderText
        self.__editing = False  # text editing in progress

    def setPlaceholderText(self, text):
        # type: (str) -> None
        """
        Set the placeholder text. This is shown when the item has no text,
        i.e when `toPlainText()` returns an empty string.

        """
        if self.__placeholderText != text:
            self.__placeholderText = text
            if not self.toPlainText():
                self.update()

    def placeholderText(self):
        # type: () -> str
        """
        Return the placeholder text.
        """
        return self.__placeholderText

    placeholderText_ = Property(str, placeholderText, setPlaceholderText,
                                doc="Placeholder text")

    def paint(self, painter, option, widget=None):
        # type: (QPainter, QStyleOptionGraphicsItem, Optional[QWidget]) -> None
        super().paint(painter, option, widget)

        # Draw placeholder text if necessary
        if not (self.toPlainText() and self.toHtml()) and \
                self.__placeholderText and \
                not (self.hasFocus() and \
                     self.textInteractionFlags() & Qt.TextEditable):
            brect = self.boundingRect()
            painter.setFont(self.font())
            metrics = painter.fontMetrics()
            text = metrics.elidedText(self.__placeholderText, Qt.ElideRight,
                                      brect.width())
            color = self.defaultTextColor()
            color.setAlpha(min(color.alpha(), 150))
            painter.setPen(QPen(color))
            painter.drawText(brect, Qt.AlignTop | Qt.AlignLeft, text)

    def hoverMoveEvent(self, event):
        # type: (QGraphicsSceneHoverEvent) -> None
        layout = self.document().documentLayout()
        if layout.anchorAt(event.pos()):
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.unsetCursor()
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> None
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

    def setTextInteractionFlags(self, flags):
        # type: (Union[Qt.TextInteractionFlag, Qt.TextInteractionFlags]) -> None
        super().setTextInteractionFlags(flags)
        if self.hasFocus() and flags & Qt.TextEditable and not self.__editing:
            self.__editing = True
            self.editingStarted.emit()

    def focusInEvent(self, event):
        # type: (QFocusEvent) -> None
        super().focusInEvent(event)
        if self.textInteractionFlags() & Qt.TextEditable and \
                not self.__editing:
            self.__editing = True
            self.editingStarted.emit()

    def focusOutEvent(self, event):
        # type: (QFocusEvent) -> None
        super().focusOutEvent(event)
        if self.__editing and \
                event.reason() not in {Qt.ActiveWindowFocusReason,
                                       Qt.PopupFocusReason}:
            self.__editing = False
            self.editingFinished.emit()


class TextAnnotation(Annotation):
    """
    Text annotation item for the canvas scheme.

    Text interaction (if enabled) is started by double clicking the item.
    """
    #: Emitted when the editing is finished (i.e. the item loses edit focus).
    editingFinished = Signal()

    #: Emitted when the text content changes on user interaction.
    textEdited = Signal()

    #: Emitted when the text annotation's contents change
    #: (`content` or `contentType` changed)
    contentChanged = Signal()

    def __init__(self, parent=None, **kwargs):
        # type: (Optional[QGraphicsItem], Any) -> None
        super().__init__(None, **kwargs)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        self.setFocusPolicy(Qt.ClickFocus)

        self.__contentType = "text/plain"
        self.__content = ""

        self.__textMargins = (2, 2, 2, 2)
        self.__textInteractionFlags = Qt.NoTextInteraction
        self.__defaultInteractionFlags = Qt.TextInteractionFlags(
            Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard
        )
        rect = self.geometry().translated(-self.pos())
        self.__framePen = QPen(Qt.NoPen)
        self.__framePathItem = QGraphicsPathItem(self)
        self.__framePathItem.setPen(self.__framePen)

        self.__textItem = GraphicsTextEdit(self)
        self.__textItem.setOpenExternalLinks(True)
        self.__textItem.setPlaceholderText(self.tr("Enter text here"))
        self.__textItem.setPos(2, 2)
        self.__textItem.setTextWidth(rect.width() - 4)
        self.__textItem.setTabChangesFocus(True)
        self.__textItem.setTextInteractionFlags(self.__defaultInteractionFlags)
        self.__textItem.setFont(self.font())
        self.__textItem.editingFinished.connect(self.__textEditingFinished)
        self.__textItem.setDefaultTextColor(
            self.palette().color(QPalette.Text)
        )
        if self.__textItem.scene() is not None:
            self.__textItem.installSceneEventFilter(self)
        layout = self.__textItem.document().documentLayout()
        layout.documentSizeChanged.connect(self.__onDocumentSizeChanged)

        self.__updateFrame()
        # set parent item at the end in order to ensure
        # QGraphicsItem.ItemSceneHasChanged is delivered after initialization
        if parent is not None:
            self.setParentItem(parent)

    def itemChange(self, change, value):
        # type: (QGraphicsItem.GraphicsItemChange, Any) -> Any
        if change == QGraphicsItem.ItemSceneHasChanged:
            if self.__textItem.scene() is not None:
                self.__textItem.installSceneEventFilter(self)
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.__updateFrameStyle()
        return super().itemChange(change, value)

    def adjustSize(self):
        # type: () -> None
        """Resize to a reasonable size.
        """
        self.__textItem.setTextWidth(-1)
        self.__textItem.adjustSize()
        size = self.__textItem.boundingRect().size()
        left, top, right, bottom = self.textMargins()
        geom = QRectF(self.pos(), size + QSizeF(left + right, top + bottom))
        self.setGeometry(geom)

    def setFramePen(self, pen):
        # type: (QPen) -> None
        """Set the frame pen. By default Qt.NoPen is used (i.e. the frame
        is not shown).
        """
        if pen != self.__framePen:
            self.__framePen = QPen(pen)
            self.__updateFrameStyle()

    def framePen(self):
        # type: () -> QPen
        """Return the frame pen.
        """
        return QPen(self.__framePen)

    def setFrameBrush(self, brush):
        # type: (QBrush) -> None
        """Set the frame brush.
        """
        self.__framePathItem.setBrush(brush)

    def frameBrush(self):
        # type: () -> QBrush
        """Return the frame brush.
        """
        return self.__framePathItem.brush()

    def __updateFrameStyle(self):
        # type: () -> None
        if self.isSelected():
            pen = QPen(QColor(96, 158, 215), 1.25, Qt.DashDotLine)
        else:
            pen = self.__framePen

        self.__framePathItem.setPen(pen)

    def contentType(self):
        # type: () -> str
        return self.__contentType

    def setContent(self, content, contentType="text/plain"):
        # type: (str, str) -> None
        if self.__content != content or self.__contentType != contentType:
            self.__contentType = contentType
            self.__content = content
            self.__updateRenderedContent()
            self.contentChanged.emit()

    def content(self):
        # type: () -> str
        return self.__content

    def setPlainText(self, text):
        # type: (str) -> None
        """Set the annotation text as plain text.
        """
        self.setContent(text, "text/plain")

    def toPlainText(self):
        # type: () -> str
        return self.__textItem.toPlainText()

    def setHtml(self, text):
        # type: (str) -> None
        """Set the annotation text as html.
        """
        self.setContent(text, "text/html")

    def toHtml(self):
        # type: () -> str
        return self.__textItem.toHtml()

    def setDefaultTextColor(self, color):
        # type: (QColor) -> None
        """Set the default text color.
        """
        self.__textItem.setDefaultTextColor(color)

    def defaultTextColor(self):
        # type: () -> QColor
        return self.__textItem.defaultTextColor()

    def setTextMargins(self, left, top, right, bottom):
        # type: (int, int, int, int) -> None
        """Set the text margins.
        """
        margins = (left, top, right, bottom)
        if self.__textMargins != margins:
            self.__textMargins = margins
            self.__textItem.setPos(left, top)
            self.__textItem.setTextWidth(
                max(self.geometry().width() - left - right, 0)
            )

    def textMargins(self):
        # type: () -> Tuple[int, int, int, int]
        """Return the text margins.
        """
        return self.__textMargins

    def document(self):
        # type: () -> QTextDocument
        """Return the QTextDocument instance used internally.
        """
        return self.__textItem.document()

    def setTextCursor(self, cursor):
        # type: (QTextCursor) -> None
        self.__textItem.setTextCursor(cursor)

    def textCursor(self):
        # type: () -> QTextCursor
        return self.__textItem.textCursor()

    def setTextInteractionFlags(self, flags):
        # type: (Union[Qt.TextInteractionFlags, Qt.TextInteractionFlag]) -> None
        self.__textInteractionFlags = Qt.TextInteractionFlags(flags)

    def textInteractionFlags(self):
        # type: () -> Qt.TextInteractionFlags
        return Qt.TextInteractionFlags(self.__textInteractionFlags)

    def setDefaultStyleSheet(self, stylesheet):
        # type: (str) -> None
        self.document().setDefaultStyleSheet(stylesheet)

    def mouseDoubleClickEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> None
        super().mouseDoubleClickEvent(event)

        if event.buttons() == Qt.LeftButton and \
                self.__textInteractionFlags & Qt.TextEditable:
            self.startEdit()

    def startEdit(self):
        # type: () -> None
        """Start the annotation text edit process.
        """
        self.__textItem.setPlainText(self.__content)
        self.__textItem.setTextInteractionFlags(self.__textInteractionFlags)
        self.__textItem.setFocus(Qt.MouseFocusReason)
        self.__textItem.document().contentsChanged.connect(
            self.textEdited
        )

    def endEdit(self):
        # type: () -> None
        """End the annotation edit.
        """
        content = self.__textItem.toPlainText()

        self.__textItem.setTextInteractionFlags(self.__defaultInteractionFlags)
        self.__textItem.document().contentsChanged.disconnect(
            self.textEdited
        )
        cursor = self.__textItem.textCursor()
        cursor.clearSelection()
        self.__textItem.setTextCursor(cursor)
        self.__content = content

        self.editingFinished.emit()
        # Cannot change the textItem's html immediately, this method is
        # invoked from it.
        # TODO: Separate the editor from the view.
        QMetaObject.invokeMethod(
            self, "__updateRenderedContent", Qt.QueuedConnection)

    def __onDocumentSizeChanged(self, size):
        # type: (QSizeF) -> None
        # The size of the text document has changed. Expand the text
        # control rect's height if the text no longer fits inside.
        rect = self.geometry()
        _, top, _, bottom = self.textMargins()
        if rect.height() < (size.height() + bottom + top):
            rect.setHeight(size.height() + bottom + top)
            self.setGeometry(rect)

    def __updateFrame(self):
        # type: () -> None
        rect = self.geometry()
        rect.moveTo(0, 0)
        path = QPainterPath()
        path.addRect(rect)
        self.__framePathItem.setPath(path)

    def resizeEvent(self, event):
        # type: (QGraphicsSceneResizeEvent) -> None
        width = event.newSize().width()
        left, _, right, _ = self.textMargins()
        self.__textItem.setTextWidth(max(width - left - right, 0))
        self.__updateFrame()
        super().resizeEvent(event)

    def __textEditingFinished(self):
        # type: () -> None
        self.endEdit()

    def sceneEventFilter(self, obj, event):
        # type: (QGraphicsItem, QEvent) -> bool
        if obj is self.__textItem and \
                not (self.__textItem.hasFocus() and
                     self.__textItem.textInteractionFlags() & Qt.TextEditable) and \
                event.type() in {QEvent.GraphicsSceneContextMenu} and \
                event.modifiers() & Qt.AltModifier:
            # Handle Alt + context menu events here
            self.contextMenuEvent(event)
            event.accept()
            return True
        return super().sceneEventFilter(obj, event)

    def changeEvent(self, event):
        # type: (QEvent) -> None
        if event.type() == QEvent.FontChange:
            self.__textItem.setFont(self.font())
        elif event.type() == QEvent.PaletteChange:
            self.__textItem.setDefaultTextColor(
                self.palette().color(QPalette.Text)
            )
        super().changeEvent(event)

    @Slot()
    def __updateRenderedContent(self):
        # type: () -> None
        self.__textItem.setHtml(
            markup.render_as_rich_text(self.__content, self.__contentType)
        )

    def contextMenuEvent(self, event):
        # type: (QGraphicsSceneContextMenuEvent) -> None
        if event.modifiers() & Qt.AltModifier:
            menu = QMenu(event.widget())
            menu.setAttribute(Qt.WA_DeleteOnClose)
            formatmenu = menu.addMenu("Render as")
            group = QActionGroup(self, exclusive=True)

            def makeaction(text, parent, data=None, **kwargs):
                # type: (str, QObject, Any, Any) -> QAction
                action = QAction(text, parent, **kwargs)
                if data is not None:
                    action.setData(data)
                return action

            formatactions = [
                makeaction("Plain Text", group, checkable=True,
                           toolTip=self.tr("Render contents as plain text"),
                           data="text/plain"),
                makeaction("HTML", group, checkable=True,
                           toolTip=self.tr("Render contents as HTML"),
                           data="text/html"),
                makeaction("RST", group, checkable=True,
                           toolTip=self.tr("Render contents as RST "
                                           "(reStructuredText)"),
                           data="text/rst"),
                makeaction("Markdown", group, checkable=True,
                           toolTip=self.tr("Render contents as Markdown"),
                           data="text/markdown")
            ]
            for action in formatactions:
                action.setChecked(action.data() == self.__contentType.lower())
                formatmenu.addAction(action)

            def ontriggered(action):
                # type: (QAction) -> None
                mimetype = action.data()
                content = self.content()
                self.setContent(content, mimetype)
                self.editingFinished.emit()

            menu.triggered.connect(ontriggered)
            menu.popup(event.screenPos())
            event.accept()
        else:
            event.ignore()


class ArrowItem(GraphicsPathObject):

    #: Arrow Style
    Plain, Concave = 1, 2

    def __init__(self, parent=None, line=None, lineWidth=4., **kwargs):
        # type: (Optional[QGraphicsItem], Optional[QLineF], float, Any) -> None
        super().__init__(parent, **kwargs)

        if line is None:
            line = QLineF(0, 0, 10, 0)

        self.__line = line

        self.__lineWidth = lineWidth

        self.__arrowStyle = ArrowItem.Plain

        self.__updateArrowPath()

    def setLine(self, line):
        # type: (QLineF) -> None
        """Set the baseline of the arrow (:class:`QLineF`).
        """
        if self.__line != line:
            self.__line = QLineF(line)
            self.__updateArrowPath()

    def line(self):
        # type: () -> QLineF
        """Return the baseline of the arrow.
        """
        return QLineF(self.__line)

    def setLineWidth(self, lineWidth):
        # type: (float) -> None
        """Set the width of the arrow.
        """
        if self.__lineWidth != lineWidth:
            self.__lineWidth = lineWidth
            self.__updateArrowPath()

    def lineWidth(self):
        # type: () -> float
        """Return the width of the arrow.
        """
        return self.__lineWidth

    def setArrowStyle(self, style):
        # type: (int) -> None
        """Set the arrow style (`ArrowItem.Plain` or `ArrowItem.Concave`)
        """
        if self.__arrowStyle != style:
            self.__arrowStyle = style
            self.__updateArrowPath()

    def arrowStyle(self):
        # type: () -> int
        """Return the arrow style
        """
        return self.__arrowStyle

    def __updateArrowPath(self):
        # type: () -> None
        if self.__arrowStyle == ArrowItem.Plain:
            path = arrow_path_plain(self.__line, self.__lineWidth)
        else:
            path = arrow_path_concave(self.__line, self.__lineWidth)
        self.setPath(path)


def arrow_path_plain(line, width):
    # type: (QLineF, float) -> QPainterPath
    """
    Return an :class:`QPainterPath` of a plain looking arrow.
    """
    path = QPainterPath()
    p1, p2 = line.p1(), line.p2()

    if p1 == p2:
        return path

    baseline = QLineF(line)
    # Require some minimum length.
    baseline.setLength(max(line.length() - width * 3, width * 3))
    path.moveTo(baseline.p1())
    path.lineTo(baseline.p2())

    stroker = QPainterPathStroker()
    stroker.setWidth(width)
    path = stroker.createStroke(path)

    arrow_head_len = width * 4
    arrow_head_angle = 50
    line_angle = line.angle() - 180

    angle_1 = line_angle - arrow_head_angle / 2.0
    angle_2 = line_angle + arrow_head_angle / 2.0

    points = [p2,
              p2 + QLineF.fromPolar(arrow_head_len, angle_1).p2(),
              p2 + QLineF.fromPolar(arrow_head_len, angle_2).p2(),
              p2]

    poly = QPolygonF(points)
    path_head = QPainterPath()
    path_head.addPolygon(poly)
    path = path.united(path_head)
    return path


def arrow_path_concave(line, width):
    # type: (QLineF, float) -> QPainterPath
    """
    Return a :class:`QPainterPath` of a pretty looking arrow.
    """
    path = QPainterPath()
    p1, p2 = line.p1(), line.p2()

    if p1 == p2:
        return path

    baseline = QLineF(line)
    # Require some minimum length.
    baseline.setLength(max(line.length() - width * 3, width * 3))

    start, end = baseline.p1(), baseline.p2()
    mid = (start + end) / 2.0
    normal = QLineF.fromPolar(1.0, baseline.angle() + 90).p2()

    path.moveTo(start)
    path.lineTo(start + (normal * width / 4.0))

    path.quadTo(mid + (normal * width / 4.0),
                end + (normal * width / 1.5))

    path.lineTo(end - (normal * width / 1.5))
    path.quadTo(mid - (normal * width / 4.0),
                start - (normal * width / 4.0))
    path.closeSubpath()

    arrow_head_len = width * 4
    arrow_head_angle = 50
    line_angle = line.angle() - 180

    angle_1 = line_angle - arrow_head_angle / 2.0
    angle_2 = line_angle + arrow_head_angle / 2.0

    points = [p2,
              p2 + QLineF.fromPolar(arrow_head_len, angle_1).p2(),
              baseline.p2(),
              p2 + QLineF.fromPolar(arrow_head_len, angle_2).p2(),
              p2]

    poly = QPolygonF(points)
    path_head = QPainterPath()
    path_head.addPolygon(poly)
    path = path.united(path_head)
    return path


class ArrowAnnotation(Annotation):
    def __init__(self, parent=None, line=None, **kwargs):
        # type: (Optional[QGraphicsItem], Optional[QLineF], Any) -> None
        super().__init__(parent, **kwargs)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        self.setFocusPolicy(Qt.ClickFocus)

        if line is None:
            line = QLineF(0, 0, 20, 0)

        self.__line = QLineF(line)
        self.__color = QColor(Qt.red)
        # An item with the same shape as this arrow, stacked behind this
        # item as a source for QGraphicsDropShadowEffect. Cannot attach
        # the effect to this item directly as QGraphicsEffect makes the item
        # non devicePixelRatio aware.
        self.__arrowShadowBase = ArrowItem(self, line=line)
        self.__arrowShadowBase.setPen(Qt.NoPen)  # no pen -> slightly thinner
        self.__arrowShadowBase.setBrush(QBrush(self.__color))
        self.__arrowShadowBase.setArrowStyle(ArrowItem.Concave)
        self.__arrowShadowBase.setLineWidth(5)

        self.__shadow = QGraphicsDropShadowEffect(
            blurRadius=5, offset=QPointF(1.0, 2.0),
        )

        self.__arrowShadowBase.setGraphicsEffect(self.__shadow)
        self.__shadow.setEnabled(True)

        # The 'real' shape item
        self.__arrowItem = ArrowItem(self, line=line)
        self.__arrowItem.setBrush(self.__color)
        self.__arrowItem.setPen(QPen(self.__color))
        self.__arrowItem.setArrowStyle(ArrowItem.Concave)
        self.__arrowItem.setLineWidth(5)

        self.__autoAdjustGeometry = True

    def setAutoAdjustGeometry(self, autoAdjust):
        # type: (bool) -> None
        """
        If set to `True` then the geometry will be adjusted whenever
        the arrow is changed with `setLine`. Otherwise the geometry
        of the item is only updated so the `line` lies within the
        `geometry()` rect (i.e. it only grows). True by default
        """
        self.__autoAdjustGeometry = autoAdjust
        if autoAdjust:
            self.adjustGeometry()

    def autoAdjustGeometry(self):
        # type: () -> bool
        """
        Should the geometry of the item be adjusted automatically when
        `setLine` is called.
        """
        return self.__autoAdjustGeometry

    def setLine(self, line):
        # type: (QLineF) -> None
        """
        Set the arrow base line (a `QLineF` in object coordinates).
        """
        if self.__line != line:
            self.__line = QLineF(line)

            # local item coordinate system
            geom = self.geometry().translated(-self.pos())

            if geom.isNull() and not line.isNull():
                geom = QRectF(0, 0, 1, 1)

            arrow_shape = arrow_path_concave(line, self.lineWidth())
            arrow_rect = arrow_shape.boundingRect()

            if not (geom.contains(arrow_rect)):
                geom = geom.united(arrow_rect)

            if self.__autoAdjustGeometry:
                # Shrink the geometry if required.
                geom = geom.intersected(arrow_rect)

            # topLeft can move changing the local coordinates.
            diff = geom.topLeft()
            line = QLineF(line.p1() - diff, line.p2() - diff)
            self.__arrowItem.setLine(line)
            self.__arrowShadowBase.setLine(line)
            self.__line = line

            # parent item coordinate system
            geom.translate(self.pos())
            self.setGeometry(geom)

    def line(self):
        # type: () -> QLineF
        """
        Return the arrow base line (`QLineF` in object coordinates).
        """
        return QLineF(self.__line)

    def setColor(self, color):
        # type: (QColor) -> None
        """
        Set arrow brush color.
        """
        if self.__color != color:
            self.__color = QColor(color)
            self.__updateStyleState()

    def color(self):
        # type: () -> QColor
        """
        Return the arrow brush color.
        """
        return QColor(self.__color)

    def setLineWidth(self, lineWidth):
        # type: (float) -> None
        """
        Set the arrow line width.
        """
        self.__arrowItem.setLineWidth(lineWidth)
        self.__arrowShadowBase.setLineWidth(lineWidth)

    def lineWidth(self):
        # type: () -> float
        """
        Return the arrow line width.
        """
        return self.__arrowItem.lineWidth()

    def adjustGeometry(self):
        # type: () -> None
        """
        Adjust the widget geometry to exactly fit the arrow inside
        while preserving the arrow path scene geometry.

        """
        # local system coordinate
        geom = self.geometry().translated(-self.pos())
        line = self.__line

        arrow_rect = self.__arrowItem.shape().boundingRect()

        if geom.isNull() and not line.isNull():
            geom = QRectF(0, 0, 1, 1)

        if not (geom.contains(arrow_rect)):
            geom = geom.united(arrow_rect)

        geom = geom.intersected(arrow_rect)
        diff = geom.topLeft()
        line = QLineF(line.p1() - diff, line.p2() - diff)
        geom.translate(self.pos())
        self.setGeometry(geom)
        self.setLine(line)

    def shape(self):
        # type: () -> QPainterPath
        arrow_shape = self.__arrowItem.shape()
        return self.mapFromItem(self.__arrowItem, arrow_shape)

    def itemChange(self, change, value):
        # type: (QGraphicsItem.GraphicsItemChange, Any) -> Any
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.__updateStyleState()

        return super().itemChange(change, value)

    def __updateStyleState(self):
        # type: () -> None
        """
        Update the arrows' brush, pen, ... based on it's state
        """
        if self.isSelected():
            color = self.__color.darker(150)
            pen = QPen(QColor(96, 158, 215), Qt.DashDotLine)
            pen.setWidthF(1.25)
            pen.setCosmetic(True)
            shadow = pen.color().darker(150)
        else:
            color = self.__color
            pen = QPen(color)
            shadow = QColor(63, 63, 63, 180)

        self.__arrowShadowBase.setBrush(color)
        self.__shadow.setColor(shadow)

        self.__arrowItem.setBrush(color)
        self.__arrowItem.setPen(pen)

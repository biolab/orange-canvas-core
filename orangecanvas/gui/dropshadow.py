"""
=================
Drop Shadow Frame
=================

A widget providing a drop shadow (gaussian blur effect) around another
widget.

"""

from AnyQt.QtWidgets import (
    QWidget, QGraphicsScene, QGraphicsRectItem, QGraphicsDropShadowEffect,
    QStyleOption, QAbstractScrollArea, QToolBar
)
from AnyQt.QtGui import QPainter, QPixmap, QColor, QPen, QPalette, QRegion
from AnyQt.QtCore import (
    Qt, QPoint, QPointF, QRect, QRectF, QSize, QSizeF, QEvent
)
from AnyQt.QtCore import pyqtProperty as Property


def render_drop_shadow_frame(pixmap, shadow_rect, shadow_color,
                             offset, radius, rect_fill_color):
    pixmap.fill(Qt.transparent)
    scene = QGraphicsScene()
    rect = QGraphicsRectItem(shadow_rect)
    rect.setBrush(QColor(rect_fill_color))
    rect.setPen(QPen(Qt.NoPen))
    scene.addItem(rect)
    effect = QGraphicsDropShadowEffect(color=shadow_color,
                                       blurRadius=radius,
                                       offset=offset)

    rect.setGraphicsEffect(effect)
    scene.setSceneRect(QRectF(QPointF(0, 0), QSizeF(pixmap.size())))
    painter = QPainter(pixmap)
    scene.render(painter)
    painter.end()
    scene.clear()
    scene.deleteLater()
    return pixmap


class DropShadowFrame(QWidget):
    """
    A widget drawing a drop shadow effect around the geometry of
    another widget (works similar to :class:`QFocusFrame`).

    Parameters
    ----------
    parent : :class:`QObject`
        Parent object.
    color : :class:`QColor`
        The color of the drop shadow.
    radius : float
        Shadow radius.

    """
    def __init__(self, parent=None, color=QColor(), radius=5,
                 **kwargs):
        super().__init__(parent, **kwargs)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoChildEventsForParent, True)
        self.setFocusPolicy(Qt.NoFocus)

        self.__color = QColor(color)
        self.__radius = radius
        self.__offset = QPoint(0, 0)

        self.__widget = None
        self.__widgetParent = None
        self.__updatePixmap()

    def setColor(self, color):
        """
        Set the color of the shadow.
        """
        if not isinstance(color, QColor):
            color = QColor(color)

        if self.__color != color:
            self.__color = QColor(color)
            self.__updatePixmap()

    def color(self):
        """
        Return the color of the drop shadow.

        By default this is a color from the `palette` (for
        `self.foregroundRole()`)
        """
        if self.__color.isValid():
            return QColor(self.__color)
        else:
            return self.palette().color(self.foregroundRole())

    color_ = Property(QColor, fget=color, fset=setColor, designable=True,
                      doc="Drop shadow color")

    def setRadius(self, radius):
        """
        Set the drop shadow's blur radius.
        """
        if self.__radius != radius:
            self.__radius = radius
            self.__updateGeometry()
            self.__updatePixmap()

    def radius(self):
        """
        Return the shadow blur radius.
        """
        return self.__radius

    radius_ = Property(int, fget=radius, fset=setRadius, designable=True,
                       doc="Drop shadow blur radius.")

    def setOffset(self, offset):
        if self.__offset != QPoint(offset):
            self.__offset = QPoint(offset)
            self.__updateGeometry()
            self.__updatePixmap()

    def offset(self):
        return QPoint(self.__offset)

    offset_ = Property(QPoint, fget=offset, fset=setOffset, designable=True,
                       doc="Drop shadow offset.")

    def setWidget(self, widget):
        """
        Set the widget around which to show the shadow.
        """
        if self.__widget:
            self.__widget.removeEventFilter(self)

        self.__widget = widget

        if self.__widget:
            self.__widget.installEventFilter(self)
            # Find the parent for the frame
            # This is the top level window a toolbar or a viewport
            # of a scroll area
            parent = widget.parentWidget()
            while not (isinstance(parent, (QAbstractScrollArea, QToolBar)) or \
                       parent.isWindow()):
                parent = parent.parentWidget()

            if isinstance(parent, QAbstractScrollArea):
                parent = parent.viewport()

            self.__widgetParent = parent
            self.setParent(parent)
            self.stackUnder(widget)
            self.__updateGeometry()
            self.setVisible(widget.isVisible())

    def widget(self):
        """
        Return the widget that was set by `setWidget`.
        """
        return self.__widget

    def paintEvent(self, event):
        # TODO: Use QPainter.drawPixmapFragments on Qt 4.7
        opt = QStyleOption()
        opt.initFrom(self)
        radius = self.radius_
        offset = self.__offset

        pixmap = self.__shadowPixmap
        pixr = pixmap.devicePixelRatio()
        assert pixr == self.devicePixelRatio()
        shadow_rect = QRectF(opt.rect)
        widget_rect = QRectF(self.widget().geometry())
        widget_rect.moveTo(radius - offset.x(), radius - offset.y())

        left = top = right = bottom = radius * pixr
        pixmap_rect = QRectF(QPointF(0, 0), QSizeF(pixmap.size()))

        # Shadow casting rectangle in the source pixmap.
        pixmap_shadow_rect = pixmap_rect.adjusted(left, top, -right, -bottom)
        pixmap_shadow_rect.translate(-offset.x() * pixr, -offset.y() * pixr)
        source_rects = self.__shadowPixmapFragments(pixmap_rect,
                                                    pixmap_shadow_rect)
        target_rects = self.__shadowPixmapFragments(shadow_rect, widget_rect)

        painter = QPainter(self)
        for source, target in zip(source_rects, target_rects):
            painter.drawPixmap(target, pixmap, source)
        painter.end()

    def eventFilter(self, obj, event):
        etype = event.type()
        if etype == QEvent.Move or etype == QEvent.Resize:
            self.__updateGeometry()
        elif etype == QEvent.Show:
            self.__updateGeometry()
            self.show()
        elif etype == QEvent.Hide:
            self.hide()
        return super().eventFilter(obj, event)

    def __updateGeometry(self):
        """
        Update the shadow geometry to fit the widget's changed
        geometry.

        """
        widget = self.__widget
        parent = self.__widgetParent
        radius = self.radius_
        offset = self.__offset
        pos = widget.pos()
        if parent != widget.parentWidget():
            pos = widget.parentWidget().mapTo(parent, pos)

        geom = QRect(pos, widget.size())
        geom = geom.adjusted(-radius, -radius, radius, radius)
        geom = geom.translated(offset)
        if geom != self.geometry():
            self.setGeometry(geom)

        # Set the widget mask (punch a hole through to the `widget` instance.
        rect = self.rect()
        mask = QRegion(rect)

        rect = rect.adjusted(radius, radius, -radius, -radius)
        rect = rect.translated(-offset)
        transparent = QRegion(rect)
        mask = mask.subtracted(transparent)
        self.setMask(mask)

    def __updatePixmap(self):
        """
        Update the cached shadow pixmap.
        """
        offset = self.__offset
        pixr = self.devicePixelRatio()
        rect_size = QSize(50 * pixr, 50 * pixr)
        left = top = right = bottom = self.radius_ * pixr
        # Size of the pixmap.
        pixmap_size = QSize(rect_size.width() + left + right,
                            rect_size.height() + top + bottom)
        shadow_rect = QRect(QPoint(left, top) - offset *pixr, rect_size)
        pixmap = QPixmap(pixmap_size)
        pixmap.fill(Qt.transparent)
        rect_fill_color = self.palette().color(QPalette.Window)

        pixmap = render_drop_shadow_frame(
            pixmap,
            QRectF(shadow_rect),
            shadow_color=self.color_,
            offset=offset * pixr,
            radius=self.radius_ * pixr,
            rect_fill_color=rect_fill_color
        )
        pixmap.setDevicePixelRatio(pixr)
        self.__shadowPixmap = pixmap
        self.update()

    def __shadowPixmapFragments(self, pixmap_rect, shadow_rect):
        """
        Return a list of 8 QRectF fragments for drawing a shadow.
        """
        s_left, s_top, s_right, s_bottom = \
            shadow_rect.left(), shadow_rect.top(), \
            shadow_rect.right(), shadow_rect.bottom()
        s_width, s_height = shadow_rect.width(), shadow_rect.height()
        p_width, p_height = pixmap_rect.width(), pixmap_rect.height()

        top_left = QRectF(0.0, 0.0, s_left, s_top)
        top = QRectF(s_left, 0.0, s_width, s_top)
        top_right = QRectF(s_right, 0.0, p_width - s_width, s_top)
        right = QRectF(s_right, s_top, p_width - s_right, s_height)
        right_bottom = QRectF(shadow_rect.bottomRight(),
                              pixmap_rect.bottomRight())
        bottom = QRectF(shadow_rect.bottomLeft(),
                        pixmap_rect.bottomRight() - \
                        QPointF(p_width - s_right, 0.0))
        bottom_left = QRectF(shadow_rect.bottomLeft() - QPointF(s_left, 0.0),
                             pixmap_rect.bottomLeft() + QPointF(s_left, 0.0))
        left = QRectF(pixmap_rect.topLeft() + QPointF(0.0, s_top),
                      shadow_rect.bottomLeft())
        return [top_left, top, top_right, right, right_bottom,
                bottom, bottom_left, left]

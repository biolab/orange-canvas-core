"""
A custom toolbar with linear uniform size layout.

"""
from typing import List

from AnyQt.QtCore import Qt, QSize, QEvent, QRect
from AnyQt.QtGui import QResizeEvent, QActionEvent
from AnyQt.QtWidgets import QToolBar, QWidget


class DynamicResizeToolBar(QToolBar):
    """
    A :class:`QToolBar` subclass that dynamically resizes its tool buttons
    to fit available space (this is done by setting fixed size on the
    button instances).

    .. note:: the class does not support `QWidgetAction`, separators, etc.

    """
    def resizeEvent(self, event):
        # type: (QResizeEvent) -> None
        super().resizeEvent(event)
        size = event.size()
        self.__layout(size)

    def actionEvent(self, event):
        # type: (QActionEvent) -> None
        super().actionEvent(event)
        if event.type() == QEvent.ActionAdded or \
                event.type() == QEvent.ActionRemoved:
            self.__layout(self.size())

    def sizeHint(self):
        # type: () -> QSize
        hint = super().sizeHint()
        width, height = hint.width(), hint.height()
        dx1, dy1, dw1, dh1 = self.getContentsMargins()
        dx2, dy2, dw2, dh2 = self.layout().getContentsMargins()
        dx, dy = dx1 + dx2, dy1 + dy2
        dw, dh = dw1 + dw2, dh1 + dh2

        count = len(self.actions())
        spacing = self.layout().spacing()
        space_spacing = max(count - 1, 0) * spacing

        if self.orientation() == Qt.Horizontal:
            width = int(height * 1.618) * count + space_spacing + dw + dx
        else:
            height = int(width * 1.618) * count + space_spacing + dh + dy
        return QSize(width, height)

    def __layout(self, size):
        # type: (QSize) -> None
        """Layout the buttons to fit inside size.
        """
        mygeom = self.geometry()
        mygeom.setSize(size)

        # Adjust for margins (both the widgets and the layouts.
        dx, dy, dw, dh = self.getContentsMargins()
        mygeom.adjust(dx, dy, -dw, -dh)

        dx, dy, dw, dh = self.layout().getContentsMargins()
        mygeom.adjust(dx, dy, -dw, -dh)

        actions = self.actions()
        widgets_it = map(self.widgetForAction, actions)

        orientation = self.orientation()
        if orientation == Qt.Horizontal:
            widgets = sorted(widgets_it, key=lambda w: w.pos().x())
        else:
            widgets = sorted(widgets_it, key=lambda w: w.pos().y())

        spacing = self.layout().spacing()
        uniform_layout_helper(widgets, mygeom, orientation,
                              spacing=spacing)


def uniform_layout_helper(items, contents_rect, expanding, spacing):
    # type: (List[QWidget], QRect, Qt.Orientation, int) -> None
    """Set fixed sizes on 'items' so they can be lay out in
    contents rect anf fil the whole space.

    """
    if len(items) == 0:
        return

    spacing_space = (len(items) - 1) * spacing

    if expanding == Qt.Horizontal:
        def setter(w, s):  # type: (QWidget, int) -> None
            w.setFixedWidth(max(s, 0))
        space = contents_rect.width() - spacing_space
    else:
        def setter(w, s):  # type: (QWidget, int) -> None
            w.setFixedHeight(max(s, 0))
        space = contents_rect.height() - spacing_space

    base_size = space // len(items)
    remainder = space % len(items)

    for i, item in enumerate(items):
        item_size = base_size + (1 if i < remainder else 0)
        setter(item, item_size)

"""
=======================
Collapsible Dock Widget
=======================

A dock widget that can be a collapsed/expanded.

"""
from typing import Optional, Any

from AnyQt.QtWidgets import (
    QDockWidget, QAbstractButton, QSizePolicy, QStyle, QWidget, QWIDGETSIZE_MAX
)
from AnyQt.QtGui import QIcon, QTransform
from AnyQt.QtCore import Qt, QEvent, QObject
from AnyQt.QtCore import pyqtProperty as Property, pyqtSignal as Signal

from .stackedwidget import AnimatedStackedWidget


class CollapsibleDockWidget(QDockWidget):
    """
    This :class:`QDockWidget` subclass overrides the `close` header
    button to instead collapse to a smaller size. The contents to show
    when in each state can be set using the :func:`setExpandedWidget`
    and :func:`setCollapsedWidget`.

    Note
    ----
    Do not use the base class :func:`QDockWidget.setWidget` method to
    set the dock contents. Use :func:`setExpandedWidget` and
    :func:`setCollapsedWidget` instead.
    """

    #: Emitted when the dock widget's expanded state changes.
    expandedChanged = Signal(bool)

    def __init__(self, *args, **kwargs):
        # type: (Any, Any) -> None
        super().__init__(*args, **kwargs)

        self.__expandedWidget = None   # type: Optional[QWidget]
        self.__collapsedWidget = None  # type: Optional[QWidget]
        self.__expanded = True

        self.__trueMinimumWidth = -1

        self.setFeatures(QDockWidget.DockWidgetClosable |
                         QDockWidget.DockWidgetMovable)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

        self.dockLocationChanged.connect(self.__onDockLocationChanged)

        # Use the toolbar horizontal extension button icon as the default
        # for the expand/collapse button
        icon = self.style().standardIcon(
            QStyle.SP_ToolBarHorizontalExtensionButton)

        # Mirror the icon
        transform = QTransform()
        transform = transform.scale(-1.0, 1.0)
        icon_rev = QIcon()
        for s in (8, 12, 14, 16, 18, 24, 32, 48, 64):
            pm = icon.pixmap(s, s)
            icon_rev.addPixmap(pm.transformed(transform))

        self.__iconRight = QIcon(icon)
        self.__iconLeft = QIcon(icon_rev)
        # Find the close button an install an event filter or close event
        close = self.findChild(QAbstractButton,
                               name="qt_dockwidget_closebutton")
        assert close is not None
        close.installEventFilter(self)
        self.__closeButton = close

        self.__stack = AnimatedStackedWidget()

        self.__stack.setSizePolicy(QSizePolicy.Fixed,
                                   QSizePolicy.Expanding)
        super().setWidget(self.__stack)

        self.__closeButton.setIcon(self.__iconLeft)

    def setExpanded(self, state):
        # type: (bool) -> None
        """
        Set the widgets `expanded` state.
        """
        if self.__expanded != state:
            self.__expanded = state
            if state and self.__expandedWidget is not None:
                self.__stack.setCurrentWidget(self.__expandedWidget)
            elif not state and self.__collapsedWidget is not None:
                self.__stack.setCurrentWidget(self.__collapsedWidget)
            self.__fixIcon()

            self.expandedChanged.emit(state)

    def expanded(self):
        # type: () -> bool
        """
        Is the dock widget in expanded state. If `True` the
        ``expandedWidget`` will be shown, and ``collapsedWidget`` otherwise.
        """
        return self.__expanded

    expanded_ = Property(bool, fset=setExpanded, fget=expanded)

    def setWidget(self, w):
        raise NotImplementedError(
                "Please use the 'setExpandedWidget'/'setCollapsedWidget' "
                "methods to set the contents of the dock widget."
              )

    def setExpandedWidget(self, widget):
        # type: (QWidget) -> None
        """
        Set the widget with contents to show while expanded.
        """
        if widget is self.__expandedWidget:
            return

        if self.__expandedWidget is not None:
            self.__stack.removeWidget(self.__expandedWidget)

        self.__stack.insertWidget(0, widget)
        self.__expandedWidget = widget

        if self.__expanded:
            self.__stack.setCurrentWidget(widget)
            self.updateGeometry()

    def expandedWidget(self):
        # type: () -> Optional[QWidget]
        """
        Return the widget previously set with ``setExpandedWidget``,
        or ``None`` if no widget has been set.
        """
        return self.__expandedWidget

    def setCollapsedWidget(self, widget):
        # type: (QWidget) -> None
        """
        Set the widget with contents to show while collapsed.
        """
        if widget is self.__collapsedWidget:
            return

        if self.__collapsedWidget is not None:
            self.__stack.removeWidget(self.__collapsedWidget)

        self.__stack.insertWidget(1, widget)
        self.__collapsedWidget = widget

        if not self.__expanded:
            self.__stack.setCurrentWidget(widget)
            self.updateGeometry()

    def collapsedWidget(self):
        # type: () -> Optional[QWidget]
        """
        Return the widget previously set with ``setCollapsedWidget``,
        or ``None`` if no widget has been set.
        """
        return self.__collapsedWidget

    def setAnimationEnabled(self, animationEnabled):
        self.__stack.setAnimationEnabled(animationEnabled)

    def animationEnabled(self):
        return self.__stack.animationEnabled()

    def currentWidget(self):
        # type: () -> Optional[QWidget]
        """
        Return the current shown widget depending on the `expanded` state
        """
        if self.__expanded:
            return self.__expandedWidget
        else:
            return self.__collapsedWidget

    def expand(self):
        # type: () -> None
        """
        Expand the dock (same as ``setExpanded(True)``)
        """
        self.setExpanded(True)

    def collapse(self):
        # type: () -> None
        """
        Collapse the dock (same as ``setExpanded(False)``)
        """
        self.setExpanded(False)

    def eventFilter(self, obj, event):
        # type: (QObject, QEvent) -> bool
        """Reimplemented."""
        if obj is self.__closeButton:
            etype = event.type()
            if etype == QEvent.MouseButtonPress:
                self.setExpanded(not self.__expanded)
                return True
            elif etype == QEvent.MouseButtonDblClick or \
                    etype == QEvent.MouseButtonRelease:
                return True
            # TODO: which other events can trigger the button (is the button
            # focusable).

        return super().eventFilter(obj, event)

    def event(self, event):
        # type: (QEvent) -> bool
        """Reimplemented."""
        if event.type() == QEvent.LayoutRequest:
            self.__fixMinimumWidth()
        return super().event(event)

    def __onDockLocationChanged(self, area):
        # type: (Qt.DockWidgetArea) -> None
        if area == Qt.LeftDockWidgetArea:
            self.setLayoutDirection(Qt.LeftToRight)
        else:
            self.setLayoutDirection(Qt.RightToLeft)

        self.__stack.setLayoutDirection(self.parentWidget().layoutDirection())
        self.__fixIcon()

    def __fixMinimumWidth(self):
        # type: () -> None
        # A workaround for forcing the QDockWidget layout to disregard the
        # default minimumSize which can be to wide for us (overriding the
        # minimumSizeHint or setting the minimum size directly does not
        # seem to have an effect (Qt 4.8.3).
        size = self.__stack.sizeHint()
        if size.isValid() and not size.isEmpty():
            left, _, right, _ = self.getContentsMargins()
            width = size.width() + left + right

            if width < self.minimumSizeHint().width():
                if not self.__hasFixedWidth():
                    self.__trueMinimumWidth = self.minimumSizeHint().width()
                self.setFixedWidth(width)
            else:
                if self.__hasFixedWidth():
                    if width >= self.__trueMinimumWidth:
                        self.__trueMinimumWidth = -1
                        self.setFixedWidth(QWIDGETSIZE_MAX)
                        self.updateGeometry()
                    else:
                        self.setFixedWidth(width)

    def __hasFixedWidth(self):
        # type: () -> bool
        return self.__trueMinimumWidth >= 0

    def __fixIcon(self):
        # type: () -> None
        """Fix the dock close icon.
        """
        direction = self.layoutDirection()
        if direction == Qt.LeftToRight:
            if self.__expanded:
                icon = self.__iconLeft
            else:
                icon = self.__iconRight
        else:
            if self.__expanded:
                icon = self.__iconRight
            else:
                icon = self.__iconLeft

        self.__closeButton.setIcon(icon)

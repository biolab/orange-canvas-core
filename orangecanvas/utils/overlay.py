import enum
import functools
import logging
import operator
import sys
from collections import namedtuple

from AnyQt.QtCore import Signal, Qt, QSize, Slot, QObject, Property, QRect, QEvent, QPoint
from AnyQt.QtGui import QIcon, QPixmap, QPainter, QPalette
from AnyQt.QtWidgets import QAbstractButton, QHBoxLayout, QPushButton, QStyle, QWidget, \
    QVBoxLayout, QLabel, QSizePolicy, QStyleOption, QFocusFrame, QStylePainter, QStyleOptionButton

from orangecanvas.gui.stackedwidget import StackLayout

log = logging.getLogger(__name__)


class StandardButton(enum.IntEnum):
    NoButton, Ok, Close, Dismiss = 0x0, 0x1, 0x2, 0x4


class ButtonRole(enum.IntEnum):
    InvalidRole, AcceptRole, RejectRole, DismissRole = 0, 1, 2, 3


class Notification(QObject):
    """
    Notification data bean used to construct NotificationWidget instances.
    Pass an instance of this class to NotificationServer.registerNotification().

    Args:
        title (str)
        text (str)
        accept_button_label (str)
        reject_button_label (str)
        iconPath (str): Relative to Orange directory
    """

    InvalidRole, AcceptRole, RejectRole, DismissRole = list(ButtonRole)

    # upon calling NotificationServer.registerNotification,
    # the following signals are connected to the instantiated NotificationWidgets'
    clicked = Signal(ButtonRole)
    accepted = Signal()
    rejected = Signal()
    dismissed = Signal()

    def __init__(self, title, text, accept_button_label=None, reject_button_label=None, icon=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = title
        self.text = text
        self.accept_button_label = accept_button_label
        self.reject_button_label = reject_button_label
        self.icon = icon


class OverlayWidget(QWidget):
    """
    A widget positioned on top of another widget.
    """
    def __init__(self, parent=None, alignment=Qt.AlignCenter, **kwargs):
        super().__init__(parent, **kwargs)
        self.setContentsMargins(0, 0, 0, 0)
        self.__alignment = alignment
        self.__widget = None

    def setWidget(self, widget):
        """
        Set the widget over which this overlay should be displayed (anchored).

        :type widget: QWidget
        """
        if self.__widget is not None:
            self.__widget.removeEventFilter(self)
            self.__widget.destroyed.disconnect(self.__on_destroyed)
        self.__widget = widget
        if self.__widget is not None:
            self.__widget.installEventFilter(self)
            self.__widget.destroyed.connect(self.__on_destroyed)

        if self.__widget is None:
            self.hide()
        else:
            self.__layout()

    def widget(self):
        """
        Return the overlaid widget.

        :rtype: QWidget | None
        """
        return self.__widget

    def setAlignment(self, alignment):
        """
        Set overlay alignment.

        :type alignment: Qt.Alignment
        """
        if self.__alignment != alignment:
            self.__alignment = alignment
            if self.__widget is not None:
                self.__layout()

    def alignment(self):
        """
        Return the overlay alignment.

        :rtype: Qt.Alignment
        """
        return self.__alignment

    def eventFilter(self, recv, event):
        # reimplemented
        if recv is self.__widget:
            if event.type() == QEvent.Resize or event.type() == QEvent.Move:
                self.__layout()
            elif event.type() == QEvent.Show:
                self.show()
            elif event.type() == QEvent.Hide:
                self.hide()
        return super().eventFilter(recv, event)

    def event(self, event):
        # reimplemented
        if event.type() == QEvent.LayoutRequest:
            self.__layout()
            return True
        else:
            return super().event(event)

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, painter, self)

    def showEvent(self, event):
        super().showEvent(event)
        # Force immediate re-layout on show
        self.__layout()

    def __layout(self):
        # position itself over `widget`
        # pylint: disable=too-many-branches
        widget = self.__widget
        if widget is None:
            return

        alignment = self.__alignment
        policy = self.sizePolicy()

        if widget.window() is self.window() and not self.isWindow():
            if widget.isWindow():
                bounds = widget.rect()
            else:
                bounds = QRect(widget.mapTo(widget.window(), QPoint(0, 0)),
                               widget.size())
            tl = self.parent().mapFrom(widget.window(), bounds.topLeft())
            bounds = QRect(tl, widget.size())
        else:
            if widget.isWindow():
                bounds = widget.geometry()
            else:
                bounds = QRect(widget.mapToGlobal(QPoint(0, 0)),
                               widget.size())

            if self.isWindow():
                bounds = bounds
            else:
                bounds = QRect(self.parent().mapFromGlobal(bounds.topLeft()),
                               bounds.size())

        sh = self.sizeHint()
        minsh = self.minimumSizeHint()
        minsize = self.minimumSize()
        if minsize.isNull():
            minsize = minsh
        maxsize = bounds.size().boundedTo(self.maximumSize())
        minsize = minsize.boundedTo(maxsize)
        effectivesh = sh.expandedTo(minsize).boundedTo(maxsize)

        hpolicy = policy.horizontalPolicy()
        vpolicy = policy.verticalPolicy()

        if not effectivesh.isValid():
            effectivesh = QSize(0, 0)
            vpolicy = hpolicy = QSizePolicy.Ignored

        def getsize(hint, minimum, maximum, policy):
            if policy == QSizePolicy.Ignored:
                return maximum
            elif policy & QSizePolicy.ExpandFlag:
                return maximum
            else:
                return max(hint, minimum)

        width = getsize(effectivesh.width(), minsize.width(),
                        maxsize.width(), hpolicy)

        heightforw = self.heightForWidth(width)
        if heightforw > 0:
            height = getsize(heightforw, minsize.height(),
                             maxsize.height(), vpolicy)
        else:
            height = getsize(effectivesh.height(), minsize.height(),
                             maxsize.height(), vpolicy)

        size = QSize(width, height)
        if alignment & Qt.AlignLeft:
            x = bounds.x()
        elif alignment & Qt.AlignRight:
            x = bounds.x() + bounds.width() - size.width()
        else:
            x = bounds.x() + max(0, bounds.width() - size.width()) // 2

        if alignment & Qt.AlignTop:
            y = bounds.y()
        elif alignment & Qt.AlignBottom:
            y = bounds.y() + bounds.height() - size.height()
        else:
            y = bounds.y() + max(0, bounds.height() - size.height()) // 2

        geom = QRect(QPoint(x, y), size)
        self.setGeometry(geom)

    @Slot()
    def __on_destroyed(self):
        self.__widget = None
        if self.isVisible():
            self.hide()


class NotificationMessageWidget(QWidget):
    #: Emitted when a button with the AcceptRole is clicked
    accepted = Signal()
    #: Emitted when a button with the RejectRole is clicked
    rejected = Signal()
    #: Emitted when a button is clicked
    clicked = Signal(QAbstractButton)

    NoButton, Ok, Close = list(StandardButton)[:3]
    InvalidRole, AcceptRole, RejectRole = list(ButtonRole)[:3]

    _Button = namedtuple("_Button", ["button", "role", "stdbutton"])

    def __init__(self, parent=None, icon=QIcon(), title="", text="", wordWrap=False,
                 textFormat=Qt.PlainText, standardButtons=NoButton, acceptLabel="Ok",
                 rejectLabel="No", **kwargs):
        super().__init__(parent, **kwargs)
        self._title = title
        self._text = text
        self._icon = QIcon()
        self._wordWrap = wordWrap
        self._standardButtons = NotificationMessageWidget.NoButton
        self._buttons = []
        self._acceptLabel = acceptLabel
        self._rejectLabel = rejectLabel

        self._iconlabel = QLabel(objectName="icon-label")
        self._titlelabel = QLabel(objectName="title-label", text=title,
                                  wordWrap=wordWrap, textFormat=textFormat)
        self._textlabel = QLabel(objectName="text-label", text=text,
                                 wordWrap=wordWrap, textFormat=textFormat)
        self._textlabel.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self._textlabel.setOpenExternalLinks(True)

        if sys.platform == "darwin":
            self._titlelabel.setAttribute(Qt.WA_MacSmallSize)
            self._textlabel.setAttribute(Qt.WA_MacSmallSize)

        layout = QHBoxLayout()
        self._iconlabel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        layout.addWidget(self._iconlabel)
        layout.setAlignment(self._iconlabel, Qt.AlignTop)

        message_layout = QVBoxLayout()
        self._titlelabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        if sys.platform == "darwin":
            self._titlelabel.setContentsMargins(0, 1, 0, 0)
        else:
            self._titlelabel.setContentsMargins(0, 0, 0, 0)
        message_layout.addWidget(self._titlelabel)
        self._textlabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        message_layout.addWidget(self._textlabel)

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setAlignment(Qt.AlignLeft)
        message_layout.addLayout(self.buttonLayout)

        layout.addLayout(message_layout)
        layout.setSpacing(7)
        self.setLayout(layout)
        self.setIcon(icon)
        self.setStandardButtons(standardButtons)

    def setText(self, text):
        """
        Set the current message text.

        :type message: str
        """
        if self._text != text:
            self._text = text
            self._textlabel.setText(text)

    def text(self):
        """
        Return the current message text.

        :rtype: str
        """
        return self._text

    def setTitle(self, title):
        """
        Set the current title text.

        :type title: str
        """
        if self._title != title:
            self._title = title
            self._titleLabel.setText(title)

    def title(self):
        """
        Return the current title text.

        :rtype: str
        """
        return self._title

    def setIcon(self, icon):
        """
        Set the message icon.

        :type icon: QIcon | QPixmap | QString | QStyle.StandardPixmap
        """
        if isinstance(icon, QStyle.StandardPixmap):
            icon = self.style().standardIcon(icon)
        else:
            icon = QIcon(icon)

        if self._icon != icon:
            self._icon = QIcon(icon)
            if not self._icon.isNull():
                size = self.style().pixelMetric(
                    QStyle.PM_SmallIconSize, None, self)
                pm = self._icon.pixmap(QSize(size, size))
            else:
                pm = QPixmap()

            self._iconlabel.setPixmap(pm)
            self._iconlabel.setVisible(not pm.isNull())

    def icon(self):
        """
        Return the current icon.

        :rtype: QIcon
        """
        return QIcon(self._icon)

    def setWordWrap(self, wordWrap):
        """
        Set the message text wrap property

        :type wordWrap: bool
        """
        if self._wordWrap != wordWrap:
            self._wordWrap = wordWrap
            self._textlabel.setWordWrap(wordWrap)

    def wordWrap(self):
        """
        Return the message text wrap property.

        :rtype: bool
        """
        return self._wordWrap

    def setTextFormat(self, textFormat):
        """
        Set message text format

        :type textFormat: Qt.TextFormat
        """
        self._textlabel.setTextFormat(textFormat)

    def textFormat(self):
        """
        Return the message text format.

        :rtype: Qt.TextFormat
        """
        return self._textlabel.textFormat()

    def setAcceptLabel(self, label):
        """
        Set the accept button label.
        :type label: str
        """
        self._acceptLabel = label

    def acceptLabel(self):
        """
        Return the accept button label.
        :rtype str
        """
        return self._acceptLabel

    def setRejectLabel(self, label):
        """
        Set the reject button label.
        :type label: str
        """
        self._rejectLabel = label

    def rejectLabel(self):
        """
        Return the reject button label.
        :rtype str
        """
        return self._rejectLabel

    def setStandardButtons(self, buttons):
        for button in StandardButton:
            existing = self.button(button)
            if button & buttons and existing is None:
                self.addButton(button)
            elif existing is not None:
                self.removeButton(existing)

    def standardButtons(self):
        return functools.reduce(
            operator.ior,
            (slot.stdbutton for slot in self._buttons
             if slot.stdbutton is not None),
            NotificationMessageWidget.NoButton)

    def addButton(self, button, *rolearg):
        """
        addButton(QAbstractButton, ButtonRole)
        addButton(str, ButtonRole)
        addButton(StandardButton)

        Add and return a button
        """
        stdbutton = None
        if isinstance(button, QAbstractButton):
            if len(rolearg) != 1:
                raise TypeError("Wrong number of arguments for "
                                "addButton(QAbstractButton, role)")
            role = rolearg[0]
        elif isinstance(button, StandardButton):
            if rolearg:
                raise TypeError("Wrong number of arguments for "
                                "addButton(StandardButton)")
            stdbutton = button
            if button == NotificationMessageWidget.Ok:
                role = NotificationMessageWidget.AcceptRole
                button = QPushButton(self._acceptLabel, default=False, autoDefault=False)
            elif button == NotificationMessageWidget.Close:
                role = NotificationMessageWidget.RejectRole
                button = QPushButton(self._rejectLabel, default=False, autoDefault=False)
        elif isinstance(button, str):
            if len(rolearg) != 1:
                raise TypeError("Wrong number of arguments for "
                                "addButton(str, ButtonRole)")
            role = rolearg[0]
            button = QPushButton(button, default=False, autoDefault=False)

        if sys.platform == "darwin":
            button.setAttribute(Qt.WA_MacSmallSize)

        self._buttons.append(NotificationMessageWidget._Button(button, role, stdbutton))
        button.clicked.connect(self._button_clicked)
        self._relayout()

        return button

    def _relayout(self):
        for slot in self._buttons:
            self.buttonLayout.removeWidget(slot.button)
        order = {
            NotificationWidget.AcceptRole: 0,
            NotificationWidget.RejectRole: 1,
        }
        ordered = sorted([b for b in self._buttons],
                         key=lambda slot: order.get(slot.role, -1))

        prev = self._textlabel
        for slot in ordered:
            self.buttonLayout.addWidget(slot.button)
            QWidget.setTabOrder(prev, slot.button)

    def removeButton(self, button):
        """
        Remove a `button`.

        :type button: QAbstractButton
        """
        slot = [s for s in self._buttons if s.button is button]
        if slot:
            slot = slot[0]
            self._buttons.remove(slot)
            self.layout().removeWidget(slot.button)
            slot.button.setParent(None)

    def buttonRole(self, button):
        """
        Return the ButtonRole for button

        :type button: QAbstractButton
        """
        for slot in self._buttons:
            if slot.button is button:
                return slot.role
        return NotificationMessageWidget.InvalidRole

    def button(self, standardButton):
        """
        Return the button for the StandardButton.

        :type standardButton: StandardButton
        """
        for slot in self._buttons:
            if slot.stdbutton == standardButton:
                return slot.button
        return None

    def _button_clicked(self):
        button = self.sender()
        role = self.buttonRole(button)
        self.clicked.emit(button)

        if role == NotificationMessageWidget.AcceptRole:
            self.accepted.emit()
        elif role == NotificationMessageWidget.RejectRole:
            self.rejected.emit()


class DismissButton(QAbstractButton):
    """
    A simple icon button widget.
    """
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.__focusframe = None

    def focusInEvent(self, event):
        # reimplemented
        event.accept()
        if self.__focusframe is None:
            self.__focusframe = QFocusFrame(self)
            self.__focusframe.setWidget(self)
            palette = self.palette()
            palette.setColor(QPalette.Foreground,
                             palette.color(QPalette.Highlight))
            self.__focusframe.setPalette(palette)

    def focusOutEvent(self, event):
        # reimplemented
        event.accept()
        if self.__focusframe is not None:
            self.__focusframe.hide()
            self.__focusframe.deleteLater()
            self.__focusframe = None

    def event(self, event):
        if event.type() == QEvent.Enter or event.type() == QEvent.Leave:
            self.update()
        return super().event(event)

    def sizeHint(self):
        # reimplemented
        self.ensurePolished()
        iconsize = self.iconSize()
        icon = self.icon()
        if not icon.isNull():
            iconsize = icon.actualSize(iconsize)
        return iconsize

    def minimumSizeHint(self):
        # reimplemented
        return self.sizeHint()

    def paintEvent(self, event):
        painter = QStylePainter(self)
        option = QStyleOptionButton()
        option.initFrom(self)
        option.text = ""
        option.icon = self.icon()
        option.iconSize = self.iconSize()
        option.features = QStyleOptionButton.Flat
        if self.isDown():
            option.state |= QStyle.State_Sunken
            painter.drawPrimitive(QStyle.PE_PanelButtonBevel, option)

        if not option.icon.isNull():
            if option.state & QStyle.State_Active:
                mode = (QIcon.Active if option.state & QStyle.State_MouseOver
                        else QIcon.Normal)
            else:
                mode = QIcon.Disabled
            if self.isChecked():
                state = QIcon.On
            else:
                state = QIcon.Off
            option.icon.paint(painter, option.rect, Qt.AlignCenter, mode, state)


def proxydoc(func):
    return functools.wraps(func, assigned=["__doc__"], updated=[])


class NotificationWidget(QWidget):
    #: Emitted when a button with an Accept role is clicked
    accepted = Signal()
    #: Emitted when a button with a Reject role is clicked
    rejected = Signal()
    #: Emitted when a button with a Dismiss role is clicked
    dismissed = Signal()
    #: Emitted when a button is clicked
    clicked = Signal(QAbstractButton)

    NoButton, Ok, Close, Dismiss = list(StandardButton)
    InvalidRole, AcceptRole, RejectRole, DismissRole = list(ButtonRole)

    def __init__(self, parent, title="", text="", textFormat=Qt.AutoText,
                 icon=QIcon(), wordWrap=True,
                 standardButtons=NoButton, acceptLabel="Ok", rejectLabel="No",  **kwargs):
        super().__init__(parent, **kwargs)

        self._dismissMargin = 10

        layout = QHBoxLayout()
        if sys.platform == "darwin":
            layout.setContentsMargins(6, 6, 6, 6)
        else:
            layout.setContentsMargins(9, 9, 9, 9)

        self._msgWidget = NotificationMessageWidget(
            parent=self, title=title, text=text, textFormat=textFormat, icon=icon,
            wordWrap=wordWrap, standardButtons=standardButtons, acceptLabel=acceptLabel,
            rejectLabel=rejectLabel
        )

        self.dismissButton = DismissButton(parent=self,
                                           icon=QIcon(self.style().standardIcon(
                                                QStyle.SP_TitleBarCloseButton)))
        self.dismissButton.setFixedSize(18, 18)
        self.dismissButton.clicked.connect(self.dismissed)

        def dismiss_handler():
            self.clicked.emit(self.dismissButton)

        self.dismissButton.clicked.connect(dismiss_handler)
        self._msgWidget.accepted.connect(self.accepted)
        self._msgWidget.rejected.connect(self.rejected)
        self._msgWidget.clicked.connect(self.clicked)

        layout.addWidget(self._msgWidget)
        self.setLayout(layout)

        self.setFixedWidth(400)

    def dismissMargin(self):
        return self._dismissMargin

    def setDismissMargin(self, margin):
        self._dismissMargin = margin

    dismissMargin_ = Property(int,
                              fget=dismissMargin,
                              fset=setDismissMargin,
                              designable=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if sys.platform == "darwin":
            corner_margin = 6
        else:
            corner_margin = 7
        x = self.width() - self.dismissButton.width() - self._dismissMargin - corner_margin
        y = self._dismissMargin + corner_margin
        self.dismissButton.move(x, y)

    def paintEvent(self, event):
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PE_Widget, opt, painter, self)

    @staticmethod
    def fromNotification(notif: Notification, parent=None):
        """
        Creates NotificatonWidget from a Notification.
        :type: Notification
        :rtype: NotificationWidget
        """
        kwargs = {}

        kwargs['title'] = notif.title
        kwargs['text'] = notif.text

        if notif.icon:
            kwargs['icon'] = notif.icon

        buttons = 0
        if notif.accept_button_label:
            kwargs['acceptLabel'] = notif.accept_button_label
            buttons |= NotificationWidget.Ok
        if notif.reject_button_label:
            kwargs['rejectLabel'] = notif.reject_button_label
            buttons |= NotificationWidget.Close
        kwargs['standardButtons'] = buttons

        notifWidget = NotificationWidget(parent, **kwargs)

        return notifWidget

    @proxydoc(NotificationMessageWidget.setText)
    def setText(self, text):
        self._msgWidget.setText(text)

    @proxydoc(NotificationMessageWidget.text)
    def text(self):
        return self._msgWidget.text()

    @proxydoc(NotificationMessageWidget.setTitle)
    def setTitle(self, title):
        self._msgWidget.setTitle(title)

    @proxydoc(NotificationMessageWidget.title)
    def title(self):
        return self._msgWidget.title()

    @proxydoc(NotificationMessageWidget.setIcon)
    def setIcon(self, icon):
        self._msgWidget.setIcon(icon)

    @proxydoc(NotificationMessageWidget.icon)
    def icon(self):
        return self._msgWidget.icon()

    @proxydoc(NotificationMessageWidget.textFormat)
    def textFormat(self):
        return self._msgWidget.textFormat()

    @proxydoc(NotificationMessageWidget.setTextFormat)
    def setTextFormat(self, textFormat):
        self._msgWidget.setTextFormat(textFormat)

    @proxydoc(NotificationMessageWidget.setStandardButtons)
    def setStandardButtons(self, buttons):
        self._msgWidget.setStandardButtons(buttons)

    @proxydoc(NotificationMessageWidget.addButton)
    def addButton(self, *args):
        return self._msgWidget.addButton(*args)

    @proxydoc(NotificationMessageWidget.removeButton)
    def removeButton(self, button):
        self._msgWidget.removeButton(button)

    @proxydoc(NotificationMessageWidget.buttonRole)
    def buttonRole(self, button):
        if button is self.dismissButton:
            return NotificationWidget.DismissRole
        return self._msgWidget.buttonRole(button)

    @proxydoc(NotificationMessageWidget.button)
    def button(self, standardButton):
        return self._msgWidget.button(standardButton)


class NotificationOverlay(OverlayWidget):
    def __init__(self, parent, alignment=Qt.AlignRight | Qt.AlignBottom, **kwargs):
        """
        An overlay for queueing/stacking notifications.
        """
        super().__init__(parent, alignment=alignment, **kwargs)
        self.setWidget(parent)

        layout = StackLayout()
        self.setLayout(layout)

        self._widgets = []

    def currentWidget(self):
        """
        Return the currently displayed widget.
        """
        if not self._widgets:
            return None
        return self._widgets[0]

    @Slot(Notification)
    def addNotification(self, notif: Notification):
        notifWidget = NotificationWidget.fromNotification(notif, parent=self)

        notifWidget.clicked.connect(lambda b:
                                    notif.clicked.emit(notifWidget.buttonRole(b)))
        notifWidget.accepted.connect(notif.accepted)
        notifWidget.rejected.connect(notif.rejected)
        notifWidget.dismissed.connect(notif.dismissed)

        self._addWidget(notifWidget)

    @Slot()
    def nextWidget(self):
        """
        Removes first widget from the stack.
        """
        if not self._widgets:
            log.error("Received next notification signal while no notification is displayed")
            return
        widget = self._widgets.pop(0)
        self.layout().removeWidget(widget)
        widget.close()

    def _addWidget(self, widget):
        """
        Append the widget to the stack.
        """
        self._widgets.append(widget)
        self.layout().addWidget(widget)


class NotificationServer(QObject):
    # emits when new notification is registered
    newNotification = Signal(Notification)

    # emits when a notification is responded to
    nextNotification = Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # list of queued Notification objects, to populate newly generated canvases
        self._notificationQueue = []

        self.nextNotification.connect(self._nextNotification)

    def registerNotification(self, notif: Notification):
        """
        :type notif: Notification

        After instantiating a Notification, use this method to send it.
        Queues notification in all canvas instances (shows it if no other notifications present).
        """
        notif.clicked.connect(self.nextNotification)
        self._notificationQueue.append(notif)
        self.newNotification.emit(notif)

    def getNotificationQueue(self):
        """
        Getter used to populate new canvas instances with the current
        notification queue.
        :rtype: Iterable[Notification]
        """
        return self._notificationQueue

    @Slot()
    def _nextNotification(self):
        if not self._notificationQueue:
            log.error("Received next notification signal while no notification is enqueued")
            return
        self._notificationQueue.pop(0)



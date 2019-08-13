"""
Orange Canvas Welcome Dialog
"""
from typing import Optional, Union, Iterable

from xml.sax.saxutils import escape

from AnyQt.QtWidgets import (
    QDialog, QWidget, QToolButton, QCheckBox, QAction,
    QHBoxLayout, QVBoxLayout, QSizePolicy, QLabel, QApplication
)
from AnyQt.QtGui import (
    QFont, QIcon, QPixmap, QPainter, QColor, QBrush, QActionEvent
)

from AnyQt.QtCore import Qt, QRect, QSize, QPoint
from AnyQt.QtCore import pyqtSignal as Signal

from ..canvas.items.utils import radial_gradient
from ..registry import NAMED_COLORS


def decorate_welcome_icon(icon, background_color):
    # type: (QIcon, Union[QColor, str]) -> QIcon
    """Return a `QIcon` with a circle shaped background.
    """
    welcome_icon = QIcon()
    sizes = [32, 48, 64, 80, 128, 256]
    background_color = NAMED_COLORS.get(background_color, background_color)
    background_color = QColor(background_color)
    grad = radial_gradient(background_color)
    for size in sizes:
        icon_size = QSize(int(5 * size / 8), int(5 * size / 8))
        icon_rect = QRect(QPoint(0, 0), icon_size)
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        ellipse_rect = QRect(0, 0, size, size)
        p.drawEllipse(ellipse_rect)
        icon_rect.moveCenter(ellipse_rect.center())
        icon.paint(p, icon_rect, Qt.AlignCenter, )
        p.end()

        welcome_icon.addPixmap(pixmap)

    return welcome_icon


WELCOME_WIDGET_BUTTON_STYLE = """
WelcomeActionButton {
    border: 1px solid transparent;
    border-radius: 10px;
    font-size: 13px;
    icon-size: 75px;
}
WelcomeActionButton:pressed {
    background-color: palette(highlight);
    color: palette(highlighted-text);
}
WelcomeActionButton:focus {
    border: 1px solid palette(highlight);
}
"""


class WelcomeActionButton(QToolButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFont(QApplication.font("QAbstractButton"))

    def actionEvent(self, event):
        # type: (QActionEvent) -> None
        super().actionEvent(event)
        if event.type() == QActionEvent.ActionChanged \
                and event.action() is self.defaultAction():
            # The base does not update self visibility for defaultAction.
            self.setVisible(event.action().isVisible())


class WelcomeDialog(QDialog):
    """
    A welcome widget shown at startup presenting a series
    of buttons (actions) for a beginner to choose from.
    """
    triggered = Signal(QAction)

    def __init__(self, *args, **kwargs):
        showAtStartup = kwargs.pop("showAtStartup", True)
        feedbackUrl = kwargs.pop("feedbackUrl", "")
        super().__init__(*args, **kwargs)

        self.__triggeredAction = None  # type: Optional[QAction]
        self.__showAtStartupCheck = None
        self.__mainLayout = None
        self.__feedbackUrl = None
        self.__feedbackLabel = None

        self.setupUi()

        self.setFeedbackUrl(feedbackUrl)
        self.setShowAtStartup(showAtStartup)

    def setupUi(self):
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)

        self.__mainLayout = QVBoxLayout()
        self.__mainLayout.setContentsMargins(0, 40, 0, 40)
        self.__mainLayout.setSpacing(65)

        self.layout().addLayout(self.__mainLayout)

        self.setStyleSheet(WELCOME_WIDGET_BUTTON_STYLE)

        bottom_bar = QWidget(objectName="bottom-bar")
        bottom_bar_layout = QHBoxLayout()
        bottom_bar_layout.setContentsMargins(20, 10, 20, 10)
        bottom_bar.setLayout(bottom_bar_layout)
        bottom_bar.setSizePolicy(QSizePolicy.MinimumExpanding,
                                 QSizePolicy.Maximum)

        self.__showAtStartupCheck = QCheckBox(
            self.tr("Show at startup"), bottom_bar, checked=False
        )
        self.__feedbackLabel = QLabel(
            textInteractionFlags=Qt.TextBrowserInteraction,
            openExternalLinks=True,
            visible=False,
        )

        bottom_bar_layout.addWidget(
            self.__showAtStartupCheck, alignment=Qt.AlignVCenter | Qt.AlignLeft
        )
        bottom_bar_layout.addWidget(
            self.__feedbackLabel, alignment=Qt.AlignVCenter | Qt.AlignRight
        )
        self.layout().addWidget(bottom_bar, alignment=Qt.AlignBottom,
                                stretch=1)

        self.setSizeGripEnabled(False)
        self.setFixedSize(620, 390)

    def setShowAtStartup(self, show):
        # type: (bool) -> None
        """
        Set the 'Show at startup' check box state.
        """
        if self.__showAtStartupCheck.isChecked() != show:
            self.__showAtStartupCheck.setChecked(show)

    def showAtStartup(self):
        # type: () -> bool
        """
        Return the 'Show at startup' check box state.
        """
        return self.__showAtStartupCheck.isChecked()

    def setFeedbackUrl(self, url):
        # type: (str) -> None
        """
        Set an 'feedback' url. When set a link is displayed in the bottom row.
        """
        self.__feedbackUrl = url
        if url:
            text = self.tr("Help us improve!")
            self.__feedbackLabel.setText(
                '<a href="{url}">{text}</a>'.format(url=url, text=escape(text))
            )
        else:
            self.__feedbackLabel.setText("")
        self.__feedbackLabel.setVisible(bool(url))

    def addRow(self, actions, background="light-orange"):
        """Add a row with `actions`.
        """
        count = self.__mainLayout.count()
        self.insertRow(count, actions, background)

    def insertRow(self, index, actions, background="light-orange"):
        # type: (int, Iterable[QAction], Union[QColor, str]) -> None
        """Insert a row with `actions` at `index`.
        """
        widget = QWidget(objectName="icon-row")
        layout = QHBoxLayout()
        layout.setContentsMargins(40, 0, 40, 0)
        layout.setSpacing(65)
        widget.setLayout(layout)

        self.__mainLayout.insertWidget(index, widget, stretch=10,
                                       alignment=Qt.AlignCenter)

        for i, action in enumerate(actions):
            self.insertAction(index, i, action, background)

    def insertAction(self, row, index, action, background="light-orange"):
        """Insert `action` in `row` in position `index`.
        """
        button = self.createButton(action, background)
        self.insertButton(row, index, button)

    def insertButton(self, row, index, button):
        # type: (int, int, QToolButton) -> None
        """Insert `button` in `row` in position `index`.
        """
        item = self.__mainLayout.itemAt(row)
        layout = item.widget().layout()
        layout.insertWidget(index, button)
        button.triggered.connect(self.__on_actionTriggered)

    def createButton(self, action, background="light-orange"):
        # type: (QAction, Union[QColor, str]) -> QToolButton
        """Create a tool button for action.
        """
        button = WelcomeActionButton(self)
        button.setDefaultAction(action)
        button.setText(action.iconText())
        button.setIcon(decorate_welcome_icon(action.icon(), background))
        button.setToolTip(action.toolTip())
        button.setFixedSize(100, 100)
        button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        button.setVisible(action.isVisible())
        font = QFont(button.font())
        font.setPointSize(13)
        button.setFont(font)

        return button

    def buttonAt(self, i, j):
        # type: (int, int) -> QToolButton
        """Return the button at i-t row and j-th column.
        """
        item = self.__mainLayout.itemAt(i)
        row = item.widget()
        item = row.layout().itemAt(j)
        return item.widget()

    def triggeredAction(self):
        # type: () -> Optional[QAction]
        """Return the action that was triggered by the user.
        """
        return self.__triggeredAction

    def showEvent(self, event):
        # Clear the triggered action before show.
        self.__triggeredAction = None
        super().showEvent(event)

    def __on_actionTriggered(self, action):
        # type: (QAction) -> None
        """Called when the button action is triggered.
        """
        self.triggered.emit(action)
        self.__triggeredAction = action

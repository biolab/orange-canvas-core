from typing import Sequence

from AnyQt.QtCore import QObject, Signal, Slot, Qt
from AnyQt.QtWidgets import QWidget, QAction, QActionGroup, QApplication

from orangecanvas.utils import findf

__all__ = [
    "WindowListManager",
]


class WindowListManager(QObject):
    """
    An open windows list manager.

    Provides and manages actions for opened 'Windows' menu bar entries.
    """
    #: Signal emitted when a widget/window is added
    windowAdded = Signal(QWidget, QAction)
    #: Signal emitted when a widget/window is removed
    windowRemoved = Signal(QWidget, QAction)

    __instance = None

    @staticmethod
    def instance() -> "WindowListManager":
        """Return the global WindowListManager instance."""
        if WindowListManager.__instance is None:
            return WindowListManager()
        return WindowListManager.__instance

    def __init__(self, *args, **kwargs):
        if self.__instance is not None:
            raise RuntimeError
        WindowListManager.__instance = self
        super().__init__(*args, **kwargs)
        self.__group = QActionGroup(
            self, objectName="window-list-manager-action-group"
        )
        self.__group.setExclusive(True)
        self.__windows = []
        app = QApplication.instance()
        app.focusWindowChanged.connect(
            self.__focusWindowChanged, Qt.QueuedConnection
        )

    def actionGroup(self) -> QActionGroup:
        """Return the QActionGroup containing the *Window* actions."""
        return self.__group

    def addWindow(self, window: QWidget) -> None:
        """Add a `window` to the managed list."""
        if window in self.__windows:
            raise ValueError(f"{window} already added")
        action = self.createActionForWindow(window)
        self.__windows.append(window)
        self.__group.addAction(action)
        self.windowAdded.emit(window, action)

    def removeWindow(self, window: QWidget) -> None:
        """Remove the `window` from the managed list."""
        self.__windows.remove(window)
        act = self.actionForWindow(window)
        self.__group.removeAction(act)
        self.windowRemoved.emit(window, act)
        act.setData(None)
        act.setParent(None)
        act.deleteLater()

    def actionForWindow(self, window: QWidget) -> QAction:
        """Return the `QAction` representing the `window`."""
        return findf(self.actions(), lambda a: a.data() is window)

    def createActionForWindow(self, window: QWidget) -> QAction:
        """Create the `QAction` instance for managing the `window`."""
        action = QAction(
            window.windowTitle(),
            window,
            visible=window.isVisible(),
            checkable=True,
            objectName="action-canvas-window-list-manager-window-action"
        )
        action.setData(window)
        handle = window.windowHandle()
        if not handle:
            # TODO: need better visible, title notify bypassing QWindow
            window.create()
            handle = window.windowHandle()
        action.setChecked(handle.isActive())
        handle.visibleChanged.connect(action.setVisible)
        handle.windowTitleChanged.connect(action.setText)

        def activate(state):
            if not state:
                return
            handle: QWidget = action.data()
            handle.setVisible(True)
            if handle != QApplication.activeWindow():
                # Do not re-activate when called from `focusWindowChanged`;
                # breaks macOS window cycling (CMD+`) order.
                handle.raise_()
                handle.activateWindow()

        action.toggled.connect(activate)
        return action

    def actions(self) -> Sequence[QAction]:
        """Return all actions representing managed windows."""
        return self.__group.actions()

    @Slot()
    def __focusWindowChanged(self):
        window = QApplication.activeWindow()
        act = findf(self.actions(), lambda a: a.data() is window)
        if act is not None and not act.isChecked():
            act.setChecked(True)

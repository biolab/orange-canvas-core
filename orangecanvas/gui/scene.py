from typing import Optional

from AnyQt.QtCore import Qt, QObject, Signal
from AnyQt.QtGui import QTransform, QKeyEvent
from AnyQt.QtWidgets import (
    QGraphicsScene, QGraphicsView, QGraphicsSceneHelpEvent, QToolTip,
    QGraphicsSceneMouseEvent, QGraphicsSceneContextMenuEvent,
    QGraphicsSceneDragDropEvent, QApplication
)

from orangecanvas.gui.quickhelp import QuickHelpTipEvent


class UserInteraction(QObject):
    """
    Base class for user interaction handlers.

    Parameters
    ----------
    parent : :class:`QObject`, optional
        A parent QObject
    deleteOnEnd : bool, optional
        Should the UserInteraction be deleted when it finishes (``True``
        by default).
    """
    # Cancel reason flags

    #: No specified reason
    NoReason = 0
    #: User canceled the operation (e.g. pressing ESC)
    UserCancelReason = 1
    #: Another interaction was set
    InteractionOverrideReason = 3
    #: An internal error occurred
    ErrorReason = 4
    #: Other (unspecified) reason
    OtherReason = 5

    #: Emitted when the interaction is set on the scene.
    started = Signal()

    #: Emitted when the interaction finishes successfully.
    finished = Signal()

    #: Emitted when the interaction ends (canceled or finished)
    ended = Signal()

    #: Emitted when the interaction is canceled.
    canceled = Signal(int)

    def __init__(self, scene: 'GraphicsScene', parent: Optional[QObject] = None,
                 deleteOnEnd=True, **kwargs):
        super().__init__(parent, **kwargs)
        self.scene = scene
        self.deleteOnEnd = deleteOnEnd
        self.cancelOnEsc = False

        self.__finished = False
        self.__canceled = False
        self.__cancelReason = self.NoReason

    def start(self) -> None:
        """
        Start the interaction. This is called by the :class:`GraphicsScene`
        when the interaction is installed.

        .. note:: Must be called from subclass implementations.
        """
        self.started.emit()

    def end(self) -> None:
        """
        Finish the interaction. Restore any leftover state in this method.

        .. note:: This gets called from the default :func:`cancel`
                  implementation.
        """
        self.__finished = True

        if self.scene.user_interaction_handler is self:
            self.scene.set_user_interaction_handler(None)

        if self.__canceled:
            self.canceled.emit(self.__cancelReason)
        else:
            self.finished.emit()
        self.ended.emit()

        if self.deleteOnEnd:
            self.deleteLater()

    def cancel(self, reason=OtherReason) -> None:
        """
        Cancel the interaction with `reason`.
        """
        self.__canceled = True
        self.__cancelReason = reason
        self.end()

    def isFinished(self) -> bool:
        """
        Is the interaction finished.
        """
        return self.__finished

    def isCanceled(self) -> bool:
        """
        Was the interaction canceled.
        """
        return self.__canceled

    def cancelReason(self) -> int:
        """
        Return the reason the interaction was canceled.
        """
        return self.__cancelReason

    def postQuickTip(self, contents: str) -> None:
        """
        Post a QuickHelpTipEvent with rich text `contents` to the document
        editor.
        """
        hevent = QuickHelpTipEvent("", contents)
        QApplication.postEvent(self.document, hevent)

    def clearQuickTip(self):
        """Clear the quick tip help event."""
        self.postQuickTip("")

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> bool:
        """
        Handle a `QGraphicsScene.mousePressEvent`.
        """
        return False

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> bool:
        """
        Handle a `GraphicsScene.mouseMoveEvent`.
        """
        return False

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> bool:
        """
        Handle a `QGraphicsScene.mouseReleaseEvent`.
        """
        return False

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> bool:
        """
        Handle a `QGraphicsScene.mouseDoubleClickEvent`.
        """
        return False

    def keyPressEvent(self, event: QKeyEvent) -> bool:
        """
        Handle a `QGraphicsScene.keyPressEvent`
        """
        if self.cancelOnEsc and event.key() == Qt.Key_Escape:
            self.cancel(self.UserCancelReason)
        return False

    def keyReleaseEvent(self, event: QKeyEvent) -> bool:
        """
        Handle a `QGraphicsScene.keyPressEvent`
        """
        return False

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> bool:
        """
        Handle a `QGraphicsScene.contextMenuEvent`
        """
        return False

    def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent) -> bool:
        """
        Handle a `QGraphicsScene.dragEnterEvent`

        .. versionadded:: 0.1.20
        """
        return False

    def dragMoveEvent(self, event: QGraphicsSceneDragDropEvent) -> bool:
        """
        Handle a `QGraphicsScene.dragMoveEvent`

        .. versionadded:: 0.1.20
        """
        return False

    def dragLeaveEvent(self,event: QGraphicsSceneDragDropEvent) -> bool:
        """
        Handle a `QGraphicsScene.dragLeaveEvent`

        .. versionadded:: 0.1.20
        """
        return False

    def dropEvent(self, event: QGraphicsSceneDragDropEvent) -> bool:
        """
        Handle a `QGraphicsScene.dropEvent`

        .. versionadded:: 0.1.20
        """
        return False


class GraphicsScene(QGraphicsScene):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_interaction_handler: Optional[UserInteraction] = None

    def helpEvent(self, event: QGraphicsSceneHelpEvent) -> None:
        """
        Reimplemented.

        Send the help event to every graphics item that is under the event's
        scene position (default QGraphicsScene only dispatches help events to
        `QGraphicsProxyWidget`s.
        """
        widget = event.widget()
        if widget is not None and isinstance(widget.parentWidget(),
                                             QGraphicsView):
            view = widget.parentWidget()
            deviceTransform = view.viewportTransform()
        else:
            deviceTransform = QTransform()
        items = self.items(
            event.scenePos(), Qt.IntersectsItemShape, Qt.DescendingOrder,
            deviceTransform,
        )
        tooltiptext = None
        event.setAccepted(False)
        for item in items:
            self.sendEvent(item, event)
            if event.isAccepted():
                return
            elif item.toolTip():
                tooltiptext = item.toolTip()
                break
        QToolTip.showText(event.screenPos(), tooltiptext, event.widget())

    def mousePressEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.mousePressEvent(event):
            return
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.mouseMoveEvent(event):
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.mouseReleaseEvent(event):
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.mouseDoubleClickEvent(event):
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.keyPressEvent(event):
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.keyReleaseEvent(event):
            return
        super().keyReleaseEvent(event)

    def contextMenuEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.contextMenuEvent(event):
            return
        super().contextMenuEvent(event)

    def dragEnterEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.dragEnterEvent(event):
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.dragMoveEvent(event):
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.dragLeaveEvent(event):
            return
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if self.user_interaction_handler and \
                self.user_interaction_handler.dropEvent(event):
            return
        super().dropEvent(event)

    def set_user_interaction_handler(self, handler):
        # type: (UserInteraction) -> None
        if self.user_interaction_handler and \
                not self.user_interaction_handler.isFinished():
            self.user_interaction_handler.cancel()
        self.user_interaction_handler = handler

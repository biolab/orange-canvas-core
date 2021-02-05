"""
=========================
User Interaction Handlers
=========================

User interaction handlers for a :class:`~.SchemeEditWidget`.

User interactions encapsulate the logic of user interactions with the
scheme document.

All interactions are subclasses of :class:`UserInteraction`.


"""
import typing
from typing import Optional, Any, Tuple, List, Set, Iterable

import logging
from functools import reduce



from AnyQt.QtWidgets import (
    QApplication, QGraphicsRectItem, QUndoCommand, QGraphicsSceneMouseEvent,
    QGraphicsSceneContextMenuEvent, QWidget, QGraphicsItem,
)
from AnyQt.QtGui import QPen, QBrush, QColor, QFontMetrics, QKeyEvent, QFont
from AnyQt.QtCore import (
    Qt, QObject, QCoreApplication, QSizeF, QPointF, QRect, QRectF, QLineF,
    QPoint,
)
from AnyQt.QtCore import pyqtSignal as Signal

from orangecanvas.document.commands import UndoCommand
from .usagestatistics import UsageStatistics
from ..registry.description import WidgetDescription, OutputSignal, InputSignal
from ..registry.qt import QtWidgetRegistry
from .. import scheme
from ..scheme import SchemeNode as Node, SchemeLink as Link, Scheme, compatible_channels
from ..canvas import items
from ..canvas.items import controlpoints
from ..gui.quickhelp import QuickHelpTipEvent
from . import commands
from .editlinksdialog import EditLinksDialog

if typing.TYPE_CHECKING:
    from .schemeedit import SchemeEditWidget

    A = typing.TypeVar("A")
    #: Output/Input pair of a link
    OIPair = Tuple[OutputSignal, InputSignal]

log = logging.getLogger(__name__)


def assert_not_none(optional):
    # type: (Optional[A]) -> A
    assert optional is not None
    return optional


class UserInteraction(QObject):
    """
    Base class for user interaction handlers.

    Parameters
    ----------
    document : :class:`~.SchemeEditWidget`
        An scheme editor instance with which the user is interacting.
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
    canceled = Signal([], [int])

    def __init__(self, document, parent=None, deleteOnEnd=True):
        # type: ('SchemeEditWidget', Optional[QObject], bool) -> None
        super().__init__(parent)
        self.document = document
        self.scene = document.scene()
        scheme_ = document.scheme()
        assert scheme_ is not None
        self.scheme = scheme_  # type: scheme.Scheme
        self.suggestions = document.suggestions()
        self.deleteOnEnd = deleteOnEnd

        self.cancelOnEsc = False

        self.__finished = False
        self.__canceled = False
        self.__cancelReason = self.NoReason

    def start(self):
        # type: () -> None
        """
        Start the interaction. This is called by the :class:`CanvasScene` when
        the interaction is installed.

        .. note:: Must be called from subclass implementations.

        """
        self.started.emit()

    def end(self):
        # type: () -> None
        """
        Finish the interaction. Restore any leftover state in this method.

        .. note:: This gets called from the default :func:`cancel`
                  implementation.

        """
        self.__finished = True

        if self.scene.user_interaction_handler is self:
            self.scene.set_user_interaction_handler(None)

        if self.__canceled:
            self.canceled.emit()
            self.canceled[int].emit(self.__cancelReason)
        else:
            self.finished.emit()

        self.ended.emit()

        if self.deleteOnEnd:
            self.deleteLater()

    def cancel(self, reason=OtherReason):
        # type: (int) -> None
        """
        Cancel the interaction with `reason`.
        """

        self.__canceled = True
        self.__cancelReason = reason

        self.end()

    def isFinished(self):
        # type: () -> bool
        """
        Is the interaction finished.
        """
        return self.__finished

    def isCanceled(self):
        # type: () -> bool
        """
        Was the interaction canceled.
        """
        return self.__canceled

    def cancelReason(self):
        # type: () -> int
        """
        Return the reason the interaction was canceled.
        """
        return self.__cancelReason

    def mousePressEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        """
        Handle a `QGraphicsScene.mousePressEvent`.
        """
        return False

    def mouseMoveEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        """
        Handle a `GraphicsScene.mouseMoveEvent`.
        """
        return False

    def mouseReleaseEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        """
        Handle a `QGraphicsScene.mouseReleaseEvent`.
        """
        return False

    def mouseDoubleClickEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        """
        Handle a `QGraphicsScene.mouseDoubleClickEvent`.
        """
        return False

    def keyPressEvent(self, event):
        # type: (QKeyEvent) -> bool
        """
        Handle a `QGraphicsScene.keyPressEvent`
        """
        if self.cancelOnEsc and event.key() == Qt.Key_Escape:
            self.cancel(self.UserCancelReason)
        return False

    def keyReleaseEvent(self, event):
        # type: (QKeyEvent) -> bool
        """
        Handle a `QGraphicsScene.keyPressEvent`
        """
        return False

    def contextMenuEvent(self, event):
        # type: (QGraphicsSceneContextMenuEvent) -> bool
        """
        Handle a `QGraphicsScene.contextMenuEvent`
        """
        return False


class NoPossibleLinksError(ValueError):
    pass


class UserCanceledError(ValueError):
    pass


def reversed_arguments(func):
    """
    Return a function with reversed argument order.
    """
    def wrapped(*args):
        return func(*reversed(args))
    return wrapped


class NewLinkAction(UserInteraction):
    """
    User drags a new link from an existing `NodeAnchorItem` to create
    a connection between two existing nodes or to a new node if the release
    is over an empty area, in which case a quick menu for new node selection
    is presented to the user.

    """
    # direction of the drag
    FROM_SOURCE = 1
    FROM_SINK = 2

    def __init__(self, document, *args, **kwargs):
        super().__init__(document, *args, **kwargs)
        self.from_item = None    # type: Optional[items.NodeItem]
        self.from_signal = None  # type: Optional[Union[InputSignal, OutputSignal]]
        self.direction = 0       # type: int
        self.showing_incompatible_widget = False  # type: bool

        # An `NodeItem` currently under the mouse as a possible
        # link drop target.
        self.current_target_item = None  # type: Optional[items.NodeItem]
        # A temporary `LinkItem` used while dragging.
        self.tmp_link_item = None        # type: Optional[items.LinkItem]
        # An temporary `AnchorPoint` inserted into `current_target_item`
        self.tmp_anchor_point = None     # type: Optional[items.AnchorPoint]
        # An `AnchorPoint` following the mouse cursor
        self.cursor_anchor_point = None  # type: Optional[items.AnchorPoint]
        # An UndoCommand
        self.macro = None  # type: Optional[UndoCommand]

        # Cache viable signals of currently hovered node
        self.__target_compatible_signals = None

        self.cancelOnEsc = True

    def remove_tmp_anchor(self):
        # type: () -> None
        """
        Remove a temporary anchor point from the current target item.
        """
        assert self.current_target_item is not None
        assert self.tmp_anchor_point is not None
        if self.direction == self.FROM_SOURCE:
            self.current_target_item.removeInputAnchor(self.tmp_anchor_point)
        else:
            self.current_target_item.removeOutputAnchor(self.tmp_anchor_point)
        self.tmp_anchor_point = None

    def update_tmp_anchor(self, item, scenePos):
        # type: (items.NodeItem, QPointF) -> None
        """
        If hovering over a new compatible channel, move it.
        """
        assert self.tmp_anchor_point is not None
        if self.direction == self.FROM_SOURCE:
            signal = item.inputAnchorItem.signalAtPos(scenePos,
                                                      self.__target_compatible_signals)
        else:
            signal = item.outputAnchorItem.signalAtPos(scenePos,
                                                       self.__target_compatible_signals)
        self.tmp_anchor_point.setSignal(signal)

    def create_tmp_anchor(self, item, scenePos, viableLinks=None):
        # type: (items.NodeItem, QPointF) -> None
        """
        Create a new tmp anchor at the `item` (:class:`NodeItem`).
        """
        assert self.tmp_anchor_point is None
        if self.direction == self.FROM_SOURCE:
            anchor = item.inputAnchorItem
            signal = anchor.signalAtPos(scenePos,
                                        self.__target_compatible_signals)
            self.tmp_anchor_point = item.newInputAnchor(signal)
        else:
            anchor = item.outputAnchorItem
            signal = anchor.signalAtPos(scenePos,
                                        self.__target_compatible_signals)
            self.tmp_anchor_point = item.newOutputAnchor(signal)

    def can_connect(self, target_item):
        # type: (items.NodeItem) -> bool
        """
        Is the connection between `self.from_item` (item where the drag
        started) and `target_item` possible.

        If possible, initialize the variables regarding the node.
        """
        if self.from_item is None:
            return False
        node1 = self.scene.node_for_item(self.from_item)
        node2 = self.scene.node_for_item(target_item)

        if self.direction == self.FROM_SOURCE:
            links = self.scheme.propose_links(node1, node2,
                                              source_signal=self.from_signal)
            self.__target_compatible_signals = [l[1] for l in links]
        else:
            links = self.scheme.propose_links(node2, node1,
                                              sink_signal=self.from_signal)
            self.__target_compatible_signals = [l[0] for l in links]

        return bool(links)

    def set_link_target_anchor(self, anchor):
        # type: (items.AnchorPoint) -> None
        """
        Set the temp line target anchor.
        """
        assert self.tmp_link_item is not None
        if self.direction == self.FROM_SOURCE:
            self.tmp_link_item.setSinkItem(None, anchor=anchor)
        else:
            self.tmp_link_item.setSourceItem(None, anchor=anchor)

    def target_node_item_at(self, pos):
        # type: (QPointF) -> Optional[items.NodeItem]
        """
        Return a suitable :class:`NodeItem` at position `pos` on which
        a link can be dropped.
        """
        # Test for a suitable `NodeAnchorItem` or `NodeItem` at pos.
        if self.direction == self.FROM_SOURCE:
            anchor_type = items.SinkAnchorItem
        else:
            anchor_type = items.SourceAnchorItem

        item = self.scene.item_at(pos, (anchor_type, items.NodeItem))

        if isinstance(item, anchor_type):
            return item.parentNodeItem()
        elif isinstance(item, items.NodeItem):
            return item
        else:
            return None

    def mousePressEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        anchor_item = self.scene.item_at(
            event.scenePos(), items.NodeAnchorItem
        )
        if anchor_item is not None and event.button() == Qt.LeftButton:
            # Start a new link starting at item
            self.from_item = anchor_item.parentNodeItem()
            if isinstance(anchor_item, items.SourceAnchorItem):
                self.direction = NewLinkAction.FROM_SOURCE
            else:
                self.direction = NewLinkAction.FROM_SINK

            event.accept()

            helpevent = QuickHelpTipEvent(
                self.tr("Create a new link"),
                self.tr('<h3>Create new link</h3>'
                        '<p>Drag a link to an existing node or release on '
                        'an empty spot to create a new node.</p>'
                        '<p>Hold Shift when releasing the mouse button to '
                        'edit connections.</p>'
#                        '<a href="help://orange-canvas/create-new-links">'
#                        'More ...</a>'
                        )
            )
            QCoreApplication.postEvent(self.document, helpevent)
            return True
        else:
            # Whoever put us in charge did not know what he was doing.
            self.cancel(self.ErrorReason)
            return False

    def mouseMoveEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        if self.tmp_link_item is None:
            # On first mouse move event create the temp link item and
            # initialize it to follow the `cursor_anchor_point`.
            self.tmp_link_item = items.LinkItem()
            # An anchor under the cursor for the duration of this action.
            self.cursor_anchor_point = items.AnchorPoint()
            self.cursor_anchor_point.setPos(event.scenePos())

            # Set the `fixed` end of the temp link (where the drag started).
            scenePos = event.scenePos()

            if self.direction == self.FROM_SOURCE:
                anchor = self.from_item.outputAnchorItem
            else:
                anchor = self.from_item.inputAnchorItem
            anchor.setHovered(False)
            anchor.setCompatibleSignals(None)

            if anchor.anchorOpen():
                signal = anchor.signalAtPos(scenePos)
                anchor.setKeepAnchorOpen(signal)
            else:
                signal = None
            self.from_signal = signal

            if self.direction == self.FROM_SOURCE:
                self.tmp_link_item.setSourceItem(self.from_item, signal)
            else:
                self.tmp_link_item.setSinkItem(self.from_item, signal)

            self.set_link_target_anchor(self.cursor_anchor_point)
            self.scene.addItem(self.tmp_link_item)

        assert self.cursor_anchor_point is not None

        # `NodeItem` at the cursor position
        item = self.target_node_item_at(event.scenePos())

        if self.current_target_item is not None and \
                (item is None or item is not self.current_target_item):
            # `current_target_item` is no longer under the mouse cursor
            # (was replaced by another item or the the cursor was moved over
            # an empty scene spot.
            log.info("%r is no longer the target.", self.current_target_item)
            if self.direction == self.FROM_SOURCE:
                anchor = self.current_target_item.inputAnchorItem
            else:
                anchor = self.current_target_item.outputAnchorItem
            if not self.showing_incompatible_widget:
                self.remove_tmp_anchor()
                self.showing_incompatible_widget = True
            else:
                anchor.setIncompatible(False)
            anchor.setHovered(False)
            anchor.setCompatibleSignals(None)
            self.current_target_item = None

        if item is not None and item is not self.from_item:
            # The mouse is over a node item (different from the starting node)
            if self.current_target_item is item:
                # Mouse is over the same item
                scenePos = event.scenePos()
                # Move to new potential anchor
                if not self.showing_incompatible_widget:
                    self.update_tmp_anchor(item, scenePos)
                else:
                    self.set_link_target_anchor(self.cursor_anchor_point)
            elif self.can_connect(item):
                # Mouse is over a new item
                log.info("%r is the new target.", item)
                if self.direction == self.FROM_SOURCE:
                    item.inputAnchorItem.setCompatibleSignals(
                        self.__target_compatible_signals)
                    item.inputAnchorItem.setHovered(True)
                else:
                    item.outputAnchorItem.setCompatibleSignals(
                        self.__target_compatible_signals)
                    item.outputAnchorItem.setHovered(True)
                scenePos = event.scenePos()
                self.create_tmp_anchor(item, scenePos)
                self.set_link_target_anchor(
                    assert_not_none(self.tmp_anchor_point)
                )
                self.current_target_item = item
                self.showing_incompatible_widget = False
            else:
                log.info("%r does not have compatible channels", item)
                self.__target_compatible_signals = []
                if self.direction == self.FROM_SOURCE:
                    anchor = item.inputAnchorItem
                else:
                    anchor = item.outputAnchorItem
                anchor.setCompatibleSignals(
                    self.__target_compatible_signals)
                anchor.setHovered(True)
                anchor.setIncompatible(True)
                self.showing_incompatible_widget = True
                self.set_link_target_anchor(self.cursor_anchor_point)
                self.current_target_item = item
        else:
            self.set_link_target_anchor(self.cursor_anchor_point)

        self.cursor_anchor_point.setPos(event.scenePos())

        return True

    def mouseReleaseEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        if self.tmp_link_item is not None:
            item = self.target_node_item_at(event.scenePos())
            node = None  # type: Optional[Node]
            stack = self.document.undoStack()

            self.macro = UndoCommand(self.tr("Add link"))

            if item:
                # If the release was over a node item then connect them
                node = self.scene.node_for_item(item)
            else:
                # Release on an empty canvas part
                # Show a quick menu popup for a new widget creation.
                try:
                    node = self.create_new(event)
                except Exception:
                    log.error("Failed to create a new node, ending.",
                              exc_info=True)
                    node = None

                if node is not None:
                    commands.AddNodeCommand(self.scheme, node,
                                            parent=self.macro)

            if node is not None and not self.showing_incompatible_widget:
                if self.direction == self.FROM_SOURCE:
                    source_node = self.scene.node_for_item(self.from_item)
                    source_signal = self.from_signal
                    sink_node = node
                    if item is not None and item.inputAnchorItem.anchorOpen():
                        sink_signal = item.inputAnchorItem.signalAtPos(
                            event.scenePos(),
                            self.__target_compatible_signals
                        )
                    else:
                        sink_signal = None
                else:
                    source_node = node
                    if item is not None and item.outputAnchorItem.anchorOpen():
                        source_signal = item.outputAnchorItem.signalAtPos(
                            event.scenePos(),
                            self.__target_compatible_signals
                        )
                    else:
                        source_signal = None
                    sink_node = self.scene.node_for_item(self.from_item)
                    sink_signal = self.from_signal
                self.suggestions.set_direction(self.direction)
                self.connect_nodes(source_node, sink_node,
                                   source_signal, sink_signal)

                if not self.isCanceled() or not self.isFinished() and \
                        self.macro is not None:
                    # Push (commit) the add link/node action on the stack.
                    stack.push(self.macro)

            self.end()
            return True
        else:
            self.end()
            return False

    def create_new(self, event):
        # type: (QGraphicsSceneMouseEvent) -> Optional[Node]
        """
        Create and return a new node with a `QuickMenu`.
        """
        pos = event.screenPos()
        menu = self.document.quickMenu()
        node = self.scene.node_for_item(self.from_item)
        from_signal = self.from_signal
        from_desc = node.description

        def is_compatible(
                source_signal: OutputSignal,
                source: WidgetDescription,
                sink: WidgetDescription,
                sink_signal: InputSignal
        ) -> bool:
            return any(scheme.compatible_channels(output, input)
                       for output
                       in ([source_signal] if source_signal else source.outputs)
                       for input
                       in ([sink_signal] if sink_signal else sink.inputs))

        from_sink = self.direction == self.FROM_SINK
        if from_sink:
            # Reverse the argument order.
            is_compatible = reversed_arguments(is_compatible)
            suggestion_sort = self.suggestions.get_source_suggestions(from_desc.name)
        else:
            suggestion_sort = self.suggestions.get_sink_suggestions(from_desc.name)

        def sort(left, right):
            # list stores frequencies, so sign is flipped
            return suggestion_sort[left] > suggestion_sort[right]

        menu.setSortingFunc(sort)

        def filter(index):
            desc = index.data(QtWidgetRegistry.WIDGET_DESC_ROLE)
            if isinstance(desc, WidgetDescription):
                return is_compatible(from_signal, from_desc, desc, None)
            else:
                return False

        menu.setFilterFunc(filter)
        menu.triggerSearch()
        try:
            action = menu.exec_(pos)
        finally:
            menu.setFilterFunc(None)

        if action:
            item = action.property("item")
            desc = item.data(QtWidgetRegistry.WIDGET_DESC_ROLE)
            pos = event.scenePos()
            # a new widget should be placed so that the connection
            # stays as it was
            offset = 31 * (-1 if self.direction == self.FROM_SINK else
                           1 if self.direction == self.FROM_SOURCE else 0)
            statistics = self.document.usageStatistics()
            statistics.begin_extend_action(from_sink, node)
            node = self.document.newNodeHelper(desc,
                                               position=(pos.x() + offset,
                                                         pos.y()))
            return node
        else:
            return None

    def connect_nodes(
            self, source_node: Node, sink_node: Node,
            source_signal: Optional[OutputSignal] = None,
            sink_signal: Optional[InputSignal] = None
    ) -> None:
        """
        Connect `source_node` to `sink_node`. If there are more then one
        equally weighted and non conflicting links possible present a
        detailed dialog for link editing.

        """
        UsageStatistics.set_sink_anchor_open(sink_signal is not None)
        UsageStatistics.set_source_anchor_open(source_signal is not None)
        try:
            possible = self.scheme.propose_links(source_node, sink_node,
                                                 source_signal, sink_signal)

            log.debug("proposed (weighted) links: %r",
                      [(s1.name, s2.name, w) for s1, s2, w in possible])

            if not possible:
                raise NoPossibleLinksError

            source, sink, w = possible[0]

            # just a list of signal tuples for now, will be converted
            # to SchemeLinks later
            links_to_add = []     # type: List[Link]
            links_to_remove = []  # type: List[Link]
            show_link_dialog = False

            # Ambiguous new link request.
            if len(possible) >= 2:
                # Check for possible ties in the proposed link weights
                _, _, w2 = possible[1]
                if w == w2:
                    show_link_dialog = True

                # Check for destructive action (i.e. would the new link
                # replace a previous link)
                if sink.single and self.scheme.find_links(sink_node=sink_node,
                                                          sink_channel=sink):
                    show_link_dialog = True

            if show_link_dialog:
                existing = self.scheme.find_links(source_node=source_node,
                                                  sink_node=sink_node)

                if existing:
                    # edit_links will populate the view with existing links
                    initial_links = None
                else:
                    initial_links = [(source, sink)]

                try:
                    rstatus, links_to_add, links_to_remove = self.edit_links(
                        source_node, sink_node, initial_links
                    )
                except Exception:
                    log.error("Failed to edit the links",
                              exc_info=True)
                    raise
                if rstatus == EditLinksDialog.Rejected:
                    raise UserCanceledError
            else:
                # links_to_add now needs to be a list of actual SchemeLinks
                links_to_add = [
                    scheme.SchemeLink(source_node, source, sink_node, sink)
                ]
                links_to_add, links_to_remove = \
                    add_links_plan(self.scheme, links_to_add)

            # Remove temp items before creating any new links
            self.cleanup()

            for link in links_to_remove:
                commands.RemoveLinkCommand(self.scheme, link,
                                           parent=self.macro)

            for link in links_to_add:
                # Check if the new requested link is a duplicate of an
                # existing link
                duplicate = self.scheme.find_links(
                    link.source_node, link.source_channel,
                    link.sink_node, link.sink_channel
                )

                if not duplicate:
                    commands.AddLinkCommand(self.scheme, link,
                                            parent=self.macro)

        except scheme.IncompatibleChannelTypeError:
            log.info("Cannot connect: invalid channel types.")
            self.cancel()
        except scheme.SchemeTopologyError:
            log.info("Cannot connect: connection creates a cycle.")
            self.cancel()
        except NoPossibleLinksError:
            log.info("Cannot connect: no possible links.")
            self.cancel()
        except UserCanceledError:
            log.info("User canceled a new link action.")
            self.cancel(UserInteraction.UserCancelReason)
        except Exception:
            log.error("An error occurred during the creation of a new link.",
                      exc_info=True)
            self.cancel()

    def edit_links(
            self,
            source_node: Node,
            sink_node: Node,
            initial_links: 'Optional[List[OIPair]]' = None
    ) -> 'Tuple[int, List[Link], List[Link]]':
        """
        Show and execute the `EditLinksDialog`.
        Optional `initial_links` list can provide a list of initial
        `(source, sink)` channel tuples to show in the view, otherwise
        the dialog is populated with existing links in the scheme (passing
        an empty list will disable all initial links).

        """
        status, links_to_add_spec, links_to_remove_spec = \
            edit_links(
                self.scheme, source_node, sink_node, initial_links,
                parent=self.document
            )

        if status == EditLinksDialog.Accepted:
            links_to_add = [
                scheme.SchemeLink(
                    source_node, source_channel,
                    sink_node, sink_channel
                ) for source_channel, sink_channel in links_to_add_spec
            ]
            links_to_remove = list(reduce(
                list.__iadd__, (
                    self.scheme.find_links(
                        source_node, source_channel,
                        sink_node, sink_channel
                    ) for source_channel, sink_channel in links_to_remove_spec
                ),
                []
            ))  # type: List[Link]
            conflicting = [conflicting_single_link(self.scheme, link)
                           for link in links_to_add]
            conflicting = [link for link in conflicting if link is not None]
            for link in conflicting:
                if link not in links_to_remove:
                    links_to_remove.append(link)

            return status, links_to_add, links_to_remove
        else:
            return status, [], []

    def end(self):
        # type: () -> None
        self.cleanup()
        self.reset_open_anchor()
        # Remove the help tip set in mousePressEvent
        self.macro = None
        helpevent = QuickHelpTipEvent("", "")
        QCoreApplication.postEvent(self.document, helpevent)
        super().end()

    def cancel(self, reason=UserInteraction.OtherReason):
        # type: (int) -> None
        self.cleanup()
        self.reset_open_anchor()
        super().cancel(reason)

    def cleanup(self):
        # type: () -> None
        """
        Cleanup all temporary items in the scene that are left.
        """
        if self.tmp_link_item:
            self.tmp_link_item.setSinkItem(None)
            self.tmp_link_item.setSourceItem(None)

            if self.tmp_link_item.scene():
                self.scene.removeItem(self.tmp_link_item)

            self.tmp_link_item = None

        if self.current_target_item:
            if not self.showing_incompatible_widget:
                self.remove_tmp_anchor()
            else:
                if self.direction == self.FROM_SOURCE:
                    anchor = self.current_target_item.inputAnchorItem
                else:
                    anchor = self.current_target_item.outputAnchorItem
                anchor.setIncompatible(False)

            self.current_target_item = None

        if self.cursor_anchor_point and self.cursor_anchor_point.scene():
            self.scene.removeItem(self.cursor_anchor_point)
            self.cursor_anchor_point = None

    def reset_open_anchor(self):
        """
        This isn't part of cleanup, because it should retain its value
        until the link is created.
        """
        if self.direction == self.FROM_SOURCE:
            anchor = self.from_item.outputAnchorItem
        else:
            anchor = self.from_item.inputAnchorItem
        anchor.setKeepAnchorOpen(None)


def edit_links(
        scheme: Scheme,
        source_node: Node,
        sink_node: Node,
        initial_links: 'Optional[List[OIPair]]' = None,
        parent: 'Optional[QWidget]' = None
) -> 'Tuple[int, List[OIPair], List[OIPair]]':
    """
    Show and execute the `EditLinksDialog`.
    Optional `initial_links` list can provide a list of initial
    `(source, sink)` channel tuples to show in the view, otherwise
    the dialog is populated with existing links in the scheme (passing
    an empty list will disable all initial links).

    """
    log.info("Constructing a Link Editor dialog.")

    dlg = EditLinksDialog(parent, windowTitle="Edit Links")

    # all SchemeLinks between the two nodes.
    links = scheme.find_links(source_node=source_node, sink_node=sink_node)
    existing_links = [(link.source_channel, link.sink_channel)
                      for link in links]

    if initial_links is None:
        initial_links = list(existing_links)

    dlg.setNodes(source_node, sink_node)
    dlg.setLinks(initial_links)

    log.info("Executing a Link Editor Dialog.")
    rval = dlg.exec_()

    if rval == EditLinksDialog.Accepted:
        edited_links = dlg.links()

        # Differences
        links_to_add = set(edited_links) - set(existing_links)
        links_to_remove = set(existing_links) - set(edited_links)
        return rval, list(links_to_add), list(links_to_remove)
    else:
        return rval, [], []


def add_links_plan(scheme, links, force_replace=False):
    # type: (Scheme, Iterable[Link], bool) -> Tuple[List[Link], List[Link]]
    """
    Return a plan for adding a list of links to the scheme.
    """
    links_to_add = list(links)
    links_to_remove = [conflicting_single_link(scheme, link)
                       for link in links]
    links_to_remove = [link for link in links_to_remove if link is not None]

    if not force_replace:
        links_to_add, links_to_remove = remove_duplicates(links_to_add,
                                                          links_to_remove)
    return links_to_add, links_to_remove


def conflicting_single_link(scheme, link):
    # type: (Scheme, Link) -> Optional[Link]
    """
    Find and return an existing link in `scheme` connected to the same
    input channel as `link` if the channel has the 'single' flag.
    If no such channel exists (or sink channel is not 'single')
    return `None`.
    """
    if link.sink_channel.single:
        existing = scheme.find_links(
            sink_node=link.sink_node,
            sink_channel=link.sink_channel
        )

        if existing:
            assert len(existing) == 1
            return existing[0]
    return None


def remove_duplicates(links_to_add, links_to_remove):
    # type: (List[Link], List[Link]) -> Tuple[List[Link], List[Link]]
    def link_key(link):
        # type: (Link) -> Tuple[Node, OutputSignal, Node, InputSignal]
        return (link.source_node, link.source_channel,
                link.sink_node, link.sink_channel)

    add_keys = list(map(link_key, links_to_add))
    remove_keys = list(map(link_key, links_to_remove))
    duplicate_keys = set(add_keys).intersection(remove_keys)

    def not_duplicate(link):
        # type: (Link) -> bool
        return link_key(link) not in duplicate_keys

    links_to_add = list(filter(not_duplicate, links_to_add))
    links_to_remove = list(filter(not_duplicate, links_to_remove))
    return links_to_add, links_to_remove


class NewNodeAction(UserInteraction):
    """
    Present the user with a quick menu for node selection and
    create the selected node.
    """
    def mousePressEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        if event.button() == Qt.RightButton:
            self.create_new(event.screenPos())
            self.end()
        return True

    def create_new(self, pos, search_text=""):
        # type: (QPoint, str) -> Optional[Node]
        """
        Create and add new node to the workflow using `QuickMenu` popup at
        `pos` (in screen coordinates).
        """
        menu = self.document.quickMenu()
        menu.setFilterFunc(None)

        # compares probability of the user needing the widget as a source
        def defaultSort(left, right):
            default_suggestions = self.suggestions.get_default_suggestions()
            left_frequency = sum(default_suggestions[left].values())
            right_frequency = sum(default_suggestions[right].values())
            return left_frequency > right_frequency

        menu.setSortingFunc(defaultSort)

        action = menu.exec_(pos, search_text)
        if action:
            item = action.property("item")
            desc = item.data(QtWidgetRegistry.WIDGET_DESC_ROLE)
            # Get the scene position
            view = self.document.view()
            pos = view.mapToScene(view.mapFromGlobal(pos))

            statistics = self.document.usageStatistics()
            statistics.begin_action(UsageStatistics.QuickMenu)
            node = self.document.newNodeHelper(desc,
                                               position=(pos.x(), pos.y()))
            self.document.addNode(node)
            return node
        else:
            return None


class RectangleSelectionAction(UserInteraction):
    """
    Select items in the scene using a Rectangle selection
    """
    def __init__(self, document, *args, **kwargs):
        # type: (SchemeEditWidget, Any, Any) -> None
        super().__init__(document, *args, **kwargs)
        # The initial selection at drag start
        self.initial_selection = None  # type: Optional[Set[QGraphicsItem]]
        # Selection when last updated in a mouseMoveEvent
        self.last_selection = None     # type: Optional[Set[QGraphicsItem]]
        # A selection rect (`QRectF`)
        self.selection_rect = None     # type: Optional[QRectF]
        # Keyboard modifiers
        self.modifiers = Qt.NoModifier
        self.rect_item = None          # type: Optional[QGraphicsRectItem]

    def mousePressEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        pos = event.scenePos()
        any_item = self.scene.item_at(pos)
        if not any_item and event.button() & Qt.LeftButton:
            self.modifiers = event.modifiers()
            self.selection_rect = QRectF(pos, QSizeF(0, 0))
            self.rect_item = QGraphicsRectItem(
                self.selection_rect.normalized()
            )

            self.rect_item.setPen(
                QPen(QBrush(QColor(51, 153, 255, 192)),
                     0.4, Qt.SolidLine, Qt.RoundCap)
            )

            self.rect_item.setBrush(
                QBrush(QColor(168, 202, 236, 192))
            )

            self.rect_item.setZValue(-100)

            # Clear the focus if necessary.
            if not self.scene.stickyFocus():
                self.scene.clearFocus()

            if not self.modifiers & Qt.ControlModifier:
                self.scene.clearSelection()

            event.accept()
            return True
        else:
            self.cancel(self.ErrorReason)
            return False

    def mouseMoveEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        if self.rect_item is not None and not self.rect_item.scene():
            # Add the rect item to the scene when the mouse moves.
            self.scene.addItem(self.rect_item)
        self.update_selection(event)
        return True

    def mouseReleaseEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        if event.button() == Qt.LeftButton:
            if self.initial_selection is None:
                # A single click.
                self.scene.clearSelection()
            else:
                self.update_selection(event)
        self.end()
        return True

    def update_selection(self, event):
        # type: (QGraphicsSceneMouseEvent) -> None
        """
        Update the selection rectangle from a QGraphicsSceneMouseEvent
        `event` instance.
        """
        if self.initial_selection is None:
            self.initial_selection = set(self.scene.selectedItems())
            self.last_selection = self.initial_selection

        assert self.selection_rect is not None
        assert self.rect_item is not None
        assert self.initial_selection is not None
        assert self.last_selection is not None

        pos = event.scenePos()
        self.selection_rect = QRectF(self.selection_rect.topLeft(), pos)

        # Make sure the rect_item does not cause the scene rect to grow.
        rect = self._bound_selection_rect(self.selection_rect.normalized())

        # Need that 0.5 constant otherwise the sceneRect will still
        # grow (anti-aliasing correction by QGraphicsScene?)
        pw = self.rect_item.pen().width() + 0.5

        self.rect_item.setRect(rect.adjusted(pw, pw, -pw, -pw))

        selected = self.scene.items(self.selection_rect.normalized(),
                                    Qt.IntersectsItemShape,
                                    Qt.AscendingOrder)

        selected = set([item for item in selected if \
                        item.flags() & Qt.ItemIsSelectable])

        if self.modifiers & Qt.ControlModifier:
            for item in selected | self.last_selection | \
                    self.initial_selection:
                item.setSelected(
                    (item in selected) ^ (item in self.initial_selection)
                )
        else:
            for item in selected.union(self.last_selection):
                item.setSelected(item in selected)

        self.last_selection = set(self.scene.selectedItems())

    def end(self):
        # type: () -> None
        self.initial_selection = None
        self.last_selection = None
        self.modifiers = Qt.NoModifier
        if self.rect_item is not None:
            self.rect_item.hide()
            if self.rect_item.scene() is not None:
                self.scene.removeItem(self.rect_item)
        super().end()

    def viewport_rect(self):
        # type: () -> QRectF
        """
        Return the bounding rect of the document's viewport on the scene.
        """
        view = self.document.view()
        vsize = view.viewport().size()
        viewportrect = QRect(0, 0, vsize.width(), vsize.height())
        return view.mapToScene(viewportrect).boundingRect()

    def _bound_selection_rect(self, rect):
        # type: (QRectF) -> QRectF
        """
        Bound the selection `rect` to a sensible size.
        """
        srect = self.scene.sceneRect()
        vrect = self.viewport_rect()
        maxrect = srect.united(vrect)
        return rect.intersected(maxrect)


class EditNodeLinksAction(UserInteraction):
    """
    Edit multiple links between two :class:`SchemeNode` instances using
    a :class:`EditLinksDialog`

    Parameters
    ----------
    document : :class:`SchemeEditWidget`
        The editor widget.
    source_node : :class:`SchemeNode`
        The source (link start) node for the link editor.
    sink_node : :class:`SchemeNode`
        The sink (link end) node for the link editor.

    """
    def __init__(self, document, source_node, sink_node, *args, **kwargs):
        # type: (SchemeEditWidget, Node, Node, Any, Any) -> None
        super().__init__(document, *args, **kwargs)
        self.source_node = source_node
        self.sink_node = sink_node

    def edit_links(self, initial_links=None):
        # type: (Optional[List[OIPair]]) -> None
        """
        Show and execute the `EditLinksDialog`.
        Optional `initial_links` list can provide a list of initial
        `(source, sink)` channel tuples to show in the view, otherwise
        the dialog is populated with existing links in the scheme (passing
        an empty list will disable all initial links).

        """
        log.info("Constructing a Link Editor dialog.")

        dlg = EditLinksDialog(self.document, windowTitle="Edit Links")

        links = self.scheme.find_links(source_node=self.source_node,
                                       sink_node=self.sink_node)
        existing_links = [(link.source_channel, link.sink_channel)
                          for link in links]

        if initial_links is None:
            initial_links = list(existing_links)

        dlg.setNodes(self.source_node, self.sink_node)
        dlg.setLinks(initial_links)

        log.info("Executing a Link Editor Dialog.")
        rval = dlg.exec_()

        if rval == EditLinksDialog.Accepted:
            links_spec = dlg.links()

            links_to_add = set(links_spec) - set(existing_links)
            links_to_remove = set(existing_links) - set(links_spec)

            stack = self.document.undoStack()
            stack.beginMacro("Edit Links")

            # First remove links into a 'Single' sink channel,
            # but only the ones that do not have self.source_node as
            # a source (they will be removed later from links_to_remove)
            for _, sink_channel in links_to_add:
                if sink_channel.single:
                    existing = self.scheme.find_links(
                        sink_node=self.sink_node,
                        sink_channel=sink_channel
                    )

                    existing = [link for link in existing
                                if link.source_node is not self.source_node]

                    if existing:
                        assert len(existing) == 1
                        self.document.removeLink(existing[0])

            for source_channel, sink_channel in links_to_remove:
                links = self.scheme.find_links(source_node=self.source_node,
                                               source_channel=source_channel,
                                               sink_node=self.sink_node,
                                               sink_channel=sink_channel)
                assert len(links) == 1
                self.document.removeLink(links[0])

            for source_channel, sink_channel in links_to_add:
                link = scheme.SchemeLink(self.source_node, source_channel,
                                         self.sink_node, sink_channel)

                self.document.addLink(link)

            stack.endMacro()


def point_to_tuple(point):
    # type: (QPointF) -> Tuple[float, float]
    """
    Convert a QPointF into a (x, y) tuple.
    """
    return (point.x(), point.y())


class NewArrowAnnotation(UserInteraction):
    """
    Create a new arrow annotation handler.
    """
    def __init__(self, document, *args, **kwargs):
        # type: (SchemeEditWidget, Any, Any) -> None
        super().__init__(document, *args, **kwargs)
        self.down_pos = None  # type: Optional[QPointF]
        self.arrow_item = None  # type: Optional[items.ArrowAnnotation]
        self.annotation = None  # type: Optional[scheme.SchemeArrowAnnotation]
        self.color = "red"
        self.cancelOnEsc = True

    def start(self):
        # type: () -> None
        self.document.view().setCursor(Qt.CrossCursor)

        helpevent = QuickHelpTipEvent(
            self.tr("Click and drag to create a new arrow"),
            self.tr('<h3>New arrow annotation</h3>'
                    '<p>Click and drag to create a new arrow annotation</p>'
#                    '<a href="help://orange-canvas/arrow-annotations>'
#                    'More ...</a>'
                    )
        )
        QCoreApplication.postEvent(self.document, helpevent)

        super().start()

    def setColor(self, color):
        """
        Set the color for the new arrow.
        """
        self.color = color

    def mousePressEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        if event.button() == Qt.LeftButton:
            self.down_pos = event.scenePos()
            event.accept()
            return True
        else:
            return super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        if event.buttons() & Qt.LeftButton:
            assert self.down_pos is not None
            if self.arrow_item is None and \
                    (self.down_pos - event.scenePos()).manhattanLength() > \
                    QApplication.instance().startDragDistance():

                annot = scheme.SchemeArrowAnnotation(
                    point_to_tuple(self.down_pos),
                    point_to_tuple(event.scenePos())
                )
                annot.set_color(self.color)
                item = self.scene.add_annotation(annot)

                self.arrow_item = item
                self.annotation = annot

            if self.arrow_item is not None:
                p1, p2 = map(self.arrow_item.mapFromScene,
                             (self.down_pos, event.scenePos()))
                self.arrow_item.setLine(QLineF(p1, p2))

            event.accept()
            return True
        else:
            return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        if event.button() == Qt.LeftButton:
            if self.arrow_item is not None:
                assert self.down_pos is not None and self.annotation is not None
                p1, p2 = self.down_pos, event.scenePos()
                # Commit the annotation to the scheme
                self.annotation.set_line(point_to_tuple(p1),
                                         point_to_tuple(p2))

                self.document.addAnnotation(self.annotation)

                p1, p2 = map(self.arrow_item.mapFromScene, (p1, p2))
                self.arrow_item.setLine(QLineF(p1, p2))

            self.end()
            return True
        else:
            return super().mouseReleaseEvent(event)

    def cancel(self, reason=UserInteraction.OtherReason):  # type: (int) -> None
        if self.arrow_item is not None:
            self.scene.removeItem(self.arrow_item)
            self.arrow_item = None
        super().cancel(reason)

    def end(self):
        # type: () -> None
        self.down_pos = None
        self.arrow_item = None
        self.annotation = None
        self.document.view().setCursor(Qt.ArrowCursor)

        # Clear the help tip
        helpevent = QuickHelpTipEvent("", "")
        QCoreApplication.postEvent(self.document, helpevent)

        super().end()


def rect_to_tuple(rect):
    # type: (QRectF) -> Tuple[float, float, float, float]
    """
    Convert a QRectF into a (x, y, width, height) tuple.
    """
    return rect.x(), rect.y(), rect.width(), rect.height()


class NewTextAnnotation(UserInteraction):
    """
    A New Text Annotation interaction handler
    """
    def __init__(self, document, *args, **kwargs):
        # type: (SchemeEditWidget, Any, Any) -> None
        super().__init__(document, *args, **kwargs)
        self.down_pos = None  # type: Optional[QPointF]
        self.annotation_item = None  # type: Optional[items.TextAnnotation]
        self.annotation = None  # type: Optional[scheme.SchemeTextAnnotation]
        self.control = None  # type: Optional[controlpoints.ControlPointRect]
        self.font = document.font()  # type: QFont
        self.cancelOnEsc = True

    def setFont(self, font):
        # type: (QFont) -> None
        self.font = QFont(font)

    def start(self):
        # type: () -> None
        self.document.view().setCursor(Qt.CrossCursor)

        helpevent = QuickHelpTipEvent(
            self.tr("Click to create a new text annotation"),
            self.tr('<h3>New text annotation</h3>'
                    '<p>Click (and drag to resize) on the canvas to create '
                    'a new text annotation item.</p>'
#                    '<a href="help://orange-canvas/text-annotations">'
#                    'More ...</a>'
                    )
        )
        QCoreApplication.postEvent(self.document, helpevent)

        super().start()

    def createNewAnnotation(self, rect):
        # type: (QRectF) -> None
        """
        Create a new TextAnnotation at with `rect` as the geometry.
        """
        annot = scheme.SchemeTextAnnotation(rect_to_tuple(rect))
        font = {"family": self.font.family(),
                "size": self.font.pixelSize()}
        annot.set_font(font)

        item = self.scene.add_annotation(annot)
        item.setTextInteractionFlags(Qt.TextEditorInteraction)
        item.setFramePen(QPen(Qt.DashLine))

        self.annotation_item = item
        self.annotation = annot
        self.control = controlpoints.ControlPointRect()
        self.control.rectChanged.connect(item.setGeometry)
        self.scene.addItem(self.control)

    def mousePressEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        if event.button() == Qt.LeftButton:
            self.down_pos = event.scenePos()
            return True
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        if event.buttons() & Qt.LeftButton:
            assert self.down_pos is not None
            if self.annotation_item is None and \
                    (self.down_pos - event.scenePos()).manhattanLength() > \
                    QApplication.instance().startDragDistance():
                rect = QRectF(self.down_pos, event.scenePos()).normalized()
                self.createNewAnnotation(rect)

            if self.annotation_item is not None:
                assert self.control is not None
                rect = QRectF(self.down_pos, event.scenePos()).normalized()
                self.control.setRect(rect)
            return True
        return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        if event.button() == Qt.LeftButton:
            if self.annotation_item is None:
                self.createNewAnnotation(QRectF(event.scenePos(),
                                                event.scenePos()))
                rect = self.defaultTextGeometry(event.scenePos())
            else:
                assert self.down_pos is not None
                rect = QRectF(self.down_pos, event.scenePos()).normalized()
            assert self.annotation_item is not None
            assert self.control is not None
            assert self.annotation is not None
            # Commit the annotation to the scheme.
            self.annotation.rect = rect_to_tuple(rect)

            self.document.addAnnotation(self.annotation)

            self.annotation_item.setGeometry(rect)

            self.control.rectChanged.disconnect(
                self.annotation_item.setGeometry
            )
            self.control.hide()

            # Move the focus to the editor.
            self.annotation_item.setFramePen(QPen(Qt.NoPen))
            self.annotation_item.setFocus(Qt.OtherFocusReason)
            self.annotation_item.startEdit()

            self.end()
            return True
        return super().mouseMoveEvent(event)

    def defaultTextGeometry(self, point):
        # type: (QPointF) -> QRectF
        """
        Return the default text geometry. Used in case the user single
        clicked in the scene.
        """
        assert self.annotation_item is not None
        font = self.annotation_item.font()
        metrics = QFontMetrics(font)
        spacing = metrics.lineSpacing()
        margin = self.annotation_item.document().documentMargin()

        rect = QRectF(QPointF(point.x(), point.y() - spacing - margin),
                      QSizeF(150, spacing + 2 * margin))
        return rect

    def cancel(self, reason=UserInteraction.OtherReason):  # type: (int) -> None
        if self.annotation_item is not None:
            self.annotation_item.clearFocus()
            self.scene.removeItem(self.annotation_item)
            self.annotation_item = None
        super().cancel(reason)

    def end(self):
        # type: () -> None
        if self.control is not None:
            self.scene.removeItem(self.control)

        self.control = None
        self.down_pos = None
        self.annotation_item = None
        self.annotation = None
        self.document.view().setCursor(Qt.ArrowCursor)

        # Clear the help tip
        helpevent = QuickHelpTipEvent("", "")
        QCoreApplication.postEvent(self.document, helpevent)

        super().end()


class ResizeTextAnnotation(UserInteraction):
    """
    Resize a Text Annotation interaction handler.
    """
    def __init__(self, document, *args, **kwargs):
        # type: (SchemeEditWidget, Any, Any) -> None
        super().__init__(document, *args, **kwargs)
        self.item = None        # type: Optional[items.TextAnnotation]
        self.annotation = None  # type: Optional[scheme.SchemeTextAnnotation]
        self.control = None     # type: Optional[controlpoints.ControlPointRect]
        self.savedFramePen = None  # type: Optional[QPen]
        self.savedRect = None      # type: Optional[QRectF]

    def mousePressEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        pos = event.scenePos()
        if event.button() & Qt.LeftButton and self.item is None:
            item = self.scene.item_at(pos, items.TextAnnotation)
            if item is not None and not item.hasFocus():
                self.editItem(item)
                return False
        return super().mousePressEvent(event)

    def editItem(self, item):
        # type: (items.TextAnnotation) -> None
        annotation = self.scene.annotation_for_item(item)
        rect = item.geometry()  # TODO: map to scene if item has a parent.
        control = controlpoints.ControlPointRect(rect=rect)
        self.scene.addItem(control)

        self.savedFramePen = item.framePen()
        self.savedRect = rect

        control.rectEdited.connect(item.setGeometry)
        control.setFocusProxy(item)

        item.setFramePen(QPen(Qt.DashDotLine))
        item.geometryChanged.connect(self.__on_textGeometryChanged)

        self.item = item

        self.annotation = annotation
        self.control = control

    def commit(self):
        # type: () -> None
        """
        Commit the current item geometry state to the document.
        """
        if self.item is None:
            return
        rect = self.item.geometry()
        if self.savedRect != rect:
            command = commands.SetAttrCommand(
                self.annotation, "rect",
                (rect.x(), rect.y(), rect.width(), rect.height()),
                name="Edit text geometry"
            )
            self.document.undoStack().push(command)
            self.savedRect = rect

    def __on_editingFinished(self):
        # type: () -> None
        self.commit()
        self.end()

    def __on_rectEdited(self, rect):
        # type: (QRectF) -> None
        assert self.item is not None
        self.item.setGeometry(rect)

    def __on_textGeometryChanged(self):
        # type: () -> None
        assert self.control is not None and self.item is not None
        if not self.control.isControlActive():
            rect = self.item.geometry()
            self.control.setRect(rect)

    def cancel(self, reason=UserInteraction.OtherReason):
        # type: (int) -> None
        log.debug("ResizeTextAnnotation.cancel(%s)", reason)
        if self.item is not None and self.savedRect is not None:
            self.item.setGeometry(self.savedRect)
        super().cancel(reason)

    def end(self):
        # type: () -> None
        if self.control is not None:
            self.scene.removeItem(self.control)

        if self.item is not None and self.savedFramePen is not None:
            self.item.setFramePen(self.savedFramePen)

        self.item = None
        self.annotation = None
        self.control = None

        super().end()


class ResizeArrowAnnotation(UserInteraction):
    """
    Resize an Arrow Annotation interaction handler.
    """
    def __init__(self, document, *args, **kwargs):
        # type: (SchemeEditWidget, Any, Any) -> None
        super().__init__(document, *args, **kwargs)
        self.item = None        # type: Optional[items.ArrowAnnotation]
        self.annotation = None  # type: Optional[scheme.SchemeArrowAnnotation]
        self.control = None     # type: Optional[controlpoints.ControlPointLine]
        self.savedLine = None   # type: Optional[QLineF]

    def mousePressEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        pos = event.scenePos()
        if self.item is None:
            item = self.scene.item_at(pos, items.ArrowAnnotation)
            if item is not None and not item.hasFocus():
                self.editItem(item)
                return False

        return super().mousePressEvent(event)

    def editItem(self, item):
        # type: (items.ArrowAnnotation) -> None
        annotation = self.scene.annotation_for_item(item)
        control = controlpoints.ControlPointLine()
        self.scene.addItem(control)

        line = item.line()
        self.savedLine = line

        p1, p2 = map(item.mapToScene, (line.p1(), line.p2()))

        control.setLine(QLineF(p1, p2))
        control.setFocusProxy(item)
        control.lineEdited.connect(self.__on_lineEdited)

        item.geometryChanged.connect(self.__on_lineGeometryChanged)

        self.item = item
        self.annotation = annotation
        self.control = control

    def commit(self):
        # type: () -> None
        """Commit the current geometry of the item to the document.

        Does nothing if the actual geometry has not changed.
        """
        if self.control is None or self.item is None:
            return
        line = self.control.line()
        p1, p2 = line.p1(), line.p2()

        if self.item.line() != self.savedLine:
            command = commands.SetAttrCommand(
                self.annotation,
                "geometry",
                ((p1.x(), p1.y()), (p2.x(), p2.y())),
                name="Edit arrow geometry",
            )
            self.document.undoStack().push(command)
            self.savedLine = self.item.line()

    def __on_editingFinished(self):
        # type: () -> None
        self.commit()
        self.end()

    def __on_lineEdited(self, line):
        # type: (QLineF) -> None
        if self.item is not None:
            p1, p2 = map(self.item.mapFromScene, (line.p1(), line.p2()))
            self.item.setLine(QLineF(p1, p2))

    def __on_lineGeometryChanged(self):
        # type: () -> None
        # Possible geometry change from out of our control, for instance
        # item move as a part of a selection group.
        assert self.control is not None and self.item is not None
        if not self.control.isControlActive():
            assert self.item is not None
            line = self.item.line()
            p1, p2 = map(self.item.mapToScene, (line.p1(), line.p2()))
            self.control.setLine(QLineF(p1, p2))

    def cancel(self, reason=UserInteraction.OtherReason):
        # type: (int) -> None
        log.debug("ResizeArrowAnnotation.cancel(%s)", reason)
        if self.item is not None and self.savedLine is not None:
            self.item.setLine(self.savedLine)

        super().cancel(reason)

    def end(self):
        # type: () -> None
        if self.control is not None:
            self.scene.removeItem(self.control)

        if self.item is not None:
            self.item.geometryChanged.disconnect(self.__on_lineGeometryChanged)

        self.control = None
        self.item = None
        self.annotation = None

        super().end()

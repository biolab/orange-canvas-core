import enum
import itertools
import logging
import sys
import traceback
from collections import deque
from xml.sax.saxutils import escape

from typing import Iterable, Dict, Deque, Optional, List, Tuple

from AnyQt.QtCore import Qt, QObject, QEvent, QTimer, QCoreApplication
from AnyQt.QtCore import Slot, Signal
from AnyQt.QtGui import QKeySequence
from AnyQt.QtWidgets import QWidget, QLabel, QShortcut, QAction

from orangecanvas.scheme import (
    SchemeNode, Scheme, NodeEvent, SchemeLink, LinkEvent
)
from orangecanvas.scheme.events import WorkflowEvent, WorkflowEnvChanged
from orangecanvas.scheme.node import UserMessage

log = logging.getLogger(__name__)

__all__ = ["WidgetManager"]


class Item:
    def __init__(self, node, widget, activation_order=-1, errorwidget=None):
        # type: (SchemeNode, Optional[QWidget], int, Optional[QWidget]) -> None
        self.node = node
        self.widget = widget
        self.activation_order = activation_order
        self.errorwidget = errorwidget


class WidgetManager(QObject):
    """
    WidgetManager class is responsible for creation, tracking and deletion
    of UI elements constituting an interactive workflow.

    It does so by reacting to changes in the underlying workflow model,
    creating and destroying the components when needed.

    This is an abstract class, subclassed MUST reimplement at least
    :func:`create_widget_for_node` and :func:`delete_widget_for_node`.

    The widgets created with :func:`create_widget_for_node` will automatically
    receive dispatched events:

        * :data:`WorkflowEvent.InputLinkAdded` - when a new input link is added to
          the workflow.
        * :data:`LinkEvent.InputLinkRemoved` - when a input link is removed
        * :data:`LinkEvent.OutputLinkAdded` - when a new output link is added to
          the workflow
        * :data:`LinkEvent.InputLinkRemoved` - when a output link is removed
        * :data:`WorkflowEnvEvent.WorkflowEnvironmentChanged` - when the
          workflow environment changes.

    .. seealso:: :func:`.Scheme.add_link()`, :func:`Scheme.remove_link`,
                 :func:`.Scheme.runtime_env`
    """
    #: A new QWidget was created and added by the manager.
    widget_for_node_added = Signal(SchemeNode, QWidget)

    #: A QWidget was removed, hidden and will be deleted when appropriate.
    widget_for_node_removed = Signal(SchemeNode, QWidget)

    class CreationPolicy(enum.Enum):
        """
        Widget Creation Policy.
        """
        #: Widgets are scheduled to be created from the event loop, or when
        #: first accessed with `widget_for_node`
        Normal = "Normal"
        #: Widgets are created immediately when a node is added to the
        #: workflow model.
        Immediate = "Immediate"
        #: Widgets are created only when first accessed with `widget_for_node`
        #: (e.g. when activated in the view).
        OnDemand = "OnDemand"

    Normal = CreationPolicy.Normal
    Immediate = CreationPolicy.Immediate
    OnDemand = CreationPolicy.OnDemand

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__workflow = None  # type: Optional[Scheme]
        self.__creation_policy = WidgetManager.Normal
        self.__float_widgets_on_top = False

        self.__item_for_node = {}  # type: Dict[SchemeNode, Item]
        self.__item_for_widget = {}  # type: Dict[QWidget, Item]

        self.__init_queue = deque()  # type: Deque[SchemeNode]

        self.__init_timer = QTimer(self, singleShot=True)
        self.__init_timer.timeout.connect(self.__process_init_queue)

        self.__activation_monitor = ActivationMonitor(self)
        self.__activation_counter = itertools.count()
        self.__activation_monitor.activated.connect(self.__mark_activated)

    def set_workflow(self, workflow):
        # type: (Scheme) -> None
        """
        Set the workflow.
        """
        if workflow is self.__workflow:
            return

        if self.__workflow is not None:
            # cleanup
            for node in self.__workflow.nodes:
                self.__remove_node(node)
            self.__workflow.node_added.disconnect(self.__on_node_added)
            self.__workflow.node_removed.disconnect(self.__on_node_removed)
            self.__workflow.link_added.disconnect(self.__on_link_added)
            self.__workflow.link_removed.disconnect(self.__on_link_removed)
            self.__workflow.runtime_env_changed.disconnect(self.__on_env_changed)
            self.__workflow.removeEventFilter(self)

        self.__workflow = workflow

        workflow.node_added.connect(
            self.__on_node_added, Qt.UniqueConnection)
        workflow.node_removed.connect(
            self.__on_node_removed, Qt.UniqueConnection)
        workflow.link_added.connect(
            self.__on_link_added, Qt.UniqueConnection)
        workflow.link_removed.connect(
            self.__on_link_removed, Qt.UniqueConnection)
        workflow.runtime_env_changed.connect(
            self.__on_env_changed, Qt.UniqueConnection)
        workflow.installEventFilter(self)
        for node in workflow.nodes:
            self.__add_node(node)

    def workflow(self):
        return self.__workflow

    scheme = workflow
    set_scheme = set_workflow

    def set_creation_policy(self, policy):
        # type: (CreationPolicy) -> None
        """
        Set the widget creation policy.
        """
        if self.__creation_policy != policy:
            self.__creation_policy = policy
            if self.__creation_policy == WidgetManager.Immediate:
                self.__init_timer.stop()
                # create all
                if self.__workflow is not None:
                    for node in self.__workflow.nodes:
                        self.ensure_created(node)
            elif self.__creation_policy == WidgetManager.Normal:
                if not self.__init_timer.isActive() and self.__init_queue:
                    self.__init_timer.start()
            elif self.__creation_policy == WidgetManager.OnDemand:
                self.__init_timer.stop()
            else:
                assert False

    def creation_policy(self):
        """
        Return the current widget creation policy.
        """
        return self.__creation_policy

    def create_widget_for_node(self, node):
        # type: (SchemeNode) -> QWidget
        """
        Create and initialize a widget for node.

        This is an abstract method. Subclasses must reimplemented it.
        """
        raise NotImplementedError()

    def delete_widget_for_node(self, node, widget):
        """
        Remove and delete widget for node.

        This is an abstract method. Subclasses must reimplemented it.
        """
        raise NotImplementedError()

    def node_for_widget(self, widget):
        # type: (QWidget) -> Optional[SchemeNode]
        """
        Return the node for widget.
        """
        item = self.__item_for_widget.get(widget)
        if item is not None:
            return item.node
        else:
            return None

    def widget_for_node(self, node):
        # type: (SchemeNode) -> Optional[QWidget]
        """
        Return the widget for node.
        """
        self.ensure_created(node)
        item = self.__item_for_node.get(node)
        return item.widget if item is not None else None

    def __add_widget_for_node(self, node):
        # type: (SchemeNode) -> None
        item = self.__item_for_node.get(node)
        if item is not None:
            return
        if node not in self.__workflow.nodes:
            return

        if node in self.__init_queue:
            self.__init_queue.remove(node)

        item = Item(node, None, -1)
        # Insert on the node -> item mapping.
        self.__item_for_node[node] = item
        log.debug("Creating widget for node %s", node)
        try:
            w = self.create_widget_for_node(node)
        except Exception:  # pylint: disable=broad-except
            log.critical("", exc_info=True)
            lines = traceback.format_exception(*sys.exc_info())
            text = "".join(lines)
            errorwidget = QLabel(
                textInteractionFlags=Qt.TextSelectableByMouse, wordWrap=True,
                objectName="widgetmanager-error-placeholder",
                text="<pre>" + escape(text) + "</pre>"
            )
            item.errorwidget = errorwidget
            node.set_state_message(UserMessage(text, UserMessage.Error, 0))
            raise
        else:
            item.widget = w
            self.__item_for_widget[w] = item

        self.__set_float_on_top_flag(w)

        w.installEventFilter(self.__activation_monitor)
        # Up shortcut (activate/open parent)
        up_shortcut = QShortcut(
            QKeySequence(Qt.ControlModifier + Qt.Key_Up), w)
        up_shortcut.activated.connect(self.__on_activate_parent)

        # send all the post creation notification events
        workflow = self.__workflow
        assert workflow is not None
        inputs = workflow.find_links(sink_node=node)
        for link in inputs:
            ev = LinkEvent(LinkEvent.InputLinkAdded, link)
            QCoreApplication.sendEvent(w, ev)
        outputs = workflow.find_links(source_node=node)
        for link in outputs:
            ev = LinkEvent(LinkEvent.OutputLinkAdded, link)
            QCoreApplication.sendEvent(w, ev)

        self.widget_for_node_added.emit(node, w)

    def ensure_created(self, node):
        # type: (SchemeNode) -> None
        """
        Ensure that the widget for node is created.
        """
        if node not in self.__workflow.nodes:
            return
        item = self.__item_for_node.get(node)
        if item is None:
            self.__add_widget_for_node(node)

    def __on_node_added(self, node):  # type: (SchemeNode) -> None
        assert self.__workflow is not None
        assert node in self.__workflow.nodes
        assert node not in self.__item_for_node
        self.__add_node(node)

    def __add_node(self, node): # type: (SchemeNode) -> None
        # add node for tracking
        node.installEventFilter(self)
        if self.__creation_policy == WidgetManager.Immediate:
            self.ensure_created(node)
        elif self.__creation_policy == WidgetManager.Normal:
            self.__init_queue.append(node)
            self.__init_timer.start()

    def __on_node_removed(self, node):  # type: (SchemeNode) -> None
        assert self.__workflow is not None
        assert node not in self.__workflow.nodes
        self.__remove_node(node)

    def __remove_node(self, node):  # type: (SchemeNode) -> None
        # remove the node and its widget from tracking.
        node.removeEventFilter(self)
        if node in self.__init_queue:
            self.__init_queue.remove(node)
        item = self.__item_for_node.get(node)

        if item is not None and item.widget is not None:
            widget = item.widget
            assert widget in self.__item_for_widget
            del self.__item_for_widget[widget]
            widget.removeEventFilter(self.__activation_monitor)
            item.widget = None
            self.widget_for_node_removed.emit(node, widget)
            self.delete_widget_for_node(node, widget)

        if item is not None:
            del self.__item_for_node[node]

    @Slot()
    def __process_init_queue(self):
        if self.__init_queue:
            node = self.__init_queue.popleft()
            assert node in self.__workflow.nodes
            log.debug("__process_init_queue: '%s'", node.title)
            try:
                self.ensure_created(node)
            finally:
                if self.__init_queue:
                    self.__init_timer.start()

    def __on_link_added(self, link):  # type: (SchemeLink) -> None
        assert link.source_node in self.__workflow.nodes
        assert link.sink_node in self.__workflow.nodes
        source = self.__item_for_node.get(link.source_node)
        sink = self.__item_for_node.get(link.sink_node)
        # notify the node gui of an added link
        if source is not None and source.widget is not None:
            ev = LinkEvent(LinkEvent.OutputLinkAdded, link)
            QCoreApplication.sendEvent(source.widget, ev)
        if sink is not None and sink.widget is not None:
            ev = LinkEvent(LinkEvent.InputLinkAdded, link)
            QCoreApplication.sendEvent(sink.widget, ev)

    def __on_link_removed(self, link):  # type: (SchemeLink) -> None
        assert link.source_node in self.__workflow.nodes
        assert link.sink_node in self.__workflow.nodes
        source = self.__item_for_node.get(link.source_node)
        sink = self.__item_for_node.get(link.sink_node)
        # notify the node gui of an removed link
        if source is not None and source.widget is not None:
            ev = LinkEvent(LinkEvent.OutputLinkRemoved, link)
            QCoreApplication.sendEvent(source.widget, ev)
        if sink is not None and sink.widget is not None:
            ev = LinkEvent(LinkEvent.InputLinkRemoved, link)
            QCoreApplication.sendEvent(sink.widget, ev)

    def __mark_activated(self, widget):  # type: (QWidget) ->  None
        # Update the tracked stacking order for `widget`
        item = self.__item_for_widget.get(widget)
        if item is not None:
            item.activation_order = next(self.__activation_counter)

    def activate_widget_for_node(self, node, widget):
        # type: (SchemeNode, QWidget) -> None
        """
        Activate the widget for node (show and raise above other)
        """
        if widget.windowState() == Qt.WindowMinimized:
            widget.showNormal()
        widget.setVisible(True)
        widget.raise_()
        widget.activateWindow()

    def activate_window_group(self, group):
        # type: (Scheme.WindowGroup) -> None
        self.restore_window_state(group.state)

    def raise_widgets_to_front(self):
        """
        Raise all current visible widgets to the front.

        The widgets will be stacked by activation order.
        """
        workflow = self.__workflow
        if workflow is None:
            return

        items = filter(
            lambda item: (
                item.widget.isVisible()
                if item is not None and item.widget is not None
                else False)
            ,
            map(self.__item_for_node.get, workflow.nodes))
        self.__raise_and_activate(items)

    def set_float_widgets_on_top(self, float_on_top):
        """
        Set `Float Widgets on Top` flag on all widgets.
        """
        self.__float_widgets_on_top = float_on_top
        for item in self.__item_for_node.values():
            if item.widget is not None:
                self.__set_float_on_top_flag(item.widget)

    def save_window_state(self):
        # type: () -> List[Tuple[SchemeNode, bytes]]
        """
        Save current open window arrangement.
        """
        workflow = self.__workflow  # type: Scheme
        state = []
        for node in workflow.nodes:  # type: SchemeNode
            item = self.__item_for_node.get(node, None)
            if item is None:
                continue
            stackorder = item.activation_order
            if item.widget is not None and not item.widget.isHidden():
                data = self.save_widget_geometry(node, item.widget)
                state.append((stackorder, node, data))

        state = [(node, data)
                 for _, node, data in sorted(state, key=lambda t: t[0])]
        return state

    def restore_window_state(self, state):
        # type: (List[Tuple[SchemeNode, bytes]]) -> None
        """
        Restore the window state.
        """
        workflow = self.__workflow  # type: Scheme
        visible = {node for node, _ in state}
        # first hide all other widgets
        for node in workflow.nodes:
            if node not in visible:
                # avoid creating widgets if not needed
                item = self.__item_for_node.get(node, None)
                if item is not None and item.widget is not None:
                    item.widget.hide()
        allnodes = set(workflow.nodes)
        # restore state for visible group; windows are stacked as they appear
        # in the state list.
        w = None
        for node, state in filter(lambda t: t[0] in allnodes, state):
            w = self.widget_for_node(node)  # also create it if needed
            if w is not None:
                w.show()
                self.restore_widget_geometry(node, w, state)
                w.raise_()
                self.__mark_activated(w)

        # activate (give focus to) the last window
        if w is not None:
            w.activateWindow()

    def save_widget_geometry(self, node, widget):
        # type: (SchemeNode, QWidget) -> bytes
        """
        Save and return the current geometry and state for node.
        """
        return b''

    def restore_widget_geometry(self, node, widget, state):
        # type: (SchemeNode, QWidget, bytes) -> bool
        """
        Restore the widget geometry and state for node.

        Return True if the geometry was restored successfully.

        The default implementation does nothing.
        """
        return False

    def __raise_and_activate(self, items):
        # type: (Iterable[Item]) -> None
        """Show and raise a set of widgets."""
        # preserve the tracked stacking order
        items = sorted(items, key=lambda item: item.activation_order)
        w = None
        for item in items:
            if item.widget is not None:
                w = item.widget
            elif item.errorwidget is not None:
                w = item.errorwidget
            else:
                continue
            w.show()
            w.raise_()
        if w is not None:
            # give focus to the last activated top window
            w.activateWindow()

    def __activate_widget_for_node(self, node):  # type: (SchemeNode) -> None
        # activate the widget for the node.
        self.ensure_created(node)
        item = self.__item_for_node.get(node)
        if item is None:
            return
        if item.widget is not None:
            self.activate_widget_for_node(node, item.widget)
        elif item.errorwidget is not None:
            item.errorwidget.show()
            item.errorwidget.raise_()
            item.errorwidget.activateWindow()

    def __on_activate_parent(self):
        event = WorkflowEvent(WorkflowEvent.ActivateParentRequest)
        QCoreApplication.sendEvent(self.scheme(), event)

    def eventFilter(self, recv, event):
        # type: (QObject, QEvent) -> bool
        if event.type() == NodeEvent.NodeActivateRequest \
                and isinstance(recv, SchemeNode):
            self.__activate_widget_for_node(recv)
        return False

    def __set_float_on_top_flag(self, widget):
        """Set or unset widget's float on top flag"""
        should_float_on_top = self.__float_widgets_on_top
        float_on_top = bool(widget.windowFlags() & Qt.WindowStaysOnTopHint)

        if float_on_top == should_float_on_top:
            return

        widget_was_visible = widget.isVisible()
        if should_float_on_top:
            widget.setWindowFlags(
                widget.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            widget.setWindowFlags(
                widget.windowFlags() & ~Qt.WindowStaysOnTopHint)

        # Changing window flags hid the widget
        if widget_was_visible:
            widget.show()

    def __on_env_changed(self, key, newvalue, oldvalue):
        # Notify widgets of a runtime environment change
        for item in self.__item_for_node.values():
            if item.widget is not None:
                ev = WorkflowEnvChanged(key, newvalue, oldvalue)
                QCoreApplication.sendEvent(item.widget, ev)

    def actions_for_context_menu(self, node):
        # type: (SchemeNode) -> List[QAction]
        """
        Return a list of extra actions that can be inserted into context
        menu in the workflow editor.

        Subclasses can reimplement this method to extend the default context
        menu.

        Parameters
        ----------
        node: SchemeNode
            The node for which the context menu is requested.

        Return
        ------
        actions: List[QAction]
            Actions that are appended to the default menu.
        """
        return []


# Utility class used to preserve window stacking order.
class ActivationMonitor(QObject):
    """
    An event filter for monitoring QWidgets for `WindowActivation` events.
    """
    #: Signal emitted with the `QWidget` instance that was activated.
    activated = Signal(QWidget)

    def eventFilter(self, obj, event):
        # type: (QObject, QEvent) -> bool
        if event.type() == QEvent.WindowActivate and isinstance(obj, QWidget):
            self.activated.emit(obj)
        return False

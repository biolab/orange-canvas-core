import enum
import itertools
import weakref
from functools import partial

import logging
import sys
import traceback
from collections import deque
from xml.sax.saxutils import escape

from typing import Iterable, Dict, Deque, Optional, List, Tuple

from AnyQt.QtCore import Qt, QObject, QEvent, QTimer, QCoreApplication
from AnyQt.QtCore import Slot, Signal
from AnyQt.QtGui import QKeySequence
from AnyQt.QtWidgets import QWidget, QLabel, QAction

from orangecanvas.scheme import SchemeNode, Scheme, NodeEvent, LinkEvent, Link, MetaNode
from orangecanvas.scheme.events import WorkflowEvent
from orangecanvas.scheme.node import UserMessage
from orangecanvas.gui.windowlistmanager import WindowListManager
from orangecanvas.utils.qinvoke import connect_with_context

log = logging.getLogger(__name__)

__all__ = ["WidgetManager"]

Workflow = Scheme
Node = SchemeNode


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

        * :attr:`.WorkflowEvent.InputLinkAdded` - when a new input link is
          added to the workflow.
        * :attr:`.WorkflowEvent.InputLinkRemoved` - when a input link is
          removed.
        * :attr:`.WorkflowEvent.OutputLinkAdded` - when a new output link is
          added to the workflow.
        * :attr:`.WorkflowEvent.OutputLinkRemoved` - when a output link is
          removed.
        * :attr:`.WorkflowEvent.InputLinkStateChange` - when the input link's
          runtime state changes.
        * :attr:`.WorkflowEvent.OutputLinkStateChange` - when the output link's
          runtime state changes.
        * :attr:`.WorkflowEvent.NodeStateChange` - when the node's runtime
          state changes.
        * :attr:`.WorkflowEvent.WorkflowEnvironmentChange` - when the
          workflow environment changes.

    .. seealso:: :func:`.Scheme.add_link()`, :func:`Scheme.remove_link`,
                 :func:`.Scheme.runtime_env`, :class:`NodeEvent`,
                 :class:`LinkEvent`
    """
    #: A new QWidget was created and added by the manager.
    widget_for_node_added = Signal(SchemeNode, QWidget)

    #: A QWidget was removed, hidden and will be deleted when appropriate.
    widget_for_node_removed = Signal(SchemeNode, QWidget)

    __init_queue = None  # type: Deque[SchemeNode]

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
        self.__creation_policy = WidgetManager.OnDemand
        self.__float_widgets_on_top = False

        self.__item_for_node = {}  # type: Dict[SchemeNode, Item]
        self.__item_for_widget = {}  # type: Dict[QWidget, Item]

        self.__init_queue = deque()

        self.__init_timer = QTimer(self, singleShot=True)
        self.__init_timer.timeout.connect(self.__process_init_queue)

        self.__activation_monitor = ActivationMonitor(self)
        self.__activation_counter = itertools.count()
        self.__activation_monitor.activated.connect(self.__mark_activated)
        self.__windows_list_head = QAction(
            None, objectName="action-canvas-windows-list-head",
        )
        self.__windows_list_head.setSeparator(True)

    def set_workflow(self, workflow):
        # type: (Scheme) -> None
        """
        Set the workflow.
        """
        if workflow is self.__workflow:
            return

        if self.__workflow is not None:
            # cleanup
            for node in self.__workflow.all_nodes():
                self.__remove_node(node)
            self.__workflow.node_added.disconnect(self.__on_node_added)
            self.__workflow.node_removed.disconnect(self.__on_node_removed)
            self.__workflow.removeEventFilter(self)

        self.__workflow = workflow

        workflow.node_added.connect(
            self.__on_node_added, Qt.UniqueConnection)
        workflow.node_removed.connect(
            self.__on_node_removed, Qt.UniqueConnection)
        workflow.installEventFilter(self)
        for node in workflow.all_nodes():
            self.__add_node(node)

    def workflow(self):
        # type: () -> Optional[Workflow]
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
                    for node in self.__workflow.all_nodes():
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
        # type: (SchemeNode, QWidget) -> None
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
        if self.__workflow is None:
            return

        if node not in self.__workflow.all_nodes():
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
            node.set_state_message(
                UserMessage(text, UserMessage.Error, "")
            )
            raise
        else:
            item.widget = w
            self.__item_for_widget[w] = item

        self.__set_float_on_top_flag(w)

        if w.windowIcon().isNull():
            w.setWindowIcon(node.icon())
        if not w.windowTitle():
            w.setWindowTitle(node.title)

        w.installEventFilter(self.__activation_monitor)
        raise_canvas = QAction(
            self.tr("Raise Canvas to Front"), w,
            objectName="action-canvas-raise-canvas",
            toolTip=self.tr("Raise containing canvas workflow window"),
            shortcut=QKeySequence("Ctrl+Up")
        )
        raise_canvas.triggered.connect(self.__on_activate_parent)
        raise_descendants = QAction(
            self.tr("Raise Descendants"), w,
            objectName="action-canvas-raise-descendants",
            toolTip=self.tr("Raise all immediate descendants of this node"),
            shortcut=QKeySequence("Ctrl+Shift+Right"),
            enabled=False,
        )
        raise_descendants.triggered.connect(
            partial(self.__on_raise_descendants, node)
        )
        raise_ancestors = QAction(
            self.tr("Raise Ancestors"), w,
            objectName="action-canvas-raise-ancestors",
            toolTip=self.tr("Raise all immediate ancestors of this node"),
            shortcut=QKeySequence("Ctrl+Shift+Left"),
            enabled=False,
        )
        raise_ancestors.triggered.connect(
            partial(self.__on_raise_ancestors, node)
        )
        w.addActions([raise_canvas, raise_descendants, raise_ancestors])
        w.addAction(self.__windows_list_head)
        windowmanager = WindowListManager.instance()
        windowmanager.addWindow(w)
        w.addActions(windowmanager.actions())
        w_ref = weakref.ref(w)  # avoid ref cycles in connection closures

        def addWindowAction(_, a: QAction):
            w = w_ref()
            if w is not None:
                w.addAction(a)

        def removeWindowAction(_, a: QAction):
            w = w_ref()
            if w is not None:
                w.removeAction(a)

        connect_with_context(
            windowmanager.windowAdded, w, addWindowAction,
        )
        connect_with_context(
            windowmanager.windowRemoved, w, removeWindowAction,
        )
        # send all the post creation notification events
        workflow = self.__workflow
        assert workflow is not None
        ev = NodeEvent(NodeEvent.NodeAdded, node)
        QCoreApplication.sendEvent(w, ev)
        inputs = workflow.find_links(sink_node=node)
        raise_ancestors.setEnabled(bool(inputs))
        for i, link in enumerate(inputs):
            ev = LinkEvent(LinkEvent.InputLinkAdded, link, i)
            QCoreApplication.sendEvent(w, ev)
        outputs = workflow.find_links(source_node=node)
        raise_descendants.setEnabled(bool(outputs))
        for i, link in enumerate(outputs):
            ev = LinkEvent(LinkEvent.OutputLinkAdded, link, i)
            QCoreApplication.sendEvent(w, ev)

        self.widget_for_node_added.emit(node, w)

    def ensure_created(self, node):
        # type: (SchemeNode) -> None
        """
        Ensure that the widget for node is created.
        """
        if self.__workflow is None:
            return
        # ignore MetaNodes and co.
        if not isinstance(node, SchemeNode):
            return
        if node not in self.__workflow.all_nodes():
            return
        item = self.__item_for_node.get(node)
        if item is None:
            self.__add_widget_for_node(node)

    def __on_node_added(self, node):
        # type: (Node) -> None
        assert self.__workflow is not None
        if isinstance(node, MetaNode):
            nodes = node.all_nodes()
        else:
            nodes = [node]
        for n in nodes:
            if isinstance(n, SchemeNode):
                self.__add_node(n)

    def __add_node(self, node):
        # type: (SchemeNode) -> None
        # add node for tracking
        node.installEventFilter(self)
        if self.__creation_policy == WidgetManager.Immediate:
            self.ensure_created(node)
        else:
            self.__init_queue.append(node)
            if self.__creation_policy == WidgetManager.Normal:
                self.__init_timer.start()

    def __on_node_removed(self, node):  # type: (SchemeNode) -> None
        assert self.__workflow is not None
        assert node not in self.__workflow.all_nodes()
        if isinstance(node, MetaNode):
            nodes = node.all_nodes()
        else:
            nodes = [node]
        for n in nodes:
            self.__remove_node(n)

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
            windowmanager = WindowListManager.instance()
            windowmanager.removeWindow(widget)
            ev = NodeEvent(NodeEvent.NodeRemoved, node)
            QCoreApplication.sendEvent(widget, ev)
            item.widget = None
            self.widget_for_node_removed.emit(node, widget)
            self.delete_widget_for_node(node, widget)

        if item is not None:
            del self.__item_for_node[node]

    @Slot()
    def __process_init_queue(self):
        if self.__init_queue:
            node = self.__init_queue.popleft()
            assert self.__workflow is not None
            assert node in self.__workflow.all_nodes()
            log.debug("__process_init_queue: '%s'", node.title)
            try:
                self.ensure_created(node)
            finally:
                if self.__init_queue:
                    self.__init_timer.start()

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
            map(self.__item_for_node.get, workflow.all_nodes()))
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
        if self.__workflow is None:
            return []

        workflow = self.__workflow  # type: Scheme
        state = []
        for node in workflow.all_nodes():  # type: SchemeNode
            item = self.__item_for_node.get(node, None)
            if item is None:
                continue
            stackorder = item.activation_order
            if item.widget is not None and not item.widget.isHidden():
                data = self.save_widget_geometry(node, item.widget)
                state.append((stackorder, node, data))

        return [(node, data)
                for _, node, data in sorted(state, key=lambda t: t[0])]

    def restore_window_state(self, state):
        # type: (List[Tuple[Node, bytes]]) -> None
        """
        Restore the window state.
        """
        assert self.__workflow is not None
        workflow = self.__workflow  # type: Scheme
        visible = {node for node, _ in state}
        # first hide all other widgets
        for node in workflow.all_nodes():
            if node not in visible:
                # avoid creating widgets if not needed
                item = self.__item_for_node.get(node, None)
                if item is not None and item.widget is not None:
                    item.widget.hide()
        allnodes = set(workflow.all_nodes())
        # restore state for visible group; windows are stacked as they appear
        # in the state list.
        w = None
        for node, node_state in filter(lambda t: t[0] in allnodes, state):
            w = self.widget_for_node(node)  # also create it if needed
            if w is not None:
                w.show()
                self.restore_widget_geometry(node, w, node_state)
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

    @Slot(SchemeNode)
    def __on_raise_ancestors(self, node):
        # type: (SchemeNode) -> None
        """
        Raise all the ancestor widgets of `widget`.
        """
        item = self.__item_for_node.get(node)
        if item is not None:
            scheme = self.scheme()
            assert scheme is not None
            ancestors = [self.__item_for_node.get(p)
                         for p in scheme.parent_nodes(item.node)]
            self.__raise_and_activate(filter(None, reversed(ancestors)))

    @Slot(SchemeNode)
    def __on_raise_descendants(self, node):
        # type: (SchemeNode) -> None
        """
        Raise all the descendants widgets of `widget`.
        """
        item = self.__item_for_node.get(node)
        if item is not None:
            scheme = self.scheme()
            assert scheme is not None
            descendants = [self.__item_for_node.get(p)
                           for p in scheme.child_nodes(item.node)]
            self.__raise_and_activate(filter(None, reversed(descendants)))

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

    def __on_link_added_removed(self, link: Link):
        source = link.source_node
        sink = link.sink_node
        item = self.__item_for_node.get(source)
        if item is not None and item.widget is not None:
            self.__update_actions_state(item)
        item = self.__item_for_node.get(sink)
        if item is not None and item.widget is not None:
            self.__update_actions_state(item)

    def __update_actions_state(self, item: Item) -> None:
        widget = item.widget
        workflow = self.__workflow
        if widget is None or workflow is None:
            return
        node = item.node
        inputs = workflow.find_links(sink_node=node)
        outputs = workflow.find_links(source_node=node)

        action = widget.findChild(QAction, "action-canvas-raise-ancestors")
        action.setEnabled(bool(inputs))

        action = widget.findChild(QAction, "action-canvas-raise-descendants")
        action.setEnabled(bool(outputs))

    def eventFilter(self, recv, event):
        # type: (QObject, QEvent) -> bool
        if isinstance(recv, SchemeNode):
            if event.type() == NodeEvent.NodeActivateRequest:
                self.__activate_widget_for_node(recv)
            self.__dispatch_events(recv, event)
        elif event.type() == WorkflowEvent.WorkflowEnvironmentChange \
                and recv is self.__workflow:
            for node in self.__item_for_node:
                self.__dispatch_events(node, event)
        elif event.type() in (LinkEvent.LinkAdded, LinkEvent.LinkRemoved):
            self.__on_link_added_removed(event.link())
        return False

    def __dispatch_events(self, node: Node, event: QEvent) -> None:
        """
        Dispatch relevant workflow events to the GUI widget
        """
        if event.type() in (
            WorkflowEvent.InputLinkAdded,
            WorkflowEvent.InputLinkRemoved,
            WorkflowEvent.InputLinkStateChange,
            WorkflowEvent.OutputLinkAdded,
            WorkflowEvent.OutputLinkRemoved,
            WorkflowEvent.OutputLinkStateChange,
            WorkflowEvent.NodeStateChange,
            WorkflowEvent.WorkflowEnvironmentChange,
        ):
            item = self.__item_for_node.get(node)
            if item is not None and item.widget is not None:
                QCoreApplication.sendEvent(item.widget, event)

    def __set_float_on_top_flag(self, widget):
        # type: (QWidget) -> None
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

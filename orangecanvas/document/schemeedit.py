"""
====================
Scheme Editor Widget
====================


"""
import enum
import io
import logging
import itertools
import re
import sys
import copy
import warnings
import dictdiffer

from operator import attrgetter
from urllib.parse import urlencode
from contextlib import ExitStack
from typing import (
    List, Tuple, Optional, Dict, Any, Iterable, Sequence
)

from AnyQt.QtWidgets import (
    QWidget, QVBoxLayout, QMenu, QAction, QActionGroup,
    QUndoStack, QGraphicsItem, QGraphicsTextItem,
    QGraphicsSceneDragDropEvent, QGraphicsSceneMouseEvent,
    QGraphicsSceneContextMenuEvent, QGraphicsView, QGraphicsScene,
    QApplication
)
from AnyQt.QtGui import (
    QKeySequence, QCursor, QFont, QPainter, QPixmap, QColor, QIcon,
    QWhatsThisClickedEvent, QKeyEvent, QPalette
)
from AnyQt.QtCore import (
    Qt, QObject, QEvent, QSignalMapper, QCoreApplication, QPointF,
    QMimeData, Slot)
from AnyQt.QtCore import pyqtProperty as Property, pyqtSignal as Signal

from orangecanvas.document.commands import UndoCommand
from .interactions import DropHandler, UserInteraction, propose_links
from .utils import prepare_macro_patch, disable_undo_stack_actions
from .windowgroupsdialog import SaveWindowGroup
from ..registry import WidgetDescription, WidgetRegistry
from .suggestions import Suggestions
from .usagestatistics import UsageStatistics
from ..registry.qt import whats_this_helper, QtWidgetRegistry
from ..gui.quickhelp import QuickHelpTipEvent
from ..gui.utils import (
    message_information, disabled, clipboard_has_format, clipboard_data
)
from ..scheme import (
    scheme, signalmanager, Scheme, SchemeNode, MetaNode, Node, Link,
    BaseSchemeAnnotation, SchemeTextAnnotation, WorkflowEvent,
)
from ..scheme.widgetmanager import WidgetManager
from ..canvas.scene import CanvasScene
from ..canvas.view import CanvasView
from ..canvas import items
from ..canvas.items.annotationitem import Annotation as AnnotationItem
from . import interactions
from . import commands
from . import quickmenu
from ..utils import findf, UNUSED, apply_all, uniquify, is_printable
from ..utils.qinvoke import connect_with_context

Pos = Tuple[float, float]
RuntimeState = signalmanager.SignalManager.State

# Private MIME type for clipboard contents
MimeTypeWorkflowFragment = "application/vnd.{}-ows-fragment+xml".format(__name__)

log = logging.getLogger(__name__)

DuplicateOffset = QPointF(0, 120)


class NoWorkflowError(RuntimeError):
    def __init__(self, message: str = "No workflow model is set", **kwargs):
        super().__init__(message, *kwargs)


class UndoStack(QUndoStack):

    indexIncremented = Signal()

    def __init__(self, parent, statistics: UsageStatistics):
        QUndoStack.__init__(self, parent)
        self.__statistics = statistics
        self.__previousIndex = self.index()
        self.__currentIndex = self.index()

        self.indexChanged.connect(self.__refreshIndex)

    @Slot(int)
    def __refreshIndex(self, newIndex):
        self.__previousIndex = self.__currentIndex
        self.__currentIndex = newIndex

        if self.__previousIndex < newIndex:
            self.indexIncremented.emit()

    @Slot()
    def undo(self):
        self.__statistics.begin_action(UsageStatistics.Undo)
        super().undo()
        self.__statistics.end_action()

    @Slot()
    def redo(self):
        self.__statistics.begin_action(UsageStatistics.Redo)
        super().redo()
        self.__statistics.end_action()

    def push(self, macro):
        super().push(macro)
        self.__statistics.end_action()


class SchemeEditWidget(QWidget):
    """
    A widget for editing a :class:`~.scheme.Scheme` instance.

    """
    #: Undo command has become available/unavailable.
    undoAvailable = Signal(bool)

    #: Redo command has become available/unavailable.
    redoAvailable = Signal(bool)

    #: Document modified state has changed.
    modificationChanged = Signal(bool)

    #: Undo command was added to the undo stack.
    undoCommandAdded = Signal()

    #: Item selection has changed.
    selectionChanged = Signal()

    #: Document title has changed.
    titleChanged = Signal(str)

    #: Document path has changed.
    pathChanged = Signal(str)

    # Quick Menu triggers
    (NoTriggers,
     RightClicked,
     DoubleClicked,
     SpaceKey,
     AnyKey) = [0, 1, 2, 4, 8]

    class OpenAnchors(enum.Enum):
        """Interactions with individual anchors"""
        #: Channel anchors never separate
        Never = "Never"
        #: Channel anchors separate on hover
        Always = "Always"
        #: Channel anchors separate on hover on Shift key
        OnShift = "OnShift"

    def __init__(self, parent=None, ):
        super().__init__(parent)

        self.__modified = False
        self.__registry = None       # type: Optional[WidgetRegistry]
        self.__scheme = None         # type: Optional[Scheme]
        self.__root = None           # type: Optional[MetaNode]
        self.__widgetManager = None  # type: Optional[WidgetManager]
        self.__path = ""

        self.__quickMenuTriggers = SchemeEditWidget.SpaceKey | \
                                   SchemeEditWidget.DoubleClicked
        self.__openAnchorsMode = SchemeEditWidget.OpenAnchors.OnShift
        self.__emptyClickButtons = Qt.NoButton
        self.__channelNamesVisible = True
        self.__nodeAnimationEnabled = True
        self.__possibleSelectionHandler = None
        self.__possibleMouseItemsMove = False
        self.__itemsMoving = {}
        self.__contextMenuTarget = None  # type: Optional[Link]
        self.__dropTarget = None  # type: Optional[items.LinkItem]
        self.__quickMenu = None   # type: Optional[quickmenu.QuickMenu]
        self.__quickTip = ""

        self.__statistics = UsageStatistics(self)

        self.__undoStack = UndoStack(self, self.__statistics)
        self.__undoStack.cleanChanged[bool].connect(self.__onCleanChanged)
        self.__undoStack.indexIncremented.connect(self.undoCommandAdded)

        # Preferred position for paste command. Updated on every mouse button
        # press and copy operation.
        self.__pasteOrigin = QPointF(20, 20)

        # scheme node properties when set to a clean state
        self.__cleanProperties = {}

        # list of links when set to a clean state
        self.__cleanLinks = []

        # list of annotations when set to a clean state
        self.__cleanAnnotations = []

        self.__dropHandlers = ()  # type: Sequence[DropHandler]

        self.__editFinishedMapper = QSignalMapper(self)
        self.__editFinishedMapper.mappedObject.connect(
            self.__onEditingFinished
        )

        self.__annotationGeomChanged = QSignalMapper(self)

        self.__setupActions()
        self.__setupUi()

        # Edit menu for a main window menu bar.
        self.__editMenu = QMenu(self.tr("&Edit"), self)
        self.__editMenu.addAction(self.__undoAction)
        self.__editMenu.addAction(self.__redoAction)
        self.__editMenu.addSeparator()
        self.__editMenu.addAction(self.__removeSelectedAction)
        self.__editMenu.addAction(self.__duplicateSelectedAction)
        self.__editMenu.addAction(self.__copySelectedAction)
        self.__editMenu.addAction(self.__pasteAction)
        self.__editMenu.addAction(self.__selectAllAction)
        self.__editMenu.addAction(self.__createMacroAction)

        # Widget context menu
        self.__widgetMenu = QMenu(self.tr("Widget"), self)
        self.__widgetMenu.addAction(self.__openSelectedAction)
        self.__widgetMenu.addSeparator()
        self.__widgetMenu.addAction(self.__renameAction)
        self.__widgetMenu.addAction(self.__removeSelectedAction)
        self.__widgetMenu.addAction(self.__duplicateSelectedAction)
        self.__widgetMenu.addAction(self.__copySelectedAction)
        self.__widgetMenu.addAction(self.__createMacroAction)
        self.__widgetMenu.addSeparator()
        self.__widgetMenu.addAction(self.__helpAction)

        # Widget menu for a main window menu bar.
        self.__menuBarWidgetMenu = QMenu(self.tr("&Widget"), self)
        self.__menuBarWidgetMenu.addAction(self.__openSelectedAction)
        self.__menuBarWidgetMenu.addAction(self.__openParentMetaNodeAction)
        self.__menuBarWidgetMenu.addSeparator()
        self.__menuBarWidgetMenu.addAction(self.__renameAction)
        self.__menuBarWidgetMenu.addAction(self.__removeSelectedAction)
        self.__menuBarWidgetMenu.addSeparator()
        self.__menuBarWidgetMenu.addAction(self.__helpAction)

        self.__linkMenu = QMenu(self.tr("Link"), self)
        self.__linkMenu.addAction(self.__linkEnableAction)
        self.__linkMenu.addSeparator()
        self.__linkMenu.addAction(self.__nodeInsertAction)
        self.__linkMenu.addSeparator()
        self.__linkMenu.addAction(self.__linkRemoveAction)
        self.__linkMenu.addAction(self.__linkResetAction)

        self.__suggestions = Suggestions()

    def __setupActions(self):
        self.__cleanUpAction = QAction(
            self.tr("Clean Up"), self,
            objectName="cleanup-action",
            shortcut=QKeySequence("Shift+A"),
            toolTip=self.tr("Align widgets to a grid (Shift+A)"),
            triggered=self.alignToGrid,
        )

        self.__newTextAnnotationAction = QAction(
            self.tr("Text"), self,
            objectName="new-text-action",
            toolTip=self.tr("Add a text annotation to the workflow."),
            checkable=True,
            toggled=self.__toggleNewTextAnnotation,
        )

        # Create a font size menu for the new annotation action.
        self.__fontMenu = QMenu("Font Size", self)
        self.__fontActionGroup = group = QActionGroup(
            self, triggered=self.__onFontSizeTriggered
        )

        def font(size):
            f = QFont(self.font())
            f.setPixelSize(size)
            return f

        for size in [12, 14, 16, 18, 20, 22, 24]:
            action = QAction(
                "%ipx" % size, group, checkable=True, font=font(size)
            )
            self.__fontMenu.addAction(action)

        group.actions()[2].setChecked(True)

        self.__newTextAnnotationAction.setMenu(self.__fontMenu)

        self.__newArrowAnnotationAction = QAction(
            self.tr("Arrow"), self,
            objectName="new-arrow-action",
            toolTip=self.tr("Add a arrow annotation to the workflow."),
            checkable=True,
            toggled=self.__toggleNewArrowAnnotation,
        )

        # Create a color menu for the arrow annotation action
        self.__arrowColorMenu = QMenu("Arrow Color",)
        self.__arrowColorActionGroup = group = QActionGroup(
            self, triggered=self.__onArrowColorTriggered
        )

        def color_icon(color):
            icon = QIcon()
            for size in [16, 24, 32]:
                pixmap = QPixmap(size, size)
                pixmap.fill(QColor(0, 0, 0, 0))
                p = QPainter(pixmap)
                p.setRenderHint(QPainter.Antialiasing)
                p.setBrush(color)
                p.setPen(Qt.NoPen)
                p.drawEllipse(1, 1, size - 2, size - 2)
                p.end()
                icon.addPixmap(pixmap)
            return icon

        for color in ["#000", "#C1272D", "#662D91", "#1F9CDF", "#39B54A"]:
            icon = color_icon(QColor(color))
            action = QAction(group, icon=icon, checkable=True,
                             iconVisibleInMenu=True)
            action.setData(color)
            self.__arrowColorMenu.addAction(action)

        group.actions()[1].setChecked(True)

        self.__newArrowAnnotationAction.setMenu(self.__arrowColorMenu)

        self.__undoAction = self.__undoStack.createUndoAction(self)
        self.__undoAction.setShortcut(QKeySequence.Undo)
        self.__undoAction.setObjectName("undo-action")

        self.__redoAction = self.__undoStack.createRedoAction(self)
        self.__redoAction.setShortcut(QKeySequence.Redo)
        self.__redoAction.setObjectName("redo-action")

        self.__selectAllAction = QAction(
            self.tr("Select all"), self,
            objectName="select-all-action",
            toolTip=self.tr("Select all items."),
            triggered=self.selectAll,
            shortcut=QKeySequence.SelectAll
        )
        self.__openSelectedAction = QAction(
            self.tr("Open"), self,
            objectName="open-action",
            toolTip=self.tr("Open selected widget"),
            triggered=self.openSelected,
            enabled=False
        )
        self.__removeSelectedAction = QAction(
            self.tr("Remove"), self,
            objectName="remove-selected",
            toolTip=self.tr("Remove selected items"),
            triggered=self.removeSelected,
            enabled=False
        )

        shortcuts = [QKeySequence(Qt.Key_Backspace),
                     QKeySequence(Qt.Key_Delete),
                     QKeySequence("Ctrl+Backspace")]

        self.__removeSelectedAction.setShortcuts(shortcuts)

        self.__renameAction = QAction(
            self.tr("Rename"), self,
            objectName="rename-action",
            toolTip=self.tr("Rename selected widget"),
            triggered=self.__onRenameAction,
            shortcut=QKeySequence(Qt.Key_F2),
            enabled=False
        )
        if sys.platform == "darwin":
            self.__renameAction.setShortcuts([
                QKeySequence(Qt.Key_F2),
                QKeySequence(Qt.Key_Enter),
                QKeySequence(Qt.Key_Return)
            ])

        self.__helpAction = QAction(
            self.tr("Help"), self,
            objectName="help-action",
            toolTip=self.tr("Show widget help"),
            triggered=self.__onHelpAction,
            shortcut=QKeySequence("F1"),
            enabled=False,
        )
        self.__linkEnableAction = QAction(
            self.tr("Enabled"), self, objectName="link-enable-action",
            triggered=self.__toggleLinkEnabled, checkable=True,
        )

        self.__linkRemoveAction = QAction(
            self.tr("Remove"), self,
            objectName="link-remove-action",
            triggered=self.__linkRemove,
            toolTip=self.tr("Remove link."),
        )

        self.__nodeInsertAction = QAction(
            self.tr("Insert Widget"), self,
            objectName="node-insert-action",
            triggered=self.__nodeInsert,
            toolTip=self.tr("Insert widget."),
        )

        self.__linkResetAction = QAction(
            self.tr("Reset Signals"), self,
            objectName="link-reset-action",
            triggered=self.__linkReset,
        )

        self.__duplicateSelectedAction = QAction(
            self.tr("Duplicate"), self,
            objectName="duplicate-action",
            enabled=False,
            shortcut=QKeySequence("Ctrl+D"),
            triggered=self.__duplicateSelected,
        )

        self.__copySelectedAction = QAction(
            self.tr("Copy"), self,
            objectName="copy-action",
            enabled=False,
            shortcut=QKeySequence("Ctrl+C"),
            triggered=self.__copyToClipboard,
        )
        self.__createMacroAction = QAction(
            self.tr("Create Macro"), self,
            objectName="create-macro-action",
            enabled=False,
            shortcut=QKeySequence(Qt.ControlModifier | Qt.ShiftModifier | Qt.Key_M),
            triggered=self.createMacroFromSelection,
        )
        self.__pasteAction = QAction(
            self.tr("Paste"), self,
            objectName="paste-action",
            enabled=clipboard_has_format(MimeTypeWorkflowFragment),
            shortcut=QKeySequence("Ctrl+V"),
            triggered=self.__pasteFromClipboard,
        )
        QApplication.clipboard().dataChanged.connect(
            self.__updatePasteActionState
        )

        self.addActions([
            self.__newTextAnnotationAction,
            self.__newArrowAnnotationAction,
            self.__linkEnableAction,
            self.__linkRemoveAction,
            self.__nodeInsertAction,
            self.__linkResetAction,
            self.__duplicateSelectedAction,
            self.__copySelectedAction,
            self.__createMacroAction,
            self.__pasteAction
        ])

        # Actions which should be disabled while a multistep
        # interaction is in progress.
        self.__disruptiveActions = [
            self.__undoAction,
            self.__redoAction,
            self.__removeSelectedAction,
            self.__selectAllAction,
            self.__duplicateSelectedAction,
            self.__copySelectedAction,
            self.__pasteAction
        ]

        #: Top 'Window Groups' action
        self.__windowGroupsAction = QAction(
            self.tr("Window Groups"), self, objectName="window-groups-action",
            toolTip="Manage preset widget groups"
        )
        #: Action group containing action for every window group
        self.__windowGroupsActionGroup = QActionGroup(
            self.__windowGroupsAction, objectName="window-groups-action-group",
        )
        self.__windowGroupsActionGroup.triggered.connect(
            self.__activateWindowGroup
        )
        self.__saveWindowGroupAction = QAction(
            self.tr("Save Window Group..."), self,
            objectName="window-groups-save-action",
            toolTip="Create and save a new window group."
        )
        self.__saveWindowGroupAction.triggered.connect(self.__saveWindowGroup)
        self.__clearWindowGroupsAction = QAction(
            self.tr("Delete All Groups"), self,
            objectName="window-groups-clear-action",
            toolTip="Delete all saved widget presets"
        )
        self.__clearWindowGroupsAction.triggered.connect(
            self.__clearWindowGroups
        )

        groups_menu = QMenu(self)
        sep = groups_menu.addSeparator()
        sep.setObjectName("groups-separator")
        groups_menu.addAction(self.__saveWindowGroupAction)
        groups_menu.addSeparator()
        groups_menu.addAction(self.__clearWindowGroupsAction)
        self.__windowGroupsAction.setMenu(groups_menu)

        # the counterpart to Control + Key_Up to raise the containing workflow
        # view (maybe move that shortcut here)
        self.__raiseWidgetsAction = QAction(
            self.tr("Bring Widgets to Front"), self,
            objectName="bring-widgets-to-front-action",
            shortcut=QKeySequence("Ctrl+Down"),
            shortcutContext=Qt.WindowShortcut,
        )
        self.__raiseWidgetsAction.triggered.connect(self.__raiseToFont)
        self.addAction(self.__raiseWidgetsAction)
        self.__openParentMetaNodeAction = QAction(
            self.tr("Up"), self,
            objectName="open-parent-meta-node-action",
            shortcut=QKeySequence(Qt.ControlModifier | Qt.Key_Up),
            shortcutContext=Qt.WindowShortcut,
            enabled=False,
        )
        self.__openParentMetaNodeAction.triggered.connect(self.openParentMetaNode)
        self.addAction(self.__openParentMetaNodeAction)

    def __setupUi(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scene = CanvasScene(self)
        scene.setItemIndexMethod(CanvasScene.NoIndex)
        self.__setupScene(scene)

        view = CanvasView(scene)
        view.setFrameStyle(CanvasView.NoFrame)
        view.setRenderHint(QPainter.Antialiasing)

        self.__view = view
        self.__scenes = {"root": scene}

        layout.addWidget(view)
        self.setLayout(layout)

    def __setupScene(self, scene):
        # type: (CanvasScene) -> None
        """
        Set up a :class:`CanvasScene` instance for use by the editor.

        .. note:: If an existing scene is in use it must be teared down using
            __teardownScene
        """
        scene.set_channel_names_visible(self.__channelNamesVisible)
        scene.set_node_animation_enabled(
            self.__nodeAnimationEnabled
        )
        if self.__openAnchorsMode == SchemeEditWidget.OpenAnchors.Always:
            scene.set_widget_anchors_open(True)

        scene.setFont(self.font())
        scene.setPalette(self.palette())
        scene.installEventFilter(self)
        scene.focusItemChanged.connect(self.__onFocusItemChanged)
        scene.selectionChanged.connect(self.__onSelectionChanged)
        scene.link_item_activated.connect(self.__onLinkActivate)
        scene.link_item_added.connect(self.__onLinkAdded)
        scene.node_item_activated.connect(self.__onNodeActivate)
        scene.annotation_added.connect(self.__onAnnotationAdded)
        scene.annotation_removed.connect(self.__onAnnotationRemoved)

    def __teardownScene(self, scene):
        # type: (CanvasScene) -> None
        """
        Tear down an instance of :class:`CanvasScene` that was used by the
        editor.
        """
        # Clear the current item selection in the scene so edit action
        # states are updated accordingly.
        scene.clearSelection()
        # Clear focus from any item.
        scene.setFocusItem(None)
        scene.focusItemChanged.disconnect(self.__onFocusItemChanged)
        scene.selectionChanged.disconnect(self.__onSelectionChanged)
        scene.removeEventFilter(self)
        # Clear all items from the scene
        scene.blockSignals(True)
        scene.clear_scene()

    def toolbarActions(self):
        # type: () -> List[QAction]
        """
        Return a list of actions that can be inserted into a toolbar.
        At the moment these are:

            - 'Zoom in' action
            - 'Zoom out' action
            - 'Zoom Reset' action
            - 'Clean up' action (align to grid)
            - 'New text annotation' action (with a size menu)
            - 'New arrow annotation' action (with a color menu)

        """
        view = self.__view
        zoomin = view.findChild(QAction, "action-zoom-in")
        zoomout = view.findChild(QAction, "action-zoom-out")
        zoomreset = view.findChild(QAction, "action-zoom-reset")
        assert zoomin and zoomout and zoomreset
        return [zoomin,
                zoomout,
                zoomreset,
                self.__cleanUpAction,
                self.__newTextAnnotationAction,
                self.__newArrowAnnotationAction]

    def menuBarActions(self):
        # type: () -> List[QAction]
        """
        Return a list of actions that can be inserted into a `QMenuBar`.

        """
        return [self.__editMenu.menuAction(),
                self.__menuBarWidgetMenu.menuAction()]

    def isModified(self):
        # type: () -> bool
        """
        Is the document is a modified state.
        """
        return self.__modified or not self.__undoStack.isClean()

    def setModified(self, modified):
        # type: (bool) -> None
        """
        Set the document modified state.
        """
        if self.__modified != modified:
            self.__modified = modified

        if not modified:
            if self.__scheme:
                self.__cleanProperties = node_properties(self.__scheme)
                self.__cleanLinks = self.__scheme.all_links()
                self.__cleanAnnotations = self.__scheme.all_annotations()
            else:
                self.__cleanProperties = {}
                self.__cleanLinks = []
                self.__cleanAnnotations = []
            self.__undoStack.setClean()
        else:
            self.__cleanProperties = {}
            self.__cleanLinks = []
            self.__cleanAnnotations = []

    modified = Property(bool, fget=isModified, fset=setModified)

    def isModifiedStrict(self):
        """
        Is the document modified.

        Run a strict check against all node properties as they were
        at the time when the last call to `setModified(True)` was made.

        """
        propertiesChanged = self.__cleanProperties != \
                            node_properties(self.__scheme)

        log.debug("Modified strict check (modified flag: %s, "
                  "undo stack clean: %s, properties: %s)",
                  self.__modified,
                  self.__undoStack.isClean(),
                  propertiesChanged)

        return self.isModified() or propertiesChanged

    def uncleanProperties(self):
        """
        Returns node properties differences since last clean state,
        excluding unclean nodes.
        """

        currentProperties = node_properties(self.__scheme)
        # ignore diff for newly created nodes
        cleanNodes = self.cleanNodes()
        currentCleanNodeProperties = {k: v
                                      for k, v in currentProperties.items()
                                      if k in cleanNodes}

        cleanProperties = self.__cleanProperties
        # ignore diff for deleted nodes
        currentNodes = self.__scheme.all_nodes()
        cleanCurrentNodeProperties = {k: v
                                      for k, v in cleanProperties.items()
                                      if k in currentNodes}

        # ignore contexts
        ignore = set((node, "context_settings")
                     for node in currentCleanNodeProperties.keys())

        return list(dictdiffer.diff(
            cleanCurrentNodeProperties,
            currentCleanNodeProperties,
            ignore=ignore
        ))

    def restoreProperties(self, dict_diff):
        ref_properties = {
            node: node.properties for node in self.__scheme.all_nodes()
        }
        dictdiffer.patch(dict_diff, ref_properties, in_place=True)

    def cleanNodes(self):
        return list(self.__cleanProperties.keys())

    def cleanLinks(self):
        return self.__cleanLinks

    def cleanAnnotations(self):
        return self.__cleanAnnotations

    def setQuickMenuTriggers(self, triggers):
        # type: (int) -> None
        """
        Set quick menu trigger flags.

        Flags can be a bitwise `or` of:

            - `SchemeEditWidget.NoTrigeres`
            - `SchemeEditWidget.RightClicked`
            - `SchemeEditWidget.DoubleClicked`
            - `SchemeEditWidget.SpaceKey`
            - `SchemeEditWidget.AnyKey`

        """
        if self.__quickMenuTriggers != triggers:
            self.__quickMenuTriggers = triggers

    def quickMenuTriggers(self):
        # type: () -> int
        """
        Return quick menu trigger flags.
        """
        return self.__quickMenuTriggers

    def setChannelNamesVisible(self, visible):
        # type: (bool) -> None
        """
        Set channel names visibility state. When enabled the links
        in the view will have a source/sink channel names displayed over
        them.
        """
        if self.__channelNamesVisible != visible:
            self.__channelNamesVisible = visible
            apply_all(
                lambda s: s.set_channel_names_visible(visible),
                self.__scenes.values(),
            )

    def channelNamesVisible(self):
        # type: () -> bool
        """
        Return the channel name visibility state.
        """
        return self.__channelNamesVisible

    def setNodeAnimationEnabled(self, enabled):
        # type: (bool) -> None
        """
        Set the node item animation enabled state.
        """
        if self.__nodeAnimationEnabled != enabled:
            self.__nodeAnimationEnabled = enabled
            apply_all(
                lambda s: s.set_node_animation_enabled(enabled),
                self.__scenes.values(),
            )

    def nodeAnimationEnabled(self):
        # type () -> bool
        """
        Return the node item animation enabled state.
        """
        return self.__nodeAnimationEnabled

    def setOpenAnchorsMode(self, state: OpenAnchors):
        self.__openAnchorsMode = state
        apply_all(
            lambda s: s.set_widget_anchors_open(
                state == SchemeEditWidget.OpenAnchors.Always
            ),
            self.__scenes.values(),
        )

    def openAnchorsMode(self) -> OpenAnchors:
        return self.__openAnchorsMode

    def undoStack(self):
        # type: () -> QUndoStack
        """
        Return the undo stack.
        """
        return self.__undoStack

    def setPath(self, path):
        # type: (str) -> None
        """
        Set the path associated with the current scheme.

        .. note:: Calling `setScheme` will invalidate the path (i.e. set it
                  to an empty string)

        """
        if self.__path != path:
            self.__path = path
            self.pathChanged.emit(self.__path)

    def path(self):
        # type: () -> str
        """
        Return the path associated with the scheme
        """
        return self.__path

    def setScheme(self, scheme):
        # type: (Scheme) -> None
        """
        Set the :class:`~.scheme.Scheme` instance to display/edit.
        """
        if self.__scheme is not scheme:
            if self.__scheme:
                self.__scheme.title_changed.disconnect(self.titleChanged)
                self.__scheme.window_group_presets_changed.disconnect(
                    self.__reset_window_group_menu
                )
                self.__scheme.removeEventFilter(self)
                sm = self.__scheme.findChild(signalmanager.SignalManager)
                if sm:
                    sm.stateChanged.disconnect(
                        self.__signalManagerStateChanged)
                self.__widgetManager = None

                self.__scheme.node_added.disconnect(self.__statistics.log_node_add)
                self.__scheme.node_removed.disconnect(self.__statistics.log_node_remove)
                self.__scheme.link_added.disconnect(self.__statistics.log_link_add)
                self.__scheme.link_removed.disconnect(self.__statistics.log_link_remove)
                self.__statistics.write_statistics()

            self.__scheme = scheme
            self.__root = scheme.root()
            self.__suggestions.set_scheme(self)

            self.setPath("")

            if self.__scheme:
                self.__scheme.title_changed.connect(self.titleChanged)
                self.titleChanged.emit(scheme.title)
                self.__scheme.window_group_presets_changed.connect(
                    self.__reset_window_group_menu
                )
                self.__cleanProperties = node_properties(scheme)
                self.__cleanLinks = scheme.all_links()
                self.__cleanAnnotations = scheme.all_annotations()
                sm = scheme.findChild(signalmanager.SignalManager)
                if sm:
                    sm.stateChanged.connect(self.__signalManagerStateChanged)
                self.__widgetManager = getattr(scheme, "widget_manager", None)

                self.__scheme.node_added.connect(self.__statistics.log_node_add)
                self.__scheme.node_removed.connect(self.__statistics.log_node_remove)
                self.__scheme.link_added.connect(self.__statistics.log_link_add)
                self.__scheme.link_removed.connect(self.__statistics.log_link_remove)
                self.__statistics.log_scheme(self.__scheme)
            else:
                self.__cleanProperties = {}
                self.__cleanLinks = []
                self.__cleanAnnotations = []

            # clear all scenes
            for _, scene in self.__scenes.items():
                self.__teardownScene(scene)
                scene.deleteLater()

            self.__scenes.clear()
            self.__annotationGeomChanged.deleteLater()
            self.__annotationGeomChanged = QSignalMapper(self)

            self.__undoStack.clear()

            scene = CanvasScene(self)
            scene.setItemIndexMethod(CanvasScene.NoIndex)
            self.__setupScene(scene)
            self.__scenes[self.__root] = scene

            scene.set_scheme(scheme, self.__root)

            self.__view.setScene(scene)

            if self.__scheme:
                self.__scheme.installEventFilter(self)
                nodes = self.__scheme.nodes
                if nodes:
                    # TODO: First in root layer
                    self.ensureVisible(nodes[0])
        self.__reset_window_group_menu()

    def ensureVisible(self, node):
        # type: (Node) -> None
        """
        Scroll the contents of the viewport so that `node` is visible.

        Parameters
        ----------
        node: Node
        """
        if self.__scheme is None:
            return
        scene = self.currentScene()
        item = scene.item_for_node(node)
        self.__view.ensureVisible(item)

    def scheme(self):
        # type: () -> Optional[Scheme]
        """
        Return the :class:`~.scheme.Scheme` edited by the widget.
        """
        return self.__scheme

    def root(self) -> Optional[MetaNode]:
        return self.__root

    def scene(self):
        # type: () -> QGraphicsScene
        """
        Return the :class:`QGraphicsScene` instance used to display the
        current scheme.
        """
        warnings.warn(
            "scene is deprecated", DeprecationWarning, stacklevel=2
        )
        return self.__scenes.get(self.__scheme.root())

    def currentScene(self) -> CanvasScene:
        return self.__view.scene()

    def view(self):
        # type: () -> QGraphicsView
        """
        Return the :class:`QGraphicsView` instance used to display the
        current scene.
        """
        return self.__view

    def suggestions(self):
        """
        Return the widget suggestion prediction class.
        """
        return self.__suggestions

    def usageStatistics(self):
        """
        Return the usage statistics logging class.
        """
        return self.__statistics

    def setRegistry(self, registry):
        # Is this method necessary?
        # It should be removed when the scene (items) is fixed
        # so all information regarding the visual appearance is
        # included in the node/widget description.
        self.__registry = registry
        self.__quickMenu = None

    def registry(self):
        return self.__registry

    def quickMenu(self):
        # type: () -> quickmenu.QuickMenu
        """
        Return a :class:`~.quickmenu.QuickMenu` popup menu instance for
        new node creation.
        """
        if self.__quickMenu is None:
            menu = quickmenu.QuickMenu(self)
            if self.__registry is not None:
                menu.setModel(self.__registry.model())
            self.__quickMenu = menu
        return self.__quickMenu

    def setTitle(self, title):
        # type: (str) -> None
        """
        Set the scheme title.
        """
        self.__undoStack.push(
            commands.SetAttrCommand(self.__scheme, "title", title)
        )

    def setDescription(self, description):
        # type: (str) -> None
        """
        Set the scheme description string.
        """
        self.__undoStack.push(
            commands.SetAttrCommand(self.__scheme, "description", description)
        )

    def addNode(self, node):
        # type: (Node) -> None
        """
        Add a new node (:class:`.Node`) to the document.
        """
        if self.__scheme is None:
            raise NoWorkflowError()
        command = commands.AddNodeCommand(self.__scheme, node, self.__root)
        self.__undoStack.push(command)

    def createNewNode(self, description, title=None, position=None):
        # type: (WidgetDescription, Optional[str], Optional[Pos]) -> SchemeNode
        """
        Create a new :class:`.SchemeNode` and add it to the document.
        The new node is constructed using :func:`~SchemeEdit.newNodeHelper`
        method
        """
        node = self.newNodeHelper(description, title, position)
        self.addNode(node)

        return node

    def newNodeHelper(self, description, title=None, position=None):
        # type: (WidgetDescription, Optional[str], Optional[Pos]) -> SchemeNode
        """
        Return a new initialized :class:`.SchemeNode`. If `title`
        and `position` are not supplied they are initialized to sensible
        defaults.
        """
        if title is None:
            title = self.enumerateTitle(description.name)

        if position is None:
            position = self.nextPosition()

        return SchemeNode(description, title=title, position=position)

    def enumerateTitle(self, title):
        # type: (str) -> str
        """
        Enumerate a `title` string (i.e. add a number in parentheses) so
        it is not equal to any node title in the current scheme.
        """
        if self.__scheme is None:
            return title
        curr_titles = set([node.title for node in self.__scheme.all_nodes()])
        if title not in curr_titles:
            return title
        return uniquify(title, curr_titles, "{item} ({_})", start=1)

    def nextPosition(self):
        # type: () -> Tuple[float, float]
        """
        Return the next default node position as a (x, y) tuple. This is
        a position left of the last added node.
        """
        if self.__scheme is not None:
            nodes = self.__scheme.nodes
        else:
            nodes = []
        if nodes:
            x, y = nodes[-1].position
            position = (x + 150, y)
        else:
            position = (150, 150)
        return position

    def removeNode(self, node):
        # type: (Node) -> None
        """
        Remove a `node` (:class:`.Node`) from the scheme
        """
        if self.__scheme is None:
            raise NoWorkflowError()
        command = commands.RemoveNodeCommand(self.__scheme, node, self.__root)
        self.__undoStack.push(command)

    def renameNode(self, node, title):
        # type: (Node, str) -> None
        """
        Rename a `node` (:class:`.Node`) to `title`.
        """
        if self.__scheme is None:
            raise NoWorkflowError()
        self.__undoStack.push(
            commands.RenameNodeCommand(self.__scheme, node, node.title, title)
        )

    def addLink(self, link):
        # type: (Link) -> None
        """
        Add a `link` (:class:`.Link`) to the scheme.
        """
        if self.__scheme is None:
            raise NoWorkflowError()
        command = commands.AddLinkCommand(self.__scheme, link, self.__root)
        self.__undoStack.push(command)

    def removeLink(self, link):
        # type: (Link) -> None
        """
        Remove a link (:class:`.Link`) from the scheme.
        """
        if self.__scheme is None:
            raise NoWorkflowError()
        command = commands.RemoveLinkCommand(self.__scheme, link, self.__root)
        self.__undoStack.push(command)

    def insertNode(self, new_node, old_link):
        # type: (Node, Link) -> None
        """
        Insert a node in-between two linked nodes.
        """
        if self.__scheme is None:
            raise NoWorkflowError()
        source_node = old_link.source_node
        sink_node = old_link.sink_node
        source_channel = old_link.source_channel
        sink_channel = old_link.sink_channel

        proposed_links = (propose_links(self.__scheme, source_node, new_node),
                          propose_links(self.__scheme, new_node, sink_node))
        # Preserve existing {source,sink}_channel if possible; use first
        # proposed if not.
        first = findf(proposed_links[0], lambda t: t[0] == source_channel,
                      default=proposed_links[0][0])
        second = findf(proposed_links[1], lambda t: t[1] == sink_channel,
                       default=proposed_links[1][0])
        new_links = (
            Link(source_node, first[0], new_node, first[1]),
            Link(new_node, second[0], sink_node, second[1])
        )
        command = commands.InsertNodeCommand(self.__scheme, new_node, old_link, new_links, self.__root)
        self.__undoStack.push(command)

    def onNewLink(self, func):
        """
        Runs function when new link is added to current scheme.
        """
        self.__scheme.link_added.connect(func)

    def addAnnotation(self, annotation):
        # type: (BaseSchemeAnnotation) -> None
        """
        Add `annotation` (:class:`.BaseSchemeAnnotation`) to the scheme
        """
        if self.__scheme is None:
            raise NoWorkflowError()
        command = commands.AddAnnotationCommand(self.__scheme, annotation, self.__root)
        self.__undoStack.push(command)

    def removeAnnotation(self, annotation):
        # type: (BaseSchemeAnnotation) -> None
        """
        Remove `annotation` (:class:`.BaseSchemeAnnotation`) from the scheme.
        """
        if self.__scheme is None:
            raise NoWorkflowError()
        command = commands.RemoveAnnotationCommand(self.__scheme, annotation, self.__root)
        self.__undoStack.push(command)

    def removeSelected(self):
        # type: () -> None
        """
        Remove all selected items in the scheme.
        """
        selected = self.currentScene().selectedItems()
        if not selected:
            return
        scene = self.currentScene()
        self.__undoStack.beginMacro(self.tr("Remove"))
        # order LinkItem removes before NodeItems; Removing NodeItems also
        # removes links so some links in selected could already be removed by
        # a preceding NodeItem remove
        selected = sorted(
            selected, key=lambda item: not isinstance(item, items.LinkItem))
        for item in selected:
            assert self.__scheme is not None
            if isinstance(item, items.NodeItem):
                node = scene.node_for_item(item)
                self.__undoStack.push(
                    commands.RemoveNodeCommand(self.__scheme, node, self.__root)
                )
            elif isinstance(item, items.annotationitem.Annotation):
                if item.hasFocus() or item.isAncestorOf(scene.focusItem()):
                    # Clear input focus from the item to be removed.
                    scene.focusItem().clearFocus()
                annot = scene.annotation_for_item(item)
                self.__undoStack.push(
                    commands.RemoveAnnotationCommand(self.__scheme, annot, self.__root)
                )
            elif isinstance(item, items.LinkItem):
                link = scene.link_for_item(item)
                self.__undoStack.push(
                    commands.RemoveLinkCommand(self.__scheme, link, self.__root)
                )
        self.__undoStack.endMacro()

    def selectAll(self):
        # type: () -> None
        """
        Select all selectable items in the scheme.
        """
        scene = self.currentScene()
        for item in scene.items():
            if item.flags() & QGraphicsItem.ItemIsSelectable:
                item.setSelected(True)

    def alignToGrid(self):
        # type: () -> None
        """
        Align nodes to a grid.
        """
        # TODO: The the current layout implementation is BAD (fix is urgent).
        if self.__scheme is None:
            return
        scene = self.currentScene()
        tile_size = 150
        tiles = {}  # type: Dict[Tuple[int, int], Node]
        nodes = sorted(self.__root.nodes(), key=attrgetter("position"))

        if nodes:
            self.__undoStack.beginMacro(self.tr("Align To Grid"))

            for node in nodes:
                x, y = node.position
                x = int(round(float(x) / tile_size) * tile_size)
                y = int(round(float(y) / tile_size) * tile_size)
                while (x, y) in tiles:
                    x += tile_size

                self.__undoStack.push(
                    commands.MoveNodeCommand(self.__scheme, node,
                                             node.position, (x, y))
                )

                tiles[x, y] = node
                scene.item_for_node(node).setPos(x, y)

            self.__undoStack.endMacro()

    def focusNode(self):
        # type: () -> Optional[Node]
        """
        Return the current focused :class:`.Node` or ``None`` if no
        node has focus.
        """
        scene = self.currentScene()
        focus = scene.focusItem()
        node = None
        if isinstance(focus, items.NodeItem):
            try:
                node = scene.node_for_item(focus)
            except KeyError:
                # in case the node has been removed but the scene was not
                # yet fully updated.
                node = None
        return node

    def selectedNodes(self):
        # type: () -> List[Node]
        """
        Return all selected :class:`.Node` items.
        """
        return list(map(self.currentScene().node_for_item,
                        self.currentScene().selected_node_items()))

    def selectedLinks(self):
        # type: () -> List[Link]
        return list(map(self.currentScene().link_for_item,
                        self.currentScene().selected_link_items()))

    def selectedAnnotations(self):
        # type: () -> List[BaseSchemeAnnotation]
        """
        Return all selected :class:`.BaseSchemeAnnotation` items.
        """
        return list(map(self.currentScene().annotation_for_item,
                        self.currentScene().selected_annotation_items()))

    def __openNodes(self, nodes: Sequence[Node]):
        if len(nodes) == 1:
            node = nodes[0]
            if isinstance(node, MetaNode):
                self.openMetaNode(node)
                return
        # TODO: Dispatch to WidgetManager directly
        for node in nodes:
            QCoreApplication.sendEvent(
                node, WorkflowEvent(WorkflowEvent.NodeActivateRequest))

    def openSelected(self):
        # type: () -> None
        """
        Open (show and raise) all widgets for the current selected nodes.
        """
        self.__openNodes(self.selectedNodes())

    def openParentMetaNode(self):
        current = self.root()
        if current is None:
            return
        parent = current.parent_node()
        if parent is None:
            return
        self.openMetaNode(parent)

    def openMetaNode(self, node: MetaNode):
        view = self.__view
        scene = self.__scenes.get(node, None)
        workflow = self.__scheme
        handler = self._userInteractionHandler()
        if handler is not None:
            handler.cancel()
        # This is too much state
        self.__possibleSelectionHandler = None
        self.__possibleMouseItemsMove = False
        self.__itemsMoving = {}
        self.__root = node
        if scene is None:
            scene = CanvasScene(self)
            scene.setItemIndexMethod(CanvasScene.NoIndex)
            self.__setupScene(scene)
            scene.set_scheme(workflow, root=node)
            self.__scenes[node] = scene

            view.setScene(scene)
            nodes = node.nodes()
            if nodes:
                self.ensureVisible(nodes[0])
        else:
            view.setScene(scene)
        self.__openParentMetaNodeAction.setEnabled(node is not workflow.root())

    def editNodeTitle(self, node):
        # type: (Node) -> None
        """
        Edit (rename) the `node`'s title.
        """
        self.__view.setFocus(Qt.OtherFocusReason)
        scene = self.currentScene()
        item = scene.item_for_node(node)
        item.editTitle()

        def commit():
            name = item.title()
            if name == node.title:
                return  # pragma: no cover
            self.__undoStack.push(
                commands.RenameNodeCommand(self.__scheme, node, node.title,
                                           name)
            )
        connect_with_context(
            item.titleEditingFinished, self, commit
        )

    def __onCleanChanged(self, clean):
        # type: (bool) -> None
        if self.isWindowModified() != (not clean):
            self.setWindowModified(not clean)
            self.modificationChanged.emit(not clean)

    def setDropHandlers(self, dropHandlers: Sequence[DropHandler]) -> None:
        """
        Set handlers for drop events onto the workflow view.
        """
        self.__dropHandlers = tuple(dropHandlers)

    def changeEvent(self, event):
        # type: (QEvent) -> None
        if event.type() == QEvent.FontChange:
            font = self.font()
            apply_all(lambda s: s.setFont(font), self.__scenes.values())
        elif event.type() == QEvent.PaletteChange:
            palette = self.palette()
            apply_all(
                lambda s: s.setPalette(palette), self.__scenes.values(),
            )
        super().changeEvent(event)

    def __lookup_registry(self, qname: str) -> Optional[WidgetDescription]:
        if self.__registry is not None:
            try:
                return self.__registry.widget(qname)
            except KeyError:
                pass
        return None

    def __desc_from_mime_data(self, data: QMimeData) -> Optional[WidgetDescription]:
        MIME_TYPES = [
            "application/vnd.orange-canvas.registry.qualified-name",
            # A back compatible misspelling
            "application/vnv.orange-canvas.registry.qualified-name",
        ]
        for typ in MIME_TYPES:
            if data.hasFormat(typ):
                qname_bytes = bytes(data.data(typ).data())
                try:
                    qname = qname_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    return None
                return self.__lookup_registry(qname)
        return None

    def eventFilter(self, obj, event):
        # type: (QObject, QEvent) -> bool
        # Filter the scene's drag/drop events.
        scene = self.currentScene()
        if obj is scene:
            etype = event.type()
            if etype == QEvent.GraphicsSceneDragEnter or \
                    etype == QEvent.GraphicsSceneDragMove:
                assert isinstance(event, QGraphicsSceneDragDropEvent)
                drop_target = None
                desc = self.__desc_from_mime_data(event.mimeData())
                if desc is not None:
                    item = scene.item_at(event.scenePos(), items.LinkItem)
                    link = scene.link_for_item(item) if item else None
                    if link is not None and can_insert_node(desc, link):
                        drop_target = item
                        drop_target.setHoverState(True)
                    event.acceptProposedAction()
                if self.__dropTarget is not None and \
                        self.__dropTarget is not drop_target:
                    self.__dropTarget.setHoverState(False)
                self.__dropTarget = drop_target
                if desc is not None:
                    return True
            elif etype == QEvent.GraphicsSceneDragLeave:
                if self.__dropTarget is not None:
                    self.__dropTarget.setHoverState(False)
                    self.__dropTarget = None
            elif etype == QEvent.GraphicsSceneDrop:
                assert isinstance(event, QGraphicsSceneDragDropEvent)
                desc = self.__desc_from_mime_data(event.mimeData())
                if desc is not None:
                    statistics = self.usageStatistics()
                    pos = event.scenePos()
                    item = scene.item_at(event.scenePos(), items.LinkItem)
                    link = scene.link_for_item(item) if item else None
                    if link and can_insert_node(desc, link):
                        statistics.begin_insert_action(True, link)
                        node = self.newNodeHelper(desc, position=(pos.x(), pos.y()))
                        self.insertNode(node, link)
                    else:
                        statistics.begin_action(UsageStatistics.ToolboxDrag)
                        self.createNewNode(desc, position=(pos.x(), pos.y()))
                        self.view().setFocus(Qt.OtherFocusReason)
                    return True

            if etype == QEvent.GraphicsSceneDragEnter:
                return self.sceneDragEnterEvent(event)
            elif etype == QEvent.GraphicsSceneDragMove:
                return self.sceneDragMoveEvent(event)
            elif etype == QEvent.GraphicsSceneDragLeave:
                return self.sceneDragLeaveEvent(event)
            elif etype == QEvent.GraphicsSceneDrop:
                return self.sceneDropEvent(event)
            elif etype == QEvent.GraphicsSceneMousePress:
                self.__pasteOrigin = event.scenePos()
                return self.sceneMousePressEvent(event)
            elif etype == QEvent.GraphicsSceneMouseMove:
                return self.sceneMouseMoveEvent(event)
            elif etype == QEvent.GraphicsSceneMouseRelease:
                return self.sceneMouseReleaseEvent(event)
            elif etype == QEvent.GraphicsSceneMouseDoubleClick:
                return self.sceneMouseDoubleClickEvent(event)
            elif etype == QEvent.KeyPress:
                return self.sceneKeyPressEvent(event)
            elif etype == QEvent.KeyRelease:
                return self.sceneKeyReleaseEvent(event)
            elif etype == QEvent.GraphicsSceneContextMenu:
                return self.sceneContextMenuEvent(event)

        elif obj is self.__scheme:
            if event.type() == QEvent.WhatsThisClicked:
                # Re post the event
                self.__showHelpFor(event.href())
            elif event.type() == WorkflowEvent.ActivateParentRequest:
                self.window().activateWindow()
                self.window().raise_()

        return super().eventFilter(obj, event)

    def sceneMousePressEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        scene = self.currentScene()
        if scene.user_interaction_handler:
            return False

        pos = event.scenePos()

        anchor_item = scene.item_at(
            pos, items.NodeAnchorItem, buttons=Qt.LeftButton)
        if anchor_item and event.button() == Qt.LeftButton:
            # Start a new link starting at item
            scene.clearSelection()
            handler = interactions.NewLinkAction(self)
            self._setUserInteractionHandler(handler)
            return handler.mousePressEvent(event)

        link_item = scene.item_at(pos, items.LinkItem)
        if link_item and event.button() == Qt.MiddleButton:
            link = self.currentScene().link_for_item(link_item)
            self.removeLink(link)
            event.accept()
            return True
        any_item = scene.item_at(pos)
        # start node name edit on selected clicked
        if sys.platform == "darwin" \
                and event.button() == Qt.LeftButton \
                and isinstance(any_item, items.nodeitem.GraphicsTextEdit) \
                and isinstance(any_item.parentItem(), items.NodeItem):
            node = scene.node_for_item(any_item.parentItem())
            selected = self.selectedNodes()
            if node in selected:
                # deselect all other elements except the node item
                # and start the edit
                for selected_node in selected:
                    selected_node_item = scene.item_for_node(selected_node)
                    selected_node_item.setSelected(selected_node is node)
                self.editNodeTitle(node)
                return True

        if not any_item:
            self.__emptyClickButtons |= event.button()

        if not any_item and event.button() == Qt.LeftButton:
            # Create a RectangleSelectionAction but do not set in on the scene
            # just yet (instead wait for the mouse move event).
            handler = interactions.RectangleSelectionAction(self)
            rval = handler.mousePressEvent(event)
            if rval is True:
                self.__possibleSelectionHandler = handler
            return rval

        if any_item and event.button() == Qt.LeftButton:
            self.__possibleMouseItemsMove = True
            self.__itemsMoving.clear()
            scene.node_item_position_changed.connect(
                self.__onNodePositionChanged
            )
            self.__annotationGeomChanged.mappedObject.connect(
                self.__onAnnotationGeometryChanged
            )

            set_enabled_all(self.__disruptiveActions, False)

        return False

    def sceneMouseMoveEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        scene = self.currentScene()
        if scene.user_interaction_handler:
            return False

        if self.__emptyClickButtons & Qt.LeftButton and \
                event.buttons() & Qt.LeftButton and \
                self.__possibleSelectionHandler:
            # Set the RectangleSelection (initialized in mousePressEvent)
            # on the scene
            handler = self.__possibleSelectionHandler
            self._setUserInteractionHandler(handler)
            self.__possibleSelectionHandler = None
            return handler.mouseMoveEvent(event)

        return False

    def sceneMouseReleaseEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        scene = self.currentScene()
        if scene.user_interaction_handler:
            return False

        if event.button() == Qt.LeftButton and self.__possibleMouseItemsMove:
            self.__possibleMouseItemsMove = False
            scene.node_item_position_changed.disconnect(
                self.__onNodePositionChanged
            )
            self.__annotationGeomChanged.mappedObject.disconnect(
                self.__onAnnotationGeometryChanged
            )

            set_enabled_all(self.__disruptiveActions, True)

            if self.__itemsMoving:
                scene.mouseReleaseEvent(event)
                scheme = self.__scheme
                assert scheme is not None
                stack = self.undoStack()
                stack.beginMacro(self.tr("Move"))
                for scheme_item, (old, new) in self.__itemsMoving.items():
                    if isinstance(scheme_item, Node):
                        command = commands.MoveNodeCommand(
                            scheme, scheme_item, old, new
                        )
                    elif isinstance(scheme_item, BaseSchemeAnnotation):
                        command = commands.AnnotationGeometryChange(
                            scheme, scheme_item, old, new
                        )
                    else:
                        continue

                    stack.push(command)
                stack.endMacro()

                self.__itemsMoving.clear()
                return True
        elif event.button() == Qt.LeftButton:
            self.__possibleSelectionHandler = None

        return False

    def sceneMouseDoubleClickEvent(self, event):
        # type: (QGraphicsSceneMouseEvent) -> bool
        scene = self.currentScene()
        if scene.user_interaction_handler:
            return False

        item = scene.item_at(event.scenePos())
        if not item and self.__quickMenuTriggers & \
                SchemeEditWidget.DoubleClicked:
            # Double click on an empty spot
            # Create a new node using QuickMenu
            action = interactions.NewNodeAction(self)
            with disable_undo_stack_actions(
                    self.__undoAction, self.__redoAction, self.__undoStack):
                action.create_new(event.screenPos())

            event.accept()
            return True

        return False

    def sceneKeyPressEvent(self, event):
        # type: (QKeyEvent) -> bool
        self.__updateOpenWidgetAnchors(event)

        scene = self.currentScene()
        if scene.user_interaction_handler:
            return False

        # If a QGraphicsItem is in text editing mode, don't interrupt it
        focusItem = scene.focusItem()
        if focusItem and isinstance(focusItem, QGraphicsTextItem) and \
                focusItem.textInteractionFlags() & Qt.TextEditable:
            return False

        # If the mouse is not over out view
        if not self.view().underMouse():
            return False

        handler = None
        searchText = ""
        if (event.key() == Qt.Key_Space and \
                self.__quickMenuTriggers & SchemeEditWidget.SpaceKey):
            handler = interactions.NewNodeAction(self)

        elif len(event.text()) and \
                self.__quickMenuTriggers & SchemeEditWidget.AnyKey and \
                is_printable(event.text()[0]):
            handler = interactions.NewNodeAction(self)
            searchText = event.text()

        if handler is not None:
            # Control + Backspace (remove widget action on Mac OSX) conflicts
            # with the 'Clear text' action in the search widget (there might
            # be selected items in the canvas), so we disable the
            # remove widget action so the text editing follows standard
            # 'look and feel'
            with ExitStack() as stack:
                stack.enter_context(disabled(self.__removeSelectedAction))
                stack.enter_context(
                    disable_undo_stack_actions(
                        self.__undoAction, self.__redoAction, self.__undoStack)
                )
                handler.create_new(QCursor.pos(), searchText)

            event.accept()
            return True

        return False

    def sceneKeyReleaseEvent(self, event):
        # type: (QKeyEvent) -> bool
        self.__updateOpenWidgetAnchors(event)
        return False

    def __updateOpenWidgetAnchors(self, event=None):
        if self.__openAnchorsMode == SchemeEditWidget.OpenAnchors.Never:
            return
        mode = self.__openAnchorsMode
        # Open widget anchors on shift. New link action should work during this
        if event:
            shift_down = event.modifiers() == Qt.ShiftModifier
        else:
            shift_down = QApplication.keyboardModifiers() == Qt.ShiftModifier
        if mode == SchemeEditWidget.OpenAnchors.Never:
            opened = False
        elif mode == SchemeEditWidget.OpenAnchors.OnShift:
            opened = shift_down
        else:
            opened = True
        for scene in self.__scenes.values():
            scene.set_widget_anchors_open(opened)

    def sceneContextMenuEvent(self, event):
        # type: (QGraphicsSceneContextMenuEvent) -> bool
        scenePos = event.scenePos()
        globalPos = event.screenPos()

        item = self.currentScene().item_at(scenePos, items.NodeItem)
        if item is not None:
            node = self.currentScene().node_for_item(item)
            actions = []  # type: List[QAction]
            manager = self.widgetManager()
            if manager is not None:
                actions = manager.actions_for_context_menu(node)

            # TODO: Inspect actions for all selected nodes and merge 'same'
            #       actions (by name)
            if actions and len(self.selectedNodes()) == 1:
                # The node has extra actions for the context menu.
                # Copy the default context menu and append the extra actions.
                menu = QMenu(self)
                for a in self.__widgetMenu.actions():
                    menu.addAction(a)
                menu.addSeparator()
                for a in actions:
                    menu.addAction(a)
                menu.setAttribute(Qt.WA_DeleteOnClose)
            else:
                menu = self.__widgetMenu
            menu.popup(globalPos)
            return True

        item = self.currentScene().item_at(scenePos, items.LinkItem)
        if item is not None:
            link = self.currentScene().link_for_item(item)
            self.__linkEnableAction.setChecked(link.enabled)
            self.__contextMenuTarget = link
            self.__linkMenu.popup(globalPos)
            return True

        item = self.currentScene().item_at(scenePos)
        if not item and \
                self.__quickMenuTriggers & SchemeEditWidget.RightClicked:
            action = interactions.NewNodeAction(self)

            with disable_undo_stack_actions(
                    self.__undoAction, self.__redoAction, self.__undoStack):
                action.create_new(globalPos)
            return True

        return False

    def sceneDragEnterEvent(self, event: QGraphicsSceneDragDropEvent) -> bool:
        UNUSED(event)
        delegate = self._userInteractionHandler()
        if delegate is not None:
            return False

        handler = interactions.DropAction(self, dropHandlers=self.__dropHandlers)
        self._setUserInteractionHandler(handler)
        return False

    def sceneDragMoveEvent(self, event: QGraphicsSceneDragDropEvent) -> bool:
        UNUSED(event)
        return False

    def sceneDragLeaveEvent(self, event: QGraphicsSceneDragDropEvent) -> bool:
        UNUSED(event)
        return False

    def sceneDropEvent(self, event: QGraphicsSceneDragDropEvent) -> bool:
        UNUSED(event)
        return False

    def _userInteractionHandler(self) -> Optional[UserInteraction]:
        return self.currentScene().user_interaction_handler

    def _setUserInteractionHandler(self, handler):
        # type: (Optional[UserInteraction]) -> None
        """
        Helper method for setting the user interaction handlers.
        """
        scene = self.currentScene()
        if scene.user_interaction_handler:
            if isinstance(scene.user_interaction_handler,
                          (interactions.ResizeArrowAnnotation,
                           interactions.ResizeTextAnnotation)):
                scene.user_interaction_handler.commit()

            scene.user_interaction_handler.ended.disconnect(
                self.__onInteractionEnded
            )

        if handler:
            handler.ended.connect(self.__onInteractionEnded)
            # Disable actions which could change the model
            set_enabled_all(self.__disruptiveActions, False)

        scene.set_user_interaction_handler(handler)

    def __onInteractionEnded(self):
        # type: () -> None
        self.sender().ended.disconnect(self.__onInteractionEnded)
        set_enabled_all(self.__disruptiveActions, True)
        self.__updateOpenWidgetAnchors()

    def __onSelectionChanged(self):
        # type: () -> None
        nodes = self.selectedNodes()
        annotations = self.selectedAnnotations()
        links = self.selectedLinks()

        self.__renameAction.setEnabled(len(nodes) == 1)
        self.__openSelectedAction.setEnabled(bool(nodes))
        self.__removeSelectedAction.setEnabled(
            bool(nodes or annotations or links)
        )

        self.__helpAction.setEnabled(len(nodes) == 1)
        self.__renameAction.setEnabled(len(nodes) == 1)
        self.__duplicateSelectedAction.setEnabled(bool(nodes))
        self.__copySelectedAction.setEnabled(bool(nodes))
        self.__createMacroAction.setEnabled(len(nodes) >= 2)

        if len(nodes) > 1:
            self.__openSelectedAction.setText(self.tr("Open All"))
        else:
            self.__openSelectedAction.setText(self.tr("Open"))

        if len(nodes) + len(annotations) + len(links) > 1:
            self.__removeSelectedAction.setText(self.tr("Remove All"))
        else:
            self.__removeSelectedAction.setText(self.tr("Remove"))

        focus = self.focusNode()
        if focus is not None and isinstance(focus, SchemeNode):
            desc = focus.description
            tip = whats_this_helper(desc, include_more_link=True)
        else:
            tip = ""

        if tip != self.__quickTip:
            self.__quickTip = tip
            ev = QuickHelpTipEvent("", self.__quickTip,
                                   priority=QuickHelpTipEvent.Permanent)

            QCoreApplication.sendEvent(self, ev)

    def __onLinkActivate(self, item):
        link = self.currentScene().link_for_item(item)
        action = interactions.EditNodeLinksAction(self, link.source_node,
                                                  link.sink_node)
        action.edit_links()

    def __onLinkAdded(self, item: items.LinkItem) -> None:
        item.setFlag(QGraphicsItem.ItemIsSelectable)

    def __onNodeActivate(self, item):
        # type: (items.NodeItem) -> None
        node = self.currentScene().node_for_item(item)
        self.__openNodes([node])

    def __onNodePositionChanged(self, item, pos):
        # type: (items.NodeItem, QPointF) -> None
        node = self.currentScene().node_for_item(item)
        new = (pos.x(), pos.y())
        if node not in self.__itemsMoving:
            self.__itemsMoving[node] = (node.position, new)
        else:
            old, _ = self.__itemsMoving[node]
            self.__itemsMoving[node] = (old, new)

    def __onAnnotationGeometryChanged(self, item):
        # type: (AnnotationItem) -> None
        annot = self.currentScene().annotation_for_item(item)
        if annot not in self.__itemsMoving:
            self.__itemsMoving[annot] = (annot.geometry,
                                         geometry_from_annotation_item(item))
        else:
            old, _ = self.__itemsMoving[annot]
            self.__itemsMoving[annot] = (old,
                                         geometry_from_annotation_item(item))

    def __onAnnotationAdded(self, item):
        # type: (AnnotationItem) -> None
        log.debug("Annotation added (%r)", item)
        item.setFlag(QGraphicsItem.ItemIsSelectable)
        item.setFlag(QGraphicsItem.ItemIsMovable)
        item.setFlag(QGraphicsItem.ItemIsFocusable)

        if isinstance(item, items.ArrowAnnotation):
            pass
        elif isinstance(item, items.TextAnnotation):
            # Make the annotation editable.
            item.setTextInteractionFlags(Qt.TextEditorInteraction)

            self.__editFinishedMapper.setMapping(item, item)
            item.editingFinished.connect(
                self.__editFinishedMapper.map
            )

        self.__annotationGeomChanged.setMapping(item, item)
        item.geometryChanged.connect(
            self.__annotationGeomChanged.map
        )

    def __onAnnotationRemoved(self, item):
        # type: (AnnotationItem) -> None
        log.debug("Annotation removed (%r)", item)
        if isinstance(item, items.ArrowAnnotation):
            pass
        elif isinstance(item, items.TextAnnotation):
            item.editingFinished.disconnect(
                self.__editFinishedMapper.map
            )

        self.__annotationGeomChanged.removeMappings(item)
        item.geometryChanged.disconnect(
            self.__annotationGeomChanged.map
        )

    def __onFocusItemChanged(self, newFocusItem, oldFocusItem):
        # type: (Optional[QGraphicsItem], Optional[QGraphicsItem]) -> None
        if isinstance(oldFocusItem, items.annotationitem.Annotation):
            self.__endControlPointEdit()
        if isinstance(newFocusItem, items.annotationitem.Annotation):
            if not self._userInteractionHandler():
                self.__startControlPointEdit(newFocusItem)

    def __onEditingFinished(self, item):
        # type: (items.TextAnnotation) -> None
        """
        Text annotation editing has finished.
        """
        annot = self.currentScene().annotation_for_item(item)
        assert isinstance(annot, SchemeTextAnnotation)
        content_type = item.contentType()
        content = item.content()

        if annot.text != content or annot.content_type != content_type:
            assert self.__scheme is not None
            self.__undoStack.push(
                commands.TextChangeCommand(
                    self.__scheme, annot,
                    annot.text, annot.content_type,
                    content, content_type
                )
            )

    def __toggleNewArrowAnnotation(self, checked):
        # type: (bool) -> None
        if self.__newTextAnnotationAction.isChecked():
            # Uncheck the text annotation action if needed.
            self.__newTextAnnotationAction.setChecked(not checked)

        action = self.__newArrowAnnotationAction

        if not checked:
            # The action was unchecked (canceled by the user)
            handler = self._userInteractionHandler()
            if isinstance(handler, interactions.NewArrowAnnotation):
                # Cancel the interaction and restore the state
                handler.ended.disconnect(action.toggle)
                handler.cancel(interactions.UserInteraction.UserCancelReason)
                log.info("Canceled new arrow annotation")

        else:
            handler = interactions.NewArrowAnnotation(self)
            checked_action = self.__arrowColorActionGroup.checkedAction()
            handler.setColor(checked_action.data())

            handler.ended.connect(action.toggle)

            self._setUserInteractionHandler(handler)

    def __onFontSizeTriggered(self, action):
        # type: (QAction) -> None
        if not self.__newTextAnnotationAction.isChecked():
            # When selecting from the (font size) menu the 'Text'
            # action does not get triggered automatically.
            self.__newTextAnnotationAction.trigger()
        else:
            # Update the preferred font on the interaction handler.
            handler = self._userInteractionHandler()
            if isinstance(handler, interactions.NewTextAnnotation):
                handler.setFont(action.font())

    def __toggleNewTextAnnotation(self, checked):
        # type: (bool) -> None
        if self.__newArrowAnnotationAction.isChecked():
            # Uncheck the arrow annotation if needed.
            self.__newArrowAnnotationAction.setChecked(not checked)

        action = self.__newTextAnnotationAction

        if not checked:
            # The action was unchecked (canceled by the user)
            handler = self._userInteractionHandler()
            if isinstance(handler, interactions.NewTextAnnotation):
                # cancel the interaction and restore the state
                handler.ended.disconnect(action.toggle)
                handler.cancel(interactions.UserInteraction.UserCancelReason)
                log.info("Canceled new text annotation")

        else:
            handler = interactions.NewTextAnnotation(self)
            checked_action = self.__fontActionGroup.checkedAction()
            handler.setFont(checked_action.font())

            handler.ended.connect(action.toggle)

            self._setUserInteractionHandler(handler)

    def __onArrowColorTriggered(self, action):
        # type: (QAction) -> None
        if not self.__newArrowAnnotationAction.isChecked():
            # When selecting from the (color) menu the 'Arrow'
            # action does not get triggered automatically.
            self.__newArrowAnnotationAction.trigger()
        else:
            # Update the preferred color on the interaction handler
            handler = self._userInteractionHandler()
            if isinstance(handler, interactions.NewArrowAnnotation):
                handler.setColor(action.data())

    def __onRenameAction(self):
        # type: () -> None
        """
        Rename was requested for the selected widget.
        """
        selected = self.selectedNodes()
        if len(selected) == 1:
            self.editNodeTitle(selected[0])

    def __onHelpAction(self):
        # type: () -> None
        """
        Help was requested for the selected widget.
        """
        nodes = self.selectedNodes()
        help_url = None
        if len(nodes) == 1 and isinstance(nodes[0], SchemeNode):
            node = nodes[0]
            desc = node.description

            help_url = "help://search?" + urlencode({"id": desc.qualified_name})
            self.__showHelpFor(help_url)

    def __showHelpFor(self, help_url):
        # type: (str) -> None
        """
        Show help for an "help" url.
        """
        # Notify the parent chain and let them respond
        ev = QWhatsThisClickedEvent(help_url)
        handled = QCoreApplication.sendEvent(self, ev)

        if not handled:
            message_information(
                self.tr("Sorry there is no documentation available for "
                        "this widget."),
                parent=self)

    def __toggleLinkEnabled(self, enabled):
        # type: (bool) -> None
        """
        Link 'enabled' state was toggled in the context menu.
        """
        if self.__contextMenuTarget:
            link = self.__contextMenuTarget
            command = commands.SetAttrCommand(
                link, "enabled", enabled, name=self.tr("Set enabled"),
            )
            self.__undoStack.push(command)

    def __linkRemove(self):
        # type: () -> None
        """
        Remove link was requested from the context menu.
        """
        if self.__contextMenuTarget:
            self.removeLink(self.__contextMenuTarget)

    def __linkReset(self):
        # type: () -> None
        """
        Link reset from the context menu was requested.
        """
        if self.__contextMenuTarget:
            link = self.__contextMenuTarget
            action = interactions.EditNodeLinksAction(
                self, link.source_node, link.sink_node
            )
            action.edit_links()

    def __nodeInsert(self):
        # type: () -> None
        """
        Node insert was requested from the context menu.
        """
        if not self.__contextMenuTarget:
            return

        original_link = self.__contextMenuTarget
        source_node = original_link.source_node
        sink_node = original_link.sink_node

        def filterFunc(index):
            desc = index.data(QtWidgetRegistry.WIDGET_DESC_ROLE)
            if isinstance(desc, WidgetDescription):
                return can_insert_node(desc, original_link)
            else:
                return False

        x = (source_node.position[0] + sink_node.position[0]) / 2
        y = (source_node.position[1] + sink_node.position[1]) / 2

        menu = self.quickMenu()
        menu.setFilterFunc(filterFunc)
        menu.setSortingFunc(None)

        view = self.view()
        try:
            action = menu.exec(view.mapToGlobal(view.mapFromScene(QPointF(x, y))))
        finally:
            menu.setFilterFunc(None)

        if action:
            item = action.property("item")
            desc = item.data(QtWidgetRegistry.WIDGET_DESC_ROLE)
        else:
            return

        if can_insert_node(desc, original_link):
            statistics = self.usageStatistics()
            statistics.begin_insert_action(False, original_link)
            new_node = self.newNodeHelper(desc, position=(x, y))
            self.insertNode(new_node, original_link)
        else:
            log.info("Cannot insert node: links not possible.")

    def __duplicateSelected(self):
        # type: () -> None
        """
        Duplicate currently selected nodes.
        """
        nodedups, linkdups = self.__copySelected()
        if not nodedups:
            return

        pos = nodes_top_left(nodedups)
        self.__paste(nodedups, linkdups, pos + DuplicateOffset,
                     commandname=self.tr("Duplicate"))

    def __copyToClipboard(self):
        """
        Copy currently selected nodes to system clipboard.
        """
        cb = QApplication.clipboard()
        selected = self.__copySelected()
        nodes, links = selected
        if not nodes:
            return
        s = Scheme()
        for n in nodes:
            s.add_node(n)
        for e in links:
            s.add_link(e)
        buff = io.BytesIO()
        try:
            s.save_to(buff, pickle_fallback=True)
        except Exception:
            log.error("copyToClipboard:", exc_info=True)
            QApplication.beep()
            return
        mime = QMimeData()
        mime.setData(MimeTypeWorkflowFragment, buff.getvalue())
        cb.setMimeData(mime)
        self.__pasteOrigin = nodes_top_left(nodes) + DuplicateOffset

    def __updatePasteActionState(self):
        self.__pasteAction.setEnabled(
            clipboard_has_format(MimeTypeWorkflowFragment)
        )

    def __copySelected(self):
        """
        Return a deep copy of currently selected nodes and links between them.
        """
        scheme = self.scheme()
        if scheme is None:
            return [], []

        # ensure up to date node properties (settings)
        scheme.sync_node_properties()

        # original nodes and links
        nodes = self.selectedNodes()
        links = [link for link in scheme.links
                 if link.source_node in nodes and
                 link.sink_node in nodes]

        # deepcopied nodes and links
        nodedups = [copy_node(node) for node in nodes]
        node_to_dup = dict(zip(nodes, nodedups))
        linkdups = [copy_link(link, source=node_to_dup[link.source_node],
                              sink=node_to_dup[link.sink_node])
                    for link in links]

        return nodedups, linkdups

    def __pasteFromClipboard(self):
        """Paste a workflow part from system clipboard."""
        buff = clipboard_data(MimeTypeWorkflowFragment)
        if buff is None:
            return
        sch = Scheme()
        try:
            sch.load_from(io.BytesIO(buff), registry=self.__registry, )
        except Exception:
            log.error("pasteFromClipboard:", exc_info=True)
            QApplication.beep()
            return
        self.__paste(sch.nodes, sch.links, self.__pasteOrigin)
        self.__pasteOrigin = self.__pasteOrigin + DuplicateOffset

    def __paste(self, nodedups, linkdups, pos: Optional[QPointF] = None,
                commandname=None):
        """
        Paste nodes and links to canvas. Arguments are expected to be duplicated nodes/links.
        """
        scheme = self.scheme()
        if scheme is None:
            return

        # find unique names for new nodes
        allnames = {node.title for node in scheme.nodes}

        for nodedup in nodedups:
            nodedup.title = uniquify(
                remove_copy_number(nodedup.title), allnames,
                pattern="{item} ({_})", start=1
            )
            allnames.add(nodedup.title)

        if pos is not None:
            # top left of nodedups brect
            origin = nodes_top_left(nodedups)
            delta = pos - origin
            # move nodedups to be relative to pos
            for nodedup in nodedups:
                nodedup.position = (
                    nodedup.position[0] + delta.x(),
                    nodedup.position[1] + delta.y(),
                )
        if commandname is None:
            commandname = self.tr("Paste")
        # create nodes, links
        command = UndoCommand(commandname)
        macrocommands = []
        for nodedup in nodedups:
            macrocommands.append(
                commands.AddNodeCommand(scheme, nodedup, self.__root, parent=command))
        for linkdup in linkdups:
            macrocommands.append(
                commands.AddLinkCommand(scheme, linkdup, self.__root, parent=command))

        statistics = self.usageStatistics()
        statistics.begin_action(UsageStatistics.Duplicate)
        self.__undoStack.push(command)
        scene = self.currentScene()

        # deselect selected
        selected = scene.selectedItems()
        for item in selected:
            item.setSelected(False)

        # select pasted
        for node in nodedups:
            item = scene.item_for_node(node)
            item.setSelected(True)

    def __createMacro(self, nodes: List['Node']) -> MetaNode:
        assert nodes
        model = self.__scheme
        parent = self.__root
        assert model is not None
        assert parent is not None
        res = prepare_macro_patch(parent, nodes)
        stack = self.__undoStack
        stack.beginMacro(self.tr("Create Macro Node"))
        for link in res.removed_links:
            stack.push(commands.RemoveLinkCommand(model, link, parent))
        for node in res.nodes:
            stack.push(commands.RemoveNodeCommand(model, node, parent))
        macro = res.macro_node
        stack.push(commands.AddNodeCommand(model, macro, parent))
        for node in res.nodes:
            stack.push(commands.AddNodeCommand(model, node, macro))
        for link in res.links:
            stack.push(commands.AddLinkCommand(model, link, macro))
        for link in itertools.chain(res.output_links, res.input_links):
            stack.push(commands.AddLinkCommand(model, link, parent))
        stack.endMacro()
        return macro

    def createMacroFromSelection(self):
        """Create a macro node from the current selection."""
        selection = self.selectedNodes()
        if not selection:
            return
        macro = self.__createMacro(selection)
        scene = self.currentScene()
        item = scene.item_for_node(macro)
        if item is not None:
            scene.clearSelection()
            item.setSelected(True)
            self.editNodeTitle(macro)

    def __startControlPointEdit(self, item):
        # type: (items.annotationitem.Annotation) -> None
        """
        Start a control point edit interaction for `item`.
        """
        if isinstance(item, items.ArrowAnnotation):
            handler = interactions.ResizeArrowAnnotation(self)
        elif isinstance(item, items.TextAnnotation):
            handler = interactions.ResizeTextAnnotation(self)
        else:
            log.warning("Unknown annotation item type %r" % item)
            return

        handler.editItem(item)
        self._setUserInteractionHandler(handler)

        log.info("Control point editing started (%r)." % item)

    def __endControlPointEdit(self):
        # type: () -> None
        """
        End the current control point edit interaction.
        """
        handler = self._userInteractionHandler()
        if isinstance(handler, (interactions.ResizeArrowAnnotation,
                                interactions.ResizeTextAnnotation)) and \
                not handler.isFinished() and not handler.isCanceled():
            handler.commit()
            handler.end()

            log.info("Control point editing finished.")

    def __signalManagerStateChanged(self, state):
        # type: (RuntimeState) -> None
        if state == RuntimeState.Running:
            role = QPalette.Base
        else:
            role = QPalette.Window
        self.__view.viewport().setBackgroundRole(role)

    def __reset_window_group_menu(self):
        group = self.__windowGroupsActionGroup
        menu = self.__windowGroupsAction.menu()
        # remove old actions
        actions = group.actions()
        for a in actions:
            group.removeAction(a)
            menu.removeAction(a)
            a.deleteLater()

        sep = menu.findChild(QAction, "groups-separator")

        workflow = self.__scheme
        if workflow is None:
            return

        presets = workflow.window_group_presets()

        for g in presets:
            a = QAction(g.name, menu)
            a.setShortcut(
                QKeySequence("Meta+P, Ctrl+{}"
                             .format(len(group.actions()) + 1))
            )
            a.setData(g)
            group.addAction(a)
            menu.insertAction(sep, a)

    def __saveWindowGroup(self):
        # type: () -> None
        """Run a 'Save Window Group' dialog"""
        workflow = self.__scheme
        manager = self.__widgetManager
        if manager is None or workflow is None:
            return
        state = manager.save_window_state()
        presets = workflow.window_group_presets()
        items = [g.name for g in presets]
        default = [i for i, g in enumerate(presets) if g.default]
        dlg = SaveWindowGroup(self, windowTitle="Save Group as...")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setItems(items)
        if default:
            dlg.setDefaultIndex(default[0])

        def store_group():
            text = dlg.selectedText()
            default = dlg.isDefaultChecked()
            try:
                idx = items.index(text)
            except ValueError:
                idx = -1
            newpresets = [copy.copy(g) for g in presets]  # shallow copy
            newpreset = Scheme.WindowGroup(text, default, state)
            if idx == -1:
                # new group slot
                newpresets.append(newpreset)
            else:
                newpresets[idx] = newpreset

            if newpreset.default:
                idx_ = idx if idx >= 0 else len(newpresets) - 1
                for g in newpresets[:idx_] + newpresets[idx_ + 1:]:
                    g.default = False

            if idx == -1:
                text = self.tr("Store Window Group")
            else:
                text = self.tr("Update Window Group")

            self.__undoStack.push(
                commands.SetWindowGroupPresets(workflow, newpresets, text=text)
            )
        dlg.accepted.connect(store_group)
        dlg.show()
        dlg.raise_()

    def __activateWindowGroup(self, action):
        # type: (QAction) -> None
        data = action.data()  # type: Scheme.WindowGroup
        wm = self.__widgetManager
        if wm is not None:
            wm.activate_window_group(data)

    def __clearWindowGroups(self):
        # type: () -> None
        workflow = self.__scheme
        if workflow is None:
            return
        self.__undoStack.push(
            commands.SetWindowGroupPresets(
                workflow, [], text=self.tr("Delete All Window Groups"))
        )

    def __raiseToFont(self):
        # Raise current visible widgets to front
        wm = self.__widgetManager
        if wm is not None:
            wm.raise_widgets_to_front()

    def activateDefaultWindowGroup(self):
        # type: () -> bool
        """
        Activate the default window group if one exists.

        Return `True` if a default group exists and was activated; `False` if
        not.
        """
        for action in self.__windowGroupsActionGroup.actions():
            g = action.data()
            if g.default:
                action.trigger()
                return True
        return False

    def widgetManager(self):
        # type: () -> Optional[WidgetManager]
        """
        Return the widget manager.
        """
        return self.__widgetManager


def geometry_from_annotation_item(item):
    if isinstance(item, items.ArrowAnnotation):
        line = item.line()
        p1 = item.mapToScene(line.p1())
        p2 = item.mapToScene(line.p2())
        return ((p1.x(), p1.y()), (p2.x(), p2.y()))
    elif isinstance(item, items.TextAnnotation):
        geom = item.geometry()
        return (geom.x(), geom.y(), geom.width(), geom.height())


def mouse_drag_distance(event, button=Qt.LeftButton):
    # type: (QGraphicsSceneMouseEvent, Qt.MouseButton) -> float
    """
    Return the (manhattan) distance between the mouse position
    when the `button` was pressed and the current mouse position.
    """
    diff = (event.buttonDownScreenPos(button) - event.screenPos())
    return diff.manhattanLength()


def set_enabled_all(objects, enable):
    # type: (Iterable[Any], bool) -> None
    """
    Set `enabled` properties on all objects (objects with `setEnabled` method).
    """
    for obj in objects:
        obj.setEnabled(enable)


def node_properties(scheme):
    # type: (Scheme) -> Dict[str, Dict[str, Any]]
    scheme.sync_node_properties()
    return {
        node: dict(node.properties) for node in scheme.all_nodes()
    }


def can_insert_node(new_node_desc, original_link):
    # type: (WidgetDescription, Link) -> bool
    return any(any(scheme.compatible_channels(output, input)
                   for input in new_node_desc.inputs)
               for output in original_link.source_node.output_channels()) and \
           any(any(scheme.compatible_channels(output, input)
                   for output in new_node_desc.outputs)
               for input in original_link.sink_node.input_channels())


def remove_copy_number(name):
    """
    >>> remove_copy_number("foo (1)")
    foo
    """
    match = re.search(r"\s+\(\d+\)\s*$", name)
    if match:
        return name[:match.start()]
    return name


def copy_node(node):
    # type: (SchemeNode) -> SchemeNode
    desc = node.description
    newnode = SchemeNode(
        desc, node.title, position=node.position,
        properties=copy.deepcopy(node.properties)
    )

    for ic in node.input_channels()[len(desc.inputs):]:
        newnode.add_input_channel(ic)
    for oc in node.output_channels()[len(desc.outputs):]:
        newnode.add_output_channel(oc)
    return newnode


def copy_link(link, source=None, sink=None):
    # type: (Link, Optional[SchemeNode], Optional[SchemeNode]) -> Link
    source = link.source_node if source is None else source
    sink = link.sink_node if sink is None else sink
    return Link(
        source, link.source_channel,
        sink, link.sink_channel,
        enabled=link.enabled,
        properties=copy.deepcopy(link.properties))


def nodes_top_left(nodes):
    # type: (List[SchemeNode]) -> QPointF
    """Return the top left point of bbox containing all the node positions."""
    return QPointF(
        min((n.position[0] for n in nodes), default=0),
        min((n.position[1] for n in nodes), default=0)
    )

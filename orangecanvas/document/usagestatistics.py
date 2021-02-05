import enum
import itertools
from datetime import datetime
import platform
import json
import logging
import os
from typing import List

from AnyQt.QtCore import QCoreApplication, QSettings

from orangecanvas import config
from orangecanvas.scheme import SchemeNode, SchemeLink, Scheme

log = logging.getLogger(__name__)


class EventType(enum.IntEnum):
    NodeAdd = 0
    NodeRemove = 1
    LinkAdd = 2
    LinkRemove = 3


class ActionType(enum.IntEnum):
    Unclassified = 0
    ToolboxClick = 1
    ToolboxDrag = 2
    QuickMenu = 3
    ExtendFromSource = 4
    ExtendFromSink = 5
    InsertDrag = 6
    InsertMenu = 7
    Undo = 8
    Redo = 9
    Duplicate = 10
    Load = 11


class UsageStatistics:
    """
    Tracks usage statistics if enabled (is disabled by default).

    Data is tracked and stored in application data directory in
    'usage-statistics.json' file.

    It is the application's responsibility to ask for permission and
    appropriately handle the collected statistics.

    Data tracked per canvas session:
        date,
        application version,
        operating system,
        anaconda boolean,
        UUID (in Orange3),
        a sequence of actions of type ActionType

    An action consists of one or more events of type EventType.
    Events refer to nodes according to a unique integer ID.
    Each node is also associated with a widget name, assigned in a NodeAdd event.
    Link events also reference corresponding source/sink channel names.

    Some actions carry metadata (e.g. search query for QuickMenu, Extend).

    Parameters
    ----------
    parent: SchemeEditWidget
    """
    _is_enabled = False
    statistics_sessions = []
    last_search_query = None
    source_open = False
    sink_open = False

    Unclassified, ToolboxClick, ToolboxDrag, QuickMenu, ExtendFromSink, ExtendFromSource, \
    InsertDrag, InsertMenu, Undo, Redo, Duplicate, Load \
        = list(ActionType)

    def __init__(self, parent):
        self.parent = parent

        self._actions = []
        self._events = []
        self._widget_ids = {}
        self._id_iter = itertools.count()

        self._action_type = ActionType.Unclassified
        self._metadata = None

        UsageStatistics.statistics_sessions.append(self)

    @classmethod
    def is_enabled(cls) -> bool:
        """
        Returns
        -------
        enabled : bool
            Is usage collection enabled.
        """
        return cls._is_enabled

    @classmethod
    def set_enabled(cls, state: bool) -> None:
        """
        Enable/disable usage collection.

        Parameters
        ----------
        state : bool
        """
        if cls._is_enabled == state:
            return

        cls._is_enabled = state
        log.info("{} usage statistics tracking".format(
            "Enabling" if state else "Disabling"
        ))
        for session in UsageStatistics.statistics_sessions:
            if state:
                # log current scheme state after enabling of statistics
                scheme = session.parent.scheme()
                session.log_scheme(scheme)
            else:
                session.drop_statistics()

    def begin_action(self, action_type):
        """
        Sets the type of action that will be logged upon next call to a log method.

        Each call to begin_action() should be matched with a call to end_action().

        Parameters
        ----------
        action_type : ActionType
        """
        if not self.is_enabled():
            return

        if self._action_type != self.Unclassified:
            raise ValueError("Tried to set " + str(action_type) + \
                             " but " + str(self._action_type) + " was already set.")

        self._prepare_action(action_type)

    def begin_extend_action(self, from_sink, extended_widget):
        """
        Sets the type of action to widget extension in the specified direction,
        noting the extended widget and query.

        Each call to begin_extend_action() should be matched with a call to end_action().

        Parameters
        ----------
        from_sink : bool
        extended_widget : SchemeNode
        """
        if not self.is_enabled():
            return

        if self._events:
            log.error("Tried to start extend action while current action already has events")
            return

        # set action type
        if from_sink:
            action_type = ActionType.ExtendFromSink
        else:
            action_type = ActionType.ExtendFromSource

        # set metadata
        if extended_widget not in self._widget_ids:
            log.error("Attempted to extend widget before it was logged. No action type was set.")
            return
        extended_id = self._widget_ids[extended_widget]

        metadata = {"Extended Widget": extended_id}

        self._prepare_action(action_type, metadata)

    def begin_insert_action(self, via_drag, original_link):
        """
        Sets the type of action to widget insertion via the specified way,
        noting the old link's source and sink widgets.

        Each call to begin_insert_action() should be matched with a call to end_action().

        Parameters
        ----------
        via_drag : bool
        original_link : SchemeLink
        """
        if not self.is_enabled():
            return

        if self._events:
            log.error("Tried to start insert action while current action already has events")
            return

        source_widget = original_link.source_node
        sink_widget = original_link.sink_node

        # set action type
        if via_drag:
            action_type = ActionType.InsertDrag
        else:
            action_type = ActionType.InsertMenu

        # set metadata
        if source_widget not in self._widget_ids or sink_widget not in self._widget_ids:
            log.error("Attempted to log insert action between unknown widgets. "
                      "No action was logged.")
            self._clear_action()
            return
        src_id, sink_id = self._widget_ids[source_widget], self._widget_ids[sink_widget]

        metadata = {"Source Widget": src_id,
                    "Sink Widget": sink_id}

        self._prepare_action(action_type, metadata)

    def _prepare_action(self, action_type, metadata=None):
        """
        Sets the type of action and metadata that will be logged upon next call to a log method.

        Parameters
        ----------
        action_type : ActionType
        metadata : Dict[str, Any]
        """
        self._action_type = action_type
        self._metadata = metadata

    def end_action(self):
        """
        Ends the started action, concatenating the relevant events and adding it to
        the list of actions.
        """
        if not self.is_enabled():
            return

        if not self._events:
            log.info("End action called but no events were logged.")
            self._clear_action()
            return

        action = {
            "Type": self._action_type,
            "Events": self._events
        }

        # add metadata
        if self._metadata:
            action.update(self._metadata)

        # add search query if relevant
        if self._action_type in {ActionType.ExtendFromSource, ActionType.ExtendFromSink,
                                 ActionType.QuickMenu}:
            action["Query"] = self.last_search_query

        self._actions.append(action)
        self._clear_action()

    def _clear_action(self):
        """
        Clear the current action.
        """
        self._events = []
        self._action_type = ActionType.Unclassified
        self._metadata = None
        self.last_search_query = ""

    def log_node_add(self, widget):
        """
        Logs an node addition action, based on the currently set action type.

        Parameters
        ----------
        widget : SchemeNode
        """
        if not self.is_enabled():
            return

        # get or generate id for widget
        if widget in self._widget_ids:
            widget_id = self._widget_ids[widget]
        else:
            widget_id = next(self._id_iter)
            self._widget_ids[widget] = widget_id

        event = {
            "Type": EventType.NodeAdd,
            "Widget Name": widget.description.id,
            "Widget": widget_id
        }

        self._events.append(event)

    def log_node_remove(self, widget):
        """
        Logs an node removal action.

        Parameters
        ----------
        widget : SchemeNode
        """
        if not self.is_enabled():
            return

        # get id for widget
        if widget not in self._widget_ids:
            log.error("Attempted to log node removal before its addition. No action was logged.")
            self._clear_action()
            return
        widget_id = self._widget_ids[widget]

        event = {
            "Type": EventType.NodeRemove,
            "Widget": widget_id
        }

        self._events.append(event)

    def log_link_add(self, link):
        """
        Logs a link addition action.

        Parameters
        ----------
        link : SchemeLink
        """
        if not self.is_enabled():
            return

        self._log_link(EventType.LinkAdd, link)

    def log_link_remove(self, link):
        """
        Logs a link removal action.

        Parameters
        ----------
        link : SchemeLink
        """
        if not self.is_enabled():
            return

        self._log_link(EventType.LinkRemove, link)

    def _log_link(self, action_type, link):
        source_widget = link.source_node
        sink_widget = link.sink_node

        # get id for widgets
        if source_widget not in self._widget_ids or sink_widget not in self._widget_ids:
            log.error("Attempted to log link action between unknown widgets. No action was logged.")
            self._clear_action()
            return

        src_id, sink_id = self._widget_ids[source_widget], self._widget_ids[sink_widget]

        event = {
            "Type": action_type,
            "Source Widget": src_id,
            "Sink Widget": sink_id,
            "Source Channel": link.source_channel.name,
            "Sink Channel": link.sink_channel.name,
            "Source Open": UsageStatistics.source_open,
            "Sink Open:": UsageStatistics.sink_open,
        }

        self._events.append(event)

    def log_scheme(self, scheme):
        """
        Log all nodes and links in a scheme.

        Parameters
        ----------
        scheme : Scheme
        """
        if not self.is_enabled():
            return

        if not scheme or not scheme.nodes:
            return

        self.begin_action(ActionType.Load)

        # first log nodes
        for node in scheme.nodes:
            self.log_node_add(node)

        # then log links
        for link in scheme.links:
            self.log_link_add(link)

        self.end_action()

    def drop_statistics(self):
        """
        Clear all data in the statistics session.
        """
        self._actions = []
        self._widget_ids = {}
        self._id_iter = itertools.count()

    def write_statistics(self):
        """
        Write the statistics session to file, and clear it.
        """
        if not self.is_enabled():
            return

        statistics_path = self.filename()
        statistics = {
            "Date": str(datetime.now().date()),
            "Application Version": QCoreApplication.applicationVersion(),
            "Operating System": platform.system() + " " + platform.release(),
            "Launch Count": QSettings().value('startup/launch-count', 0, type=int),
            "Session": self._actions
        }

        if os.path.isfile(statistics_path):
            with open(statistics_path) as f:
                data = json.load(f)
        else:
            data = []

        data.append(statistics)

        with open(statistics_path, 'w') as f:
            json.dump(data, f)

        self.drop_statistics()

    def close(self):
        """
        Close statistics session, effectively not updating it upon
        toggling statistics tracking.
        """
        UsageStatistics.statistics_sessions.remove(self)

    @staticmethod
    def set_last_search_query(query):
        if not UsageStatistics.is_enabled():
            return

        UsageStatistics.last_search_query = query

    @staticmethod
    def set_source_anchor_open(is_open):
        if not UsageStatistics.is_enabled():
            return

        UsageStatistics.source_open = is_open

    @staticmethod
    def set_sink_anchor_open(is_open):
        if not UsageStatistics.is_enabled():
            return

        UsageStatistics.sink_open = is_open

    @staticmethod
    def filename() -> str:
        """
        Return the filename path where the statistics are saved
        """
        return os.path.join(config.data_dir(), "usage-statistics.json")

    @staticmethod
    def load() -> 'List[dict]':
        """
        Load and return the usage statistics data.

        Returns
        -------
        data : dict
        """
        if not UsageStatistics.is_enabled():
            return []
        try:
            with open(UsageStatistics.filename(), "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, PermissionError, IsADirectoryError,
                UnicodeDecodeError, json.JSONDecodeError):
            return []

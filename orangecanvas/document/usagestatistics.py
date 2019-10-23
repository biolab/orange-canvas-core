import enum
import sys
from datetime import datetime
import platform
import json
import logging
import os
from typing import List

import requests

from AnyQt.QtCore import QCoreApplication, QSettings

from orangecanvas import config

log = logging.getLogger(__name__)


class ActionType(enum.IntEnum):
    Invalid = -1
    NodeAddClick = 0
    NodeAddDrag = 1
    NodeAddMenu = 2
    NodeAddInsertDrag = 3
    NodeAddInsertMenu = 4
    NodeAddExtendFromSink = 5
    NodeAddExtendFromSource = 6
    NodeRemove = 7
    LinkAdd = 8
    LinkRemove = 9
    LinkEdit = 10  # ends up transformed into LinkAdd and LinkRemove events


class UsageStatistics:
    """
    Tracks usage statistics if enabled (is disabled by default).

    Data is tracked and stored in application data directory in
    'usage-statistics.json' file.

    It is the application's responsibility to ask for permission and
    appropriately handle the collected statistics.

    In certain situations it is not simple to discern user-intended actions
    from ones done automatically. For this purpose ActionType is employed,
    set when the user explicitly performs an action.

    The stored action type is automatically cleared after node actions,
    but should be manually cleared for link actions with the clear_action_type() method.

    Data tracked per canvas session:
        date,
        application version,
        operating system,
        anaconda boolean,
        UUID,
        a sequence of the following actions:
            node addition,
            node removal,
            link addition,
            link removal
    """
    _is_enabled = False

    Invalid, NodeAddClick, NodeAddDrag, NodeAddMenu, NodeAddInsertDrag, NodeAddInsertMenu, \
    NodeAddExtendFromSink, NodeAddExtendFromSource, NodeRemove, LinkAdd, LinkRemove, LinkEdit \
        = list(ActionType)

    last_search_query = None

    def __init__(self):
        self._actions = []
        self._action_type = UsageStatistics.Invalid

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
        cls._is_enabled = state
        log.info("{} usage statistics tracking".format(
            "Enabling" if state else "Disabling"
        ))

    def log_node_add(self, widget_name, extended_widget=None):
        """
        Logs an node addition action, based on the currently set action type.

        Parameters
        ----------
        widget_name : str
        extended_widget : str
        """
        if not self.is_enabled():
            return

        node_add_action_types = {self.NodeAddClick, self.NodeAddDrag, self.NodeAddMenu,
                                 self.NodeAddInsertDrag, self.NodeAddInsertMenu,
                                 self.NodeAddExtendFromSink, self.NodeAddExtendFromSource}

        if self._action_type not in node_add_action_types:
            log.info("Invalid action type registered for node addition logging. "
                     "No action was logged.")
            return

        action = {
            "Type": self._action_type,
            "Widget Name": widget_name,
        }

        if self._action_type == UsageStatistics.NodeAddMenu:
            action["Query"] = UsageStatistics.last_search_query

        elif self._action_type == UsageStatistics.NodeAddExtendFromSink or \
                self._action_type == UsageStatistics.NodeAddExtendFromSource:
            action["Extended Widget"] = extended_widget
            action["Query"] = UsageStatistics.last_search_query

        elif self._action_type == UsageStatistics.LinkAdd or \
                self._action_type == UsageStatistics.LinkRemove:
            action["Connected Widget"] = extended_widget

        self._action_type = UsageStatistics.Invalid
        self._actions.append(action)

    def log_node_remove(self, widget_name):
        """
        Logs an node removal action.

        Parameters
        ----------
        widget_name : str
        """
        if not self.is_enabled():
            return

        if self._action_type is not UsageStatistics.NodeRemove:
            log.info("Invalid action type registered for node removal logging. "
                     "No action was logged.")
            return

        action = {
            "Type": self._action_type,
            "Widget Name": widget_name
        }

        self._action_type = UsageStatistics.Invalid
        self._actions.append(action)

    def log_link_add(self, source_widget, sink_widget, source_channel, sink_channel):
        """
        Logs an link addition action.

        Parameters
        ----------
        source_widget : str
        sink_widget : str
        source_channel : str
        sink_channel : str
        """
        if not self.is_enabled():
            return

        if self._action_type not in {UsageStatistics.LinkAdd, UsageStatistics.LinkEdit}:
            log.info("Invalid action type registered for link add logging. "
                     "No action was logged.")
            return

        self._log_link(UsageStatistics.LinkAdd, source_widget, sink_widget, source_channel,
                       sink_channel)

    def log_link_remove(self, source_widget, sink_widget, source_channel, sink_channel):
        """
        Logs an link removal action.

        Parameters
        ----------
        source_widget : str
        sink_widget : str
        source_channel : str
        sink_channel : str
        """
        if not self.is_enabled():
            return

        if self._action_type not in {UsageStatistics.LinkRemove, UsageStatistics.LinkEdit}:
            log.info("Invalid action type registered for link remove logging. "
                     "No action was logged.")
            return

        self._log_link(UsageStatistics.LinkRemove, source_widget, sink_widget, source_channel,
                       sink_channel)

    def _log_link(self, action_type, source_widget, sink_widget, source_channel, sink_channel):
        action = {
            "Type": action_type,
            "Source Widget": source_widget,
            "Sink Widget": sink_widget,
            "Source Channel": source_channel,
            "Sink Channel": sink_channel
        }

        self._actions.append(action)

    def set_action_type(self, action_type):
        """
        Sets the type of action that will be logged upon next call to log_action.

        Parameters
        ----------
        action_type : ActionType
        """
        self._action_type = action_type

    def clear_action_type(self):
        """
        Clear the currently set action type by setting it to Invalid.
        """
        self._action_type = UsageStatistics.Invalid

    def filename(self) -> str:
        """
        Return the filename path where the statistics are saved
        """
        return os.path.join(config.data_dir(), "usage-statistics.json")

    def load(self) -> 'List[dict]':
        """
        Load and return the usage statistics data.

        Returns
        -------
        data : dict
        """
        if not self.is_enabled():
            return []
        try:
            with open(self.filename(), "r", encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, PermissionError, IsADirectoryError,
                UnicodeDecodeError, json.JSONDecodeError):
            return []

    def send_statistics(self, url: str) -> None:
        """
        Send the statistics to the remote at `url`.

        The contents are send via POST file upload (multipart/form-data)

        Does nothing if not enabled.

        Parameters
        ----------
        url : str
        """
        if self.is_enabled():
            data = self.load()
            try:
                r = requests.post(url, files={'file': json.dumps(data)})
                if r.status_code != 200:
                    log.warning("Error communicating with server while attempting to send "
                                "usage statistics.")
                    return
                # success - wipe statistics file
                log.info("Usage statistics sent.")
                with open(self.filename(), 'w', encoding="utf-8") as f:
                    json.dump([], f)
            except (ConnectionError, requests.exceptions.RequestException):
                log.warning("Connection error while attempting to send usage statistics.")
            except Exception:
                log.warning("Failed to send usage statistics.")

    def write_statistics(self):
        if not self.is_enabled():
            return

        statistics_path = self.filename()
        statistics = {
            "Date": str(datetime.now().date()),
            "Application Version": QCoreApplication.applicationVersion(),
            "Operating System": platform.system() + " " + platform.release(),
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

    @staticmethod
    def set_last_search_query(query):
        UsageStatistics.last_search_query = query

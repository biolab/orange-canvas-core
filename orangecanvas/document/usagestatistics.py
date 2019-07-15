from datetime import datetime
import platform
import json
import logging
import os
from typing import List

import requests

from AnyQt.QtCore import QCoreApplication

from orangecanvas import config


log = logging.getLogger(__name__)


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
        node additions by type:
            widget name
            type of addition:
                quick menu
                toolbox click
                toolbox drag
                drag from other widget
            (if dragged from other widget, other widget name)
    """
    _is_enabled = False

    NodeAddClick = 0
    NodeAddDrag = 1
    NodeAddMenu = 2
    NodeAddExtendFromSink = 3
    NodeAddExtendFromSource = 4

    last_search_query = None

    def __init__(self):
        self.toolbox_clicks = []
        self.toolbox_drags = []
        self.quick_menu_actions = []
        self.widget_extensions = []
        self.__node_addition_type = None

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

    def log_node_added(self, widget_name, extended_widget=None):
        if not self.is_enabled():
            return

        if self.__node_addition_type == UsageStatistics.NodeAddMenu:

            self.quick_menu_actions.append({
                "Widget Name": widget_name,
                "Query": UsageStatistics.last_search_query,
            })

        elif self.__node_addition_type == UsageStatistics.NodeAddClick:

            self.toolbox_clicks.append({
                "Widget Name": widget_name,
            })

        elif self.__node_addition_type == UsageStatistics.NodeAddDrag:

            self.toolbox_drags.append({
                "Widget Name": widget_name,
            })

        elif self.__node_addition_type == UsageStatistics.NodeAddExtendFromSink:

            self.widget_extensions.append({
                "Widget Name": widget_name,
                "Extended Widget": extended_widget,
                "Direction": "FROM_SINK",
                "Query": UsageStatistics.last_search_query,
            })

        elif self.__node_addition_type == UsageStatistics.NodeAddExtendFromSource:

            self.widget_extensions.append({
                "Widget Name": widget_name,
                "Extended Widget": extended_widget,
                "Direction": "FROM_SOURCE",
                "Query": UsageStatistics.last_search_query,
            })

        else:
            log.warning("Invalid usage statistics state; "
                        "attempted to log node before setting node type.")

    def set_node_type(self, addition_type):
        self.__node_addition_type = addition_type

    def filename(self) -> str:
        """
        Return the filename path where the statics are saved
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
            "Session": {
                "Quick Menu Search": self.quick_menu_actions,
                "Toolbox Click": self.toolbox_clicks,
                "Toolbox Drag": self.toolbox_drags,
                "Widget Extension": self.widget_extensions
            }
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

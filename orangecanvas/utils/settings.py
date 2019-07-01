"""
Settings (`settings`)
=====================

A more `dict` like interface for QSettings

"""
import abc
import logging

import typing
from typing import List, Dict, Tuple, Union, Any, Type, Optional

from collections import namedtuple, MutableMapping

from AnyQt.QtCore import QObject, QEvent, QCoreApplication, QSettings
from AnyQt.QtCore import pyqtSignal as Signal


log = logging.getLogger(__name__)


config_slot = namedtuple(
    "config_slot",
    ["key",
     "value_type",
     "default_value",
     "doc"]
)


class SettingChangedEvent(QEvent):
    """
    A settings has changed.

    This event is sent by Settings instance to itself when a setting for
    a key has changed.

    """
    SettingChanged = QEvent.registerEventType()
    """Setting was changed"""

    SettingAdded = QEvent.registerEventType()
    """A setting was added"""

    SettingRemoved = QEvent.registerEventType()
    """A setting was removed"""

    def __init__(self, etype, key, value=None, oldValue=None):
        """
        Initialize the event instance
        """
        super().__init__(etype)
        self.__key = key
        self.__value = value
        self.__oldValue = oldValue

    def key(self):
        return self.__key

    def value(self):
        return self.__value

    def oldValue(self):
        return self.__oldValue


_QObjectType = type(QObject)


class QABCMeta(_QObjectType, abc.ABCMeta):  # type: ignore # pylint: disable=all
    def __init__(self, name, bases, attr_dict):
        _QObjectType.__init__(self, name, bases, attr_dict)
        abc.ABCMeta.__init__(self, name, bases, attr_dict)


# Backward compatibility.
# Settings used to store values, for which the explicit type
# was not registered in default' slots, by wrapping it in a _pickledvalue, so
# it would be pickled and unpickled when read from .ini files by PyQt.
# But this creates a mess when reading the settings back with plain QSettings.
class _pickledvalue:
    value = ...

    def __init__(self, value):
        raise RuntimeError("'_pickledvalue' instances should not be created")


class Settings(QObject, MutableMapping, metaclass=QABCMeta):
    """
    A `dict` like interface to a QSettings store.
    """
    valueChanged = Signal(str, object)
    valueAdded = Signal(str, object)
    keyRemoved = Signal(str)

    def __init__(self, parent=None, defaults=(), path=None, store=None):
        super().__init__(parent)
        if store is None:
            store = QSettings()

        path = (path or "").rstrip("/")

        self.__path = path
        self.__defaults = dict([(slot.key, slot) for slot in defaults])
        self.__store = store

    def __key(self, key):
        """
        Return the full key (including group path).
        """
        if self.__path:
            return "/".join([self.__path, key])
        else:
            return key

    def __delitem__(self, key):
        """
        Delete the setting for key. If key is a group remove the
        whole group.

        .. note:: defaults cannot be deleted they are instead reverted
                  to their original state.

        """
        if key not in self:
            raise KeyError(key)

        if self.isgroup(key):
            group = self.group(key)
            for key in group:
                del group[key]

        else:
            fullkey = self.__key(key)

            oldValue = self.get(key)

            if self.__store.contains(fullkey):
                self.__store.remove(fullkey)

            newValue = None
            if fullkey in self.__defaults:
                newValue = self.__defaults[fullkey].default_value
                etype = SettingChangedEvent.SettingChanged
            else:
                etype = SettingChangedEvent.SettingRemoved

            QCoreApplication.sendEvent(
                self, SettingChangedEvent(etype, key, newValue, oldValue)
            )

    def __value(self, fullkey, value_type):
        if value_type is None:
            value = self.__store.value(fullkey)
        else:
            try:
                value = self.__store.value(fullkey, type=value_type)
            except (TypeError, RuntimeError):
                # In case the value was pickled in a type unsafe mode
                value = self.__store.value(fullkey)

        if isinstance(value, _pickledvalue):  # back-compat
            value = value.value
        return value

    def __getitem__(self, key):
        """
        Get the setting for key.
        """
        if key not in self:
            raise KeyError(key)

        if self.isgroup(key):
            raise KeyError("{0!r} is a group".format(key))

        fullkey = self.__key(key)
        slot = self.__defaults.get(fullkey, None)

        if self.__store.contains(fullkey):
            value = self.__value(fullkey, slot.value_type if slot else None)
        elif slot is not None:
            value = slot.default_value
        else:
            raise KeyError()

        return value

    def __setitem__(self, key, value):
        """
        Set the setting for key.
        """
        if not isinstance(key, str):
            raise TypeError(key)

        fullkey = self.__key(key)
        if fullkey in self.__defaults:
            value_type = self.__defaults[fullkey].value_type
            if not isinstance(value, value_type):
                if not isinstance(value, value_type):
                    raise TypeError("Expected {0!r} got {1!r}".format(
                                        value_type.__name__,
                                        type(value).__name__)
                                    )

        if key in self:
            oldValue = self.get(key)
            etype = SettingChangedEvent.SettingChanged
        else:
            oldValue = None
            etype = SettingChangedEvent.SettingAdded

        self.__store.setValue(fullkey, value)

        QCoreApplication.sendEvent(
            self, SettingChangedEvent(etype, key, value, oldValue)
        )

    def __contains__(self, key):
        """
        Return `True` if settings contain the `key`, False otherwise.
        """
        fullkey = self.__key(key)
        return self.__store.contains(fullkey) or (fullkey in self.__defaults)

    def __iter__(self):
        """Return an iterator over over all keys.
        """
        keys = self.__store.allKeys() + list(self.__defaults.keys())

        if self.__path:
            path = self.__path + "/"
            keys = filter(lambda key: key.startswith(path), keys)
            keys = [key[len(path):] for key in keys]

        return iter(sorted(set(keys)))

    def __len__(self):
        return len(list(iter(self)))

    def group(self, path):
        if self.__path:
            path = "/".join([self.__path, path])

        return Settings(self, self.__defaults.values(), path, self.__store)

    def isgroup(self, key):
        """
        Is the `key` a settings group i.e. does it have subkeys.
        """
        if key not in self:
            raise KeyError("{0!r} is not a valid key".format(key))

        return len(self.group(key)) > 0

    def isdefault(self, key):
        """
        Is the value for key the default.
        """
        if key not in self:
            raise KeyError(key)
        return not self.__store.contains(self.__key(key))

    def clear(self):
        """
        Clear the settings and restore the defaults.
        """
        self.__store.clear()

    def add_default_slot(self, default):
        """
        Add a default slot to the settings This also replaces any
        previously set value for the key.

        """
        value = default.default_value
        oldValue = None
        etype = SettingChangedEvent.SettingAdded
        key = default.key

        if key in self:
            oldValue = self.get(key)
            etype = SettingChangedEvent.SettingChanged
            if not self.isdefault(key):
                # Replacing a default value.
                self.__store.remove(self.__key(key))

        self.__defaults[key] = default
        event = SettingChangedEvent(etype, key, value, oldValue)
        QCoreApplication.sendEvent(self, event)

    def get_default_slot(self, key):
        return self.__defaults[self.__key(key)]

    def customEvent(self, event):
        super().customEvent(event)

        if isinstance(event, SettingChangedEvent):
            if event.type() == SettingChangedEvent.SettingChanged:
                self.valueChanged.emit(event.key(), event.value())
            elif event.type() == SettingChangedEvent.SettingAdded:
                self.valueAdded.emit(event.key(), event.value())
            elif event.type() == SettingChangedEvent.SettingRemoved:
                self.keyRemoved.emit(event.key())

            parent = self.parent()
            if isinstance(parent, Settings):
                # Assumption that the parent is a parent setting group.
                parent.customEvent(
                    SettingChangedEvent(event.type(),
                                        "/".join([self.__path, event.key()]),
                                        event.value(),
                                        event.oldValue())
                )


if typing.TYPE_CHECKING:  # pragma: no cover
    _T = typing.TypeVar("_T")
    #: Specification for an value in the return value of readArray
    #: Can be single type or a tuple of (type, defaultValue) where default
    #: value is used where a stored entry is missing.
    ValueSpec = Union[Type[_T], Tuple[Type[_T], _T]]


def QSettings_readArray(settings, key, scheme):
    # type: (QSettings, str, Dict[str, ValueSpec]) -> List[Dict[str, _T]]
    """
    Read the whole array from a QSettings instance.

    Parameters
    ----------
    settings : QSettings
    key : str
    scheme : Dict[str, ValueSpec]

    Example
    -------
    >>> s = QSettings("./login.ini")
    >>> QSettings_readArray(s, "array", {"username": str, "password": str})
    [{"username": "darkhelmet", "password": "1234"}}
    >>> QSettings_readArray(
    ...    s, "array", {"username": str, "noexist": (str, "~||~")})
    ...
    [{"username": "darkhelmet", "noexist": "~||~"}}
    """
    items = []
    count = settings.beginReadArray(key)

    def normalize_spec(spec):
        # type: (ValueSpec) -> Tuple[Type[_T], Optional[_T]]
        if isinstance(spec, tuple):
            if len(spec) != 2:
                raise ValueError("len(spec) != 2")
            type_, default = spec
        else:
            type_, default = spec, None
        return type_, default

    specs = {
        name: normalize_spec(spec) for name, spec in scheme.items()
    }
    for i in range(count):
        settings.setArrayIndex(i)
        item = {}
        for key, (type_, default) in specs.items():
            value = settings.value(key, type=type_, defaultValue=default)
            item[key] = value
        items.append(item)
    settings.endArray()
    return items


def QSettings_writeArray(settings, key, values):
    # type: (QSettings, str, List[Dict[str, Any]]) -> None
    """
    Write an array of values to a QSettings instance.

    Parameters
    ----------
    settings : QSettings
    key : str
    values : List[Dict[str, Any]]

    Examples
    --------
    >>> s = QSettings("./login.ini")
    >>> QSettings_writeArray(
    ...     s, "array", [{"username": "darkhelmet", "password": "1234"}]
    ... )
    """
    settings.beginWriteArray(key, len(values))
    for i in range(len(values)):
        settings.setArrayIndex(i)
        for key_, val in values[i].items():
            settings.setValue(key_, val)
    settings.endArray()


def QSettings_writeArrayItem(settings, key, index, item, arraysize=-1):
    # type: (QSettings, str, int, Dict[str, Any], int) -> None
    """
    Write/update an array item at index.

    Parameters
    ----------
    settings : QSettings
    key : str
    index : int
    item : Dict[str, Any]
    arraysize : int
        The full array size. Note that the array will be truncated to this
        size.
    """
    if arraysize < 0:
        arraysize = settings.beginReadArray(key)
        settings.endArray()

    settings.beginWriteArray(key, arraysize)
    settings.setArrayIndex(index)
    for key_, val in item.items():
        settings.setValue(key_, val)
    settings.endArray()

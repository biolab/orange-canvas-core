"""
PyQt4 compatibility utility functions.

.. warning:: It is important that any `sip.setapi` (at least for QVariant
             and QString) calls are already made before importing this
             module.

"""
import six

import sip
import AnyQt.QtCore

# All known api names for compatibility with version of sip where
# `getapi` is not available ( < v4.9)
_API_NAMES = set(["QVariant", "QString", "QDate", "QDateTime",
                  "QTextStream", "QTime", "QUrl"])


def sip_getapi(name):
    """
    Get the api version for a name.
    """
    if sip.SIP_VERSION > 0x40900:
        return sip.getapi(name)
    elif name in _API_NAMES:
        return 1
    else:
        raise ValueError("unknown API {0!r}".format(name))

try:
    HAS_QVARIANT = sip_getapi("QVariant") == 1 and \
                   hasattr(AnyQt.QtCore, "QVariant")
except ValueError:
    HAS_QVARIANT = False

try:
    HAS_QSTRING = sip_getapi("QString") == 1
    from PyQt4.QtCore import QString as _QString
except (ValueError, ImportError):
    HAS_QSTRING = False

if HAS_QVARIANT:
    from AnyQt.QtCore import QVariant

from AnyQt.QtCore import QSettings, QByteArray
from AnyQt.QtCore import PYQT_VERSION

#: QSettings.value has a `type` parameter
QSETTINGS_HAS_TYPE = PYQT_VERSION >= 0x40803


def toPyObject(variant):
    """
    Return `variant` as a python object if it is wrapped in a `QVariant`
    instance (using `variant.toPyObject()`). In case the sip API version
    for QVariant does not export it just return the object unchanged.

    """
    if not HAS_QVARIANT:
        return variant
    elif isinstance(variant, QVariant):
        return variant.toPyObject()
    else:
        raise TypeError("Expected a 'QVariant' got '{}'."
                        .format(type(variant).__name__))


def qunwrap(variant):
    """Unwrap a `variant` and return it's contents.
    """
    value = toPyObject(variant)
    if HAS_QSTRING and isinstance(value, _QString):
        return six.text_type(value)
    else:
        return value


def qwrap(obj):
    if HAS_QVARIANT and not isinstance(obj, QVariant):
        return QVariant(obj)
    else:
        return obj


def _check_error(value_status):
    value, status = value_status
    if not status:
        raise TypeError()
    else:
        return value


def qvariant_to_py(variant, py_type):
    """
    Convert a `QVariant` object to a python object of type `py_type`.
    """
    if py_type == bool:
        return variant.toBool()
    elif py_type == int:
        return _check_error(variant.toInt())
    elif py_type == bytes:
        return bytes(variant.toByteArray())
    elif py_type == six.text_type:
        return six.text_type(variant.toString())
    elif py_type == QByteArray:
        return variant.toByteArray()

    else:
        raise TypeError("Unsuported type {0!s}".format(py_type))


if not QSETTINGS_HAS_TYPE:
    _QSettings = QSettings

    class QSettings(QSettings):
        """
        A subclass of QSettings with a simulated `type` parameter in
        value method.

        """
        # QSettings.value does not have `type` type before PyQt4 4.8.3
        # We dont't check if QVariant is exported, it is assumed on such old
        # installations the new api is not used.
        def value(self, key, defaultValue=QVariant(), type=None):
            """
            Returns the value for setting key. If the setting doesn't exist,
            returns defaultValue.

            """
            if not _QSettings.contains(self, key):
                return defaultValue

            value = _QSettings.value(self, key)

            if type is not None:
                value = qvariant_to_py(value, type)

            return value

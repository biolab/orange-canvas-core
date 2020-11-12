import weakref
from types import SimpleNamespace as namespace
from typing import Optional, TypeVar, Generic

from AnyQt.QtCore import QObject, Qt

__all__ = [
    "qobjref", "qobjref_weak"
]

Q = TypeVar("Q", bound=QObject)


class qobjref(Generic[Q]):
    """
    A 'guarded reference' to a QObject.

    An instance of a `qobjref` holds a reference to a `QObject` for as long
    as it is alive (not destroyed by C++ destructor).

    Example
    -------
    >>> import sip
    >>> obj = QObject()
    >>> ref = qobjref(obj)
    >>> assert ref() is obj
    >>> sip.delete(obj)  # forcibly delete it
    >>> assert ref() is None

    Note
    ----
    This is not thread safe in the sense that the object can be deleted
    from a different thread while the ref() is returning it.

    Note
    ----
    `qobjref` keeps a reference to the object, meaning it will not be
    garbage collected until qobjref is also reaped. Use qobjref_weak
    for weak references.

    See also
    --------
    QPointer
    """
    __slots__ = ("__obj", "__state", "__weakref__")

    def __init__(self, obj):
        # type: (Q) -> None
        assert isinstance(obj, QObject)
        self.__obj = obj

        def finalize(_weakref):
            # finalize when self is collected
            if state.objref is None:
                return
            objref = state.objref()
            if objref is not None:
                objref.destroyed.disconnect(state.zero_ref)

        # destroy/zero the reference when QObject is destroyed
        def zero_ref():
            selfref = state.selfref()
            if selfref is not None:
                selfref.__obj = None
            state.objref = None

        state = namespace(
            selfref=weakref.ref(self, finalize),
            objref=weakref.ref(obj),
            zero_ref=zero_ref,
            finalize=finalize)
        self.__state = state

        # Must not capture self in the zero_ref's closure
        obj.destroyed.connect(zero_ref, Qt.DirectConnection)

    def __call__(self):
        # type: () -> Optional[Q]
        """
        Return the QObject instance or None if it was destroyed.

        Return
        ------
        obj : Optional[QObject]
        """
        return self.__obj

    def __repr__(self):
        objrep = "to " + repr(self.__obj)
        if self.__obj is None:
            objrep = "dead"

        return "<qobjref at 0x%x; " % id(self) + objrep + ">"


class qobjref_weak(Generic[Q]):
    """
    A weak 'guarded reference' to a QObject.

    Similar to `qobjref`, except that the reference to the QObject is weak

    Example
    -------
    >>> import sip
    >>> obj = QObject()
    >>> ref = qobjref_weak(obj)
    >>> assert ref() is obj
    >>> sip.delete(obj)  # forcibly delete it
    >>> assert ref() is None
    >>> obj = QObject()
    >>> ref = qobjref_weak(obj)
    >>> assert ref() is obj
    >>> del obj  # assuming ref count is 1
    >>> assert ref() is None

    Note
    ----
    This is not thread safe in the sense that the object can be
    deleted from a different thread while the ref() is returning it.

    See also
    --------
    qobjref, QPointer
    """
    __slots__ = ("__obj_ref", "__state", "__weakref__")

    def __init__(self, obj):
        # type: (Q) -> None
        assert isinstance(obj, QObject)
        self.__obj_ref = weakref.ref(obj)

        # finalize when self is collected
        def disconnect(_weakref):
            if state.objref is None:
                return
            objref = state.objref()
            if objref is not None:
                objref.destroyed.disconnect(state.zero_ref)

        # destroy/zero the reference when QObject is destroyed
        def zero_ref():
            selfref = state.selfref()
            if selfref is not None:
                selfref.__obj_ref = None
            state.objref = None

        state = namespace(
            selfref=weakref.ref(self, disconnect),
            objref=weakref.ref(obj),
            zero_ref=zero_ref,
            disconnect=disconnect)
        self.__state = state

        # Must not capture self in the zero_ref's closure
        obj.destroyed.connect(zero_ref, Qt.DirectConnection)

    def __call__(self):
        # type: () -> Optional[Q]
        """
        Return the QObject instance or None if it is no longer alive

        Return
        ------
        obj : Optional[QObject]
        """
        ref = self.__obj_ref
        if ref is not None:
            return ref()
        else:
            return None

    def __repr__(self):
        obj = self.__call__()
        if obj is not None:
            objrep = "to " + repr(obj)
        else:
            objrep = "dead"
        return "<qobjref_weak at 0x%x; " % id(self) + objrep + ">"

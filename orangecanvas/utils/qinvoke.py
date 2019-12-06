from typing import TypeVar, Callable, overload
from AnyQt.QtCore import Qt, QObject, Signal

from functools import wraps


class _InvokeEmitter(QObject):
    sig = Signal(object, object)


class _InvokeCaller(QObject):
    sig = Signal(object, object)


A = TypeVar("A")
T1 = TypeVar("T1")
T2 = TypeVar("T2")
T3 = TypeVar("T3")
T4 = TypeVar("T4")
T5 = TypeVar("T5")
T6 = TypeVar("T6")


@overload
def qinvoke(
        func: Callable[[], A], context: QObject,
        type: Qt.ConnectionType = Qt.QueuedConnection
) -> Callable[[], None]: ...


@overload
def qinvoke(
        func: Callable[[T1], A], context: QObject,
        type: Qt.ConnectionType = Qt.QueuedConnection
) -> Callable[[T1], None]: ...


@overload
def qinvoke(
        func: Callable[[T1, T2], A], context: QObject,
        type: Qt.ConnectionType = Qt.QueuedConnection
) -> Callable[[T1, T2], None]: ...


@overload
def qinvoke(
        func: Callable[[T1, T2, T3], A], context: QObject,
        type: Qt.ConnectionType = Qt.QueuedConnection
) -> Callable[[T1, T2, T3], None]: ...


@overload
def qinvoke(
        func: Callable[[T1, T2, T3, T4], A], context: QObject,
        type: Qt.ConnectionType = Qt.QueuedConnection
) -> Callable[[T1, T2, T3, T4], None]: ...


@overload
def qinvoke(
        func: Callable[[T1, T2, T3, T4, T5], A], context: QObject,
        type: Qt.ConnectionType = Qt.QueuedConnection
) -> Callable[[T1, T2, T3, T4, T5], None]: ...


@overload
def qinvoke(
        func: Callable[[T1, T2, T3, T4, T5, T6], A], context: QObject,
        type: Qt.ConnectionType = Qt.QueuedConnection
) -> Callable[[T1, T2, T3, T4, T5, T6], None]: ...


@overload
def qinvoke(
        *, context: QObject, type: Qt.ConnectionType = Qt.QueuedConnection
) -> Callable[[Callable[..., A]], Callable[..., None]]: ...


def qinvoke(func: Callable = None, context: QObject = None, type=Qt.QueuedConnection):
    """
    Wrap and return a callable, such that it will be executed in the
    `context`'s thread/event loop.

    Parameters
    ----------
    func: Callable[..., Any]
        The function to be executed.
    context: QObject
        The invoking context. The `func` will be called in the specific event
        loop of `context`. If `context` is deleted then the call will be a
        noop.
    type: Qt.ConnectionType
        The connection type.

    Returns
    -------
    wrapped: Callable[..., None]
        A wrapped function taking the same arguments as `func`, but retuning
        no value. Calling this function will schedule `func` to be called from
        `context`'s event loop.
    """
    def decorator(func: Callable[..., A]) -> Callable[..., None]:
        emitter = _InvokeEmitter()
        # caller 'lives' in context's thread. If context is deleted so is the
        # caller (child objects are deleted before parents). This is used to
        # achieve (of fake) connection auto-disconnect.
        caller = _InvokeCaller(context)

        def call_in_context(args, kwargs):
            func(*args, *kwargs)

        # connection from emitter -(queued)-> caller -(direct)-> func
        emitter.sig.connect(caller.sig, type)
        caller.sig.connect(call_in_context, Qt.DirectConnection)

        def disconnect():
            # caller is captured in this closure. This should be the only
            # reference to it.
            caller.sig.disconnect(call_in_context)
            caller.setParent(None)  # this should delete the caller

        @wraps(func)
        def wrapped(*args, **kwargs):
            # emitter is captured in this closure. This should be the only
            # reference to it. It should ne deleted along with `wrapped`.
            emitter.sig.emit(args, kwargs)

        wrapped.disconnect = disconnect  # type: ignore
        return wrapped

    if func is not None:
        if context is not None:
            return decorator(func)
        else:
            raise TypeError
    elif context is None:
        raise TypeError

    return decorator

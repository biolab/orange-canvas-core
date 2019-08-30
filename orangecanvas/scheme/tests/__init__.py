"""
Scheme tests
"""
from AnyQt.QtCore import QObject, QEventLoop, QTimer, QCoreApplication, QEvent
from typing import List


class EventSpy(QObject):
    """
    A testing utility class (similar to QSignalSpy) to record events
    delivered to a QObject instance.

    Note
    ----
    Only event types can be recorded (as QEvent instances are deleted
    on delivery).

    Note
    ----
    Can only be used with a QCoreApplication running.

    Parameters
    ----------
    object : QObject
        An object whose events need to be recorded.
    etype : Union[QEvent.Type, Sequence[QEvent.Type]
        A event type (or types) that should be recorded
    """
    def __init__(self, object: QObject, etype, **kwargs):
        super().__init__(**kwargs)
        if not isinstance(object, QObject):
            raise TypeError

        self.__object = object
        try:
            len(etype)
        except TypeError:
            etypes = {etype}
        else:
            etypes = set(etype)

        self.__etypes = etypes
        self.__record = []
        self.__loop = QEventLoop()
        self.__timer = QTimer(self, singleShot=True)
        self.__timer.timeout.connect(self.__loop.quit)
        self.__object.installEventFilter(self)

    def wait(self, timeout=5000):
        """
        Start an event loop that runs until a spied event or a timeout occurred.

        Parameters
        ----------
        timeout : int
            Timeout in milliseconds.

        Returns
        -------
        res : bool
            True if the event occurred and False otherwise.

        Example
        -------
        >>> app = QCoreApplication.instance() or QCoreApplication([])
        >>> obj = QObject()
        >>> spy = EventSpy(obj, QEvent.User)
        >>> app.postEvent(obj, QEvent(QEvent.User))
        >>> spy.wait()
        True
        >>> print(spy.events())
        [1000]
        """
        count = len(self.__record)
        self.__timer.stop()
        self.__timer.setInterval(timeout)
        self.__timer.start()
        self.__loop.exec_()
        self.__timer.stop()
        return len(self.__record) != count

    def eventFilter(self, reciever: QObject, event: QEvent) -> bool:
        if reciever is self.__object and event.type() in self.__etypes:
            self.__record.append(event.type())
            if self.__loop.isRunning():
                self.__loop.quit()
        return super().eventFilter(reciever, event)

    def events(self) -> List[QEvent.Type]:
        """
        Return a list of all (listened to) event types that occurred.

        Returns
        -------
        events : List[QEvent.Type]
        """
        return list(self.__record)

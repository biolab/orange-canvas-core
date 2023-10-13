import asyncio
from concurrent import futures
from typing import Optional

from AnyQt.QtCore import QCoreApplication, QThread
import qasync


def get_event_loop() -> asyncio.AbstractEventLoop:
    """
    Get the asyncio.AbstractEventLoop for the main Qt application thread.

    The QCoreApplication instance must already have been created.
    Must only be called from the main Qt application thread.
    """
    try:
        # Python >= 3.7
        get_running_loop = asyncio.get_running_loop   # type: ignore
    except AttributeError:
        get_running_loop = asyncio._get_running_loop  # type: ignore
    app = QCoreApplication.instance()
    if app is None:
        raise RuntimeError("QCoreApplication is not running")
    if app.thread() is not QThread.currentThread():
        raise RuntimeError("Called from non-main thread")
    loop: Optional[asyncio.AbstractEventLoop]
    try:
        loop = get_running_loop()
    except RuntimeError:
        loop = None
    else:
        if loop is not None:
            return loop

    if loop is None:
        loop = qasync.QEventLoop(app)
        # Do not use qasync.QEventLoop's default executor which uses QThread
        # based pool and exhibits https://github.com/numpy/numpy/issues/11551
        loop.set_default_executor(futures.ThreadPoolExecutor())
        try:
            # qasync>=0.24.2 no longer sets the running loop in QEventLoop
            # constructor
            get_running_loop()
        except RuntimeError:
            asyncio.events._set_running_loop(loop)
    assert get_running_loop() is not None
    return loop

import time
import gc
import weakref
from types import SimpleNamespace
from typing import List, Optional, Callable

import unittest
from AnyQt.QtCore import QCoreApplication, QThread, QObject, Signal, QEvent

from concurrent.futures.thread import ThreadPoolExecutor

from AnyQt.QtTest import QSignalSpy, QTest

from ..qinvoke import qinvoke, connect_with_context


class CoreAppTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.app = QCoreApplication.instance()
        if self.app is None:
            self.app = QCoreApplication([])
        super().setUp()

    def tearDown(self) -> None:
        self.app = None
        super().tearDown()


def delete(qobj: QObject):
    assert qobj.thread() is QThread.currentThread()
    spy = QSignalSpy(qobj.destroyed)
    qobj.deleteLater()
    QCoreApplication.sendPostedEvents(qobj, QEvent.DeferredDelete)
    assert len(spy) == 1


class TestMethodinvoke(CoreAppTestCase):
    def test_qinvoke(self):
        executor = ThreadPoolExecutor()
        state = [None, None]  # type: List[Optional[QThread]]

        class StateSetter(QObject):
            didsetstate = Signal()

            def set_state(self, value: QThread) -> None:
                state[0] = value
                state[1] = QThread.currentThread()
                self.didsetstate.emit()

        def func(callback):  # type: (Callable[[QThread], None]) -> None
            callback(QThread.currentThread())

        obj = StateSetter()
        spy = QSignalSpy(obj.didsetstate)
        f = executor.submit(
            func, qinvoke(obj.set_state, context=obj)
        )
        self.assertTrue(spy.wait())

        self.assertIs(state[1], QThread.currentThread(),
                      "set_state was called from the wrong thread")

        self.assertIsNot(state[0], QThread.currentThread(),
                         "set_state was invoked in the main thread")

        # test that disconnect works 'atomically' w.r.t. event loop
        spy = QSignalSpy(obj.didsetstate)
        callback = qinvoke(obj.set_state, context=obj)
        f = executor.submit(func, callback)
        f.result()
        time.sleep(0.01)  # wait for finish
        callback.disconnect()  # type: ignore
        self.assertFalse(spy.wait(100), "")
        self.assertSequenceEqual(spy, [])

        executor.shutdown(wait=True)

    def test_qinvoke_context_delete(self):
        executor = ThreadPoolExecutor(max_workers=1)
        context = QObject()
        isdeleted = False
        lastindex = -1

        def mark_deleted():
            nonlocal isdeleted
            isdeleted = True

        context.destroyed.connect(mark_deleted)

        def func(i):
            nonlocal isdeleted
            nonlocal lastindex
            lastindex = i
            self.assertFalse(isdeleted)
            self.assertIs(context.thread(), self.app.thread())

        callback = qinvoke(func, context=context)

        _ = executor.map(callback, range(1000))

        while lastindex < 0:
            QTest.qWait(10)
        assert lastindex >= 0
        delete(context)
        assert isdeleted
        lasti = lastindex
        QTest.qWait(50)
        assert lasti == lastindex
        executor.shutdown()

    def test_qinvoke_as_decorator(self):
        context = QObject()

        @qinvoke(context=context)
        def f(name):
            context.setObjectName(name)

        spy = QSignalSpy(context.objectNameChanged)
        f("name")
        self.assertTrue(spy.wait(500))

    def test_errors(self):
        with self.assertRaises(TypeError):
            qinvoke(lambda: None)

        with self.assertRaises(TypeError):
            qinvoke()


class TestConnectWithContext(CoreAppTestCase):
    def test_connect_with_context(self):
        state = SimpleNamespace(th=None, greeting=None)
        target = QObject()

        def in_target_context(greeting: str):
            state.th = QThread.currentThread()
            state.greeting = greeting
            target.setObjectName(greeting)

        executor = ThreadPoolExecutor()
        emiter = QObject()
        connect_with_context(
            emiter.objectNameChanged,
            target,
            in_target_context,
        )

        def run():
            emiter.objectNameChanged.emit("hello")

        spy = QSignalSpy(target.objectNameChanged)
        executor.submit(run)
        self.assertTrue(spy.wait())
        self.assertIs(target.thread(), state.th)

        # delete target context (and connection)
        delete(target)
        state.th = None
        state.greeting = None

        executor.map(run, range(10))
        executor.shutdown(wait=True)
        QTest.qWait(10)
        self.assertIsNone(state.th)
        self.assertIsNone(state.greeting)

    def test_gc_captured_context(self):
        emitter = QObject()
        context = QObject()
        ref = weakref.ref(context)
        connect_with_context(
            emitter.objectNameChanged,
            context,
            lambda name: context.setObjectName(name)  # captures context
        )
        emitter.setObjectName("AA")
        self.assertEqual(context.objectName(), emitter.objectName())
        del context  # This needs to clear captured context in connected func
        self.assertIsNone(ref())
        emitter.setObjectName("BB")

    def test_gc_captured_context_cycle(self):
        emitter = QObject()
        context = QObject()
        context.cycle = context
        ref = weakref.ref(context)
        connect_with_context(
            emitter.objectNameChanged,
            context,
            lambda name: context.setObjectName(name)  # captures context
        )
        emitter.setObjectName("AA")
        self.assertEqual(context.objectName(), emitter.objectName())
        delete(context)
        del context  # This needs to clear captured context in connected func
        gc.collect()
        self.assertIsNone(ref())
        emitter.setObjectName("BB")

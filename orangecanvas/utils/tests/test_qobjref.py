import weakref

from AnyQt.QtCore import QObject, QCoreApplication, QEvent

from ...gui.test import QCoreAppTestCase
from ..qobjref import qobjref, qobjref_weak


def delete_qobject(obj):
    obj.deleteLater()
    QCoreApplication.sendPostedEvents(obj, QEvent.DeferredDelete)


class TestQObjectRef(QCoreAppTestCase):
    def test_delete(self):
        obj = QObject()
        ref = qobjref(obj)
        assert ref() is obj
        delete_qobject(obj)  # forcibly delete it
        assert ref() is None

    def test_deref(self):
        obj = QObject()
        obj_wref = weakref.ref(obj)
        ref = qobjref(obj)
        del obj
        assert ref() is obj_wref()
        del ref
        assert obj_wref() is None

    def test_self_finalize(self):
        obj = QObject()
        ref = qobjref(obj)
        del ref

    def test_repr(self):
        obj = QObject()
        ref = qobjref(obj)
        assert " to " in repr(ref)
        delete_qobject(obj)
        assert "dead" in repr(ref)


class TestQObjectWeakRef(QCoreAppTestCase):
    def test_delete(self):
        obj = QObject()
        ref = qobjref_weak(obj)
        assert ref() is obj
        delete_qobject(obj)  # forcibly delete it
        assert ref() is None

    def test_deref(self):
        obj = QObject()
        ref = qobjref_weak(obj)
        obj_wref = weakref.ref(obj)
        del obj
        assert ref() is obj_wref() is None

    def test_self_finalize(self):
        obj = QObject()
        ref = qobjref_weak(obj)
        del ref

    def test_repr(self):
        obj = QObject()
        ref = qobjref_weak(obj)
        assert " to " in repr(ref)
        delete_qobject(obj)
        assert "dead" in repr(ref)

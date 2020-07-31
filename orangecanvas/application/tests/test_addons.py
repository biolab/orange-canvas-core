import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from zipfile import ZipFile

from AnyQt.QtWidgets import QMessageBox, QDialogButtonBox
from AnyQt.QtCore import QEventLoop, QUrl, QMimeData, QPoint, Qt
from AnyQt.QtTest import QTest
from PyQt5.QtGui import QDropEvent
from pkg_resources import EntryPoint

from orangecanvas.application import addons
from orangecanvas.gui.test import QAppTestCase
from orangecanvas.utils.qinvoke import qinvoke

from ..addons import (
    Available, Installed, Installable, Distribution, Requirement, is_updatable,
    Install, Upgrade, Uninstall,
    installable_items, installable_from_json_response,
    AddonManagerDialog)


class TestUtils(unittest.TestCase):
    def test_items_1(self):
        inst = Installable("foo", "1.0", "a foo", "", "", [])
        dist = Distribution(project_name="foo", version="1.0")
        item = Available(inst)
        self.assertFalse(is_updatable(item))

        item = Installed(None, dist)
        self.assertFalse(is_updatable(item))
        item = Installed(inst, dist)
        self.assertFalse(is_updatable(item))

        item = Installed(inst._replace(version="0.9"), dist)
        self.assertFalse(is_updatable(item))

        item = Installed(inst._replace(version="1.1"), dist)
        self.assertTrue(is_updatable(item))

        item = Installed(inst._replace(version="2.0"), dist,
                         constraint=Requirement.parse("foo<1.99"))
        self.assertFalse(is_updatable(item))
        item = Installed(inst._replace(version="2.0"), dist,
                         constraint=Requirement.parse("foo<2.99"))
        self.assertTrue(is_updatable(item))

    def test_items_2(self):
        inst1 = Installable("foo", "1.0", "a foo", "", "", [])
        inst2 = Installable("bar", "1.0", "a bar", "", "", [])
        dist2 = Distribution(project_name="bar", version="0.9")
        dist3 = Distribution(project_name="quack", version="1.0")
        items = installable_items([inst1, inst2], [dist2, dist3])
        self.assertIn(Available(inst1), items)
        self.assertIn(Installed(inst2, dist2), items)
        self.assertIn(Installed(None, dist3), items)

    def test_installable_from_json_response(self):
        inst = installable_from_json_response({
            "info": {
                "name": "foo",
                "version": "1.0",
            },
            "releases": {
                "1.0": [
                    {
                        "filename": "aa.tar.gz",
                        "url": "https://examples.com",
                        "size": 100,
                        "packagetype": "sdist",
                    }
                ]
            },
        })
        self.assertTrue(inst.name, "foo")
        self.assertEqual(inst.version, "1.0")


@contextmanager
def addon_archive(pkginfo):
    file = tempfile.NamedTemporaryFile("wb", delete=False, suffix=".zip")
    name = file.name
    file.close()
    with ZipFile(name, 'w') as myzip:
        myzip.writestr('PKG-INFO', pkginfo)
    try:
        yield name
    finally:
        os.remove(name)


class TestAddonManagerDialog(QAppTestCase):
    def test_widget(self):
        items = [
            Installed(
                Installable("foo", "1.1", "", "", "", []),
                Distribution(project_name="foo", version="1.0"),
            ),
            Available(
                Installable("q", "1.2", "", "", "", [])
            ),
            Installed(
                None,
                Distribution(project_name="a", version="0.0")
            ),
        ]
        w = AddonManagerDialog()
        w.setItems(items)
        _ = w.items()
        state = w.itemState()
        self.assertSequenceEqual(state, [])
        state = [(Install, items[1])]
        w.setItemState(state)
        self.assertSequenceEqual(state, w.itemState())
        state = state + [(Upgrade, items[0])]
        w.setItemState(state)
        self.assertSequenceEqual(state, w.itemState()[::-1])
        state = [(Uninstall, items[0])]
        w.setItemState(state)
        self.assertSequenceEqual(state, w.itemState())
        updateTopLayout = w._AddonManagerDialog__updateTopLayout
        updateTopLayout(False)
        updateTopLayout(True)

    @patch("orangecanvas.config.default.addon_entry_points",
           return_value=[EntryPoint(
               "a", "b", dist=Distribution(project_name="foo", version="1.0"))])
    def test_drop(self, p1):
        items = [
            Installed(
                Installable("foo", "1.1", "", "", "", []),
                Distribution(project_name="foo", version="1.0"),
            ),
        ]
        w = AddonManagerDialog()
        w.setItems(items)

        # drop an addon already in the list
        pkginfo = "Metadata-Version: 1.0\nName: foo\nVersion: 0.9"
        with addon_archive(pkginfo) as fn:
            event = self._drop_event(QUrl.fromLocalFile(fn))
            w.dropEvent(event)
        items = w.items()
        self.assertEqual(1, len(items))
        self.assertEqual("0.9", items[0].installable.version)
        self.assertEqual(True, items[0].installable.force)
        state = [(Upgrade, items[0])]
        self.assertSequenceEqual(state, w.itemState())

        # drop a new addon
        pkginfo = "Metadata-Version: 1.0\nName: foo2\nVersion: 0.8"
        with addon_archive(pkginfo) as fn:
            event = self._drop_event(QUrl.fromLocalFile(fn))
            w.dropEvent(event)
        items = w.items()
        self.assertEqual(2, len(items))
        self.assertEqual("0.8", items[1].installable.version)
        self.assertEqual(True, items[1].installable.force)
        state = state + [(Install, items[1])]
        self.assertSequenceEqual(state, w.itemState())

    def _drop_event(self, url):
        # make sure data does not get garbage collected before it used
        # pylint: disable=attribute-defined-outside-init
        self.event_data = data = QMimeData()
        data.setUrls([QUrl(url)])

        return QDropEvent(
            QPoint(0, 0), Qt.MoveAction, data,
            Qt.NoButton, Qt.NoModifier, QDropEvent.Drop)

    def test_run_query(self):
        w = AddonManagerDialog()

        query_res = [
            addons._QueryResult("uber-pkg", None),
            addons._QueryResult(
                "unter-pkg", Installable("unter-pkg", "0.0.0", "", "", "", []))
        ]

        def query(names):
            return query_res

        with patch.object(QMessageBox, "exec_", return_value=QMessageBox.Cancel), \
             patch.object(addons, "query_pypi", query):
            f = w.runQueryAndAddResults(
                ["uber-pkg", "unter-pkg"],
            )
            loop = QEventLoop()
            f.add_done_callback(qinvoke(lambda f: loop.quit(), loop))
            loop.exec()
            items = w.items()
            self.assertEqual(items, [Available(query_res[1].installable)])

    def test_install(self):
        w = AddonManagerDialog()
        foo = Available(Installable("foo", "1.1", "", "", "", []))
        w.setItems([foo])
        w.setItemState([(Install, foo)])
        with patch.object(addons.PipInstaller, "install",
                          lambda self, pkg: None), \
             patch.object(addons.CondaInstaller, "install",
                          lambda self, pkg, raise_on_fail: None), \
             patch.object(QMessageBox, "exec_", return_value=QMessageBox.Cancel):
            b = w.findChild(QDialogButtonBox)
            b.accepted.emit()
            QTest.qWait(1)
            w.reject()
            QTest.qWait(1)

        w.deleteLater()

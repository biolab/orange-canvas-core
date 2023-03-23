import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch
from zipfile import ZipFile

from AnyQt.QtCore import QEventLoop, QMimeData, QPointF, Qt, QUrl
from AnyQt.QtGui import QDropEvent
from AnyQt.QtTest import QTest
from AnyQt.QtWidgets import QDialogButtonBox, QMessageBox, QTreeView, QStyle
from pkg_resources import Distribution, EntryPoint

from orangecanvas.application import addons
from orangecanvas.application.addons import AddonManagerDialog
from orangecanvas.application.utils.addons import (
    Available,
    CondaInstaller,
    Install,
    Installable,
    Installed,
    PipInstaller,
    Uninstall,
    Upgrade,
    _QueryResult,
)
from orangecanvas.gui.test import QAppTestCase
from orangecanvas.utils.qinvoke import qinvoke


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
        w.setItemState([])

        # toggle install state
        view = w.findChild(QTreeView, "add-ons-view")
        index = view.model().index(0, 0)
        delegate = view.itemDelegateForColumn(0)
        style = view.style()
        opt = view.viewOptions()
        opt.rect = view.visualRect(index)
        delegate.initStyleOption(opt, index)

        rect = style.subElementRect(
            QStyle.SE_ItemViewItemCheckIndicator, opt, view
        )

        def check_state_equal(left, right):
            self.assertEqual(Qt.CheckState(left), Qt.CheckState(right))

        check_state_equal(index.data(Qt.CheckStateRole), Qt.PartiallyChecked)
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=rect.center())
        check_state_equal(index.data(Qt.CheckStateRole), Qt.Checked)
        QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=rect.center())
        check_state_equal(index.data(Qt.CheckStateRole), Qt.Unchecked)

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
            QPointF(0, 0), Qt.MoveAction, data,
            Qt.NoButton, Qt.NoModifier, QDropEvent.Drop)

    def test_run_query(self):
        w = AddonManagerDialog()

        query_res = [
            _QueryResult("uber-pkg", None),
            _QueryResult("unter-pkg", Installable("unter-pkg", "0.0.0", "", "", "", []))
        ]

        def query(names):
            return query_res

        with patch.object(QMessageBox, "exec", return_value=QMessageBox.Cancel), \
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
        with patch.object(PipInstaller, "install", lambda self, pkg: None), \
             patch.object(CondaInstaller, "install", lambda self, pkg: None), \
             patch.object(QMessageBox, "exec", return_value=QMessageBox.Cancel):
            b = w.findChild(QDialogButtonBox)
            b.accepted.emit()
            QTest.qWait(1)
            w.reject()
            QTest.qWait(1)

        w.deleteLater()


if __name__ == "__main__":
    unittest.main()

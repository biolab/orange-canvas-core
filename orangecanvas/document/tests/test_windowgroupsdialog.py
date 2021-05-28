from AnyQt.QtTest import QSignalSpy
from AnyQt.QtWidgets import QComboBox, QDialogButtonBox, QMessageBox

from orangecanvas.document.windowgroupsdialog import SaveWindowGroup
from orangecanvas.gui.test import QAppTestCase


class TestSaveWindowGroup(QAppTestCase):
    def test_dialog_default(self):
        w = SaveWindowGroup()
        w.setItems(["A", "B", "C"])
        w.setDefaultIndex(1)
        self.assertFalse(w.isDefaultChecked())
        cb = w.findChild(QComboBox)
        cb.setCurrentIndex(1)
        self.assertTrue(w.isDefaultChecked())

    def test_dialog_new(self):
        w = SaveWindowGroup()
        w.setItems(["A", "B", "C"])
        cb = w.findChild(QComboBox)
        bg = w.findChild(QDialogButtonBox)
        cb.setEditText("D")
        b = bg.button(QDialogButtonBox.Ok)
        spy = QSignalSpy(w.finished)
        # trigger accept
        b.click()
        self.assertSequenceEqual(list(spy), [[SaveWindowGroup.Accepted]])

    def test_dialog_overwrite(self):
        w = SaveWindowGroup()
        w.setItems(["A", "B", "C"])
        cb = w.findChild(QComboBox)
        bg = w.findChild(QDialogButtonBox)
        cb.setEditText("C")
        b = bg.button(QDialogButtonBox.Ok)
        spy = QSignalSpy(w.finished)
        # trigger accept and simulate confirm overwrite
        b.click()
        mb = w.findChild(QMessageBox)
        mb.done(QMessageBox.Yes)
        self.assertSequenceEqual(list(spy), [[SaveWindowGroup.Accepted]])


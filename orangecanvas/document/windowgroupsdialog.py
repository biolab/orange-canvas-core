from typing import List

from AnyQt.QtCore import Qt
from AnyQt.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QCheckBox,
    QDialogButtonBox, QMessageBox
)


class SaveWindowGroup(QDialog):
    """
    A dialog for saving window groups.

    The user can select an existing group to overwrite or enter a new group
    name.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        layout = QVBoxLayout()
        form = QFormLayout(
            fieldGrowthPolicy=QFormLayout.AllNonFixedFieldsGrow)
        layout.addLayout(form)
        self._combobox = cb = QComboBox(
            editable=True, minimumContentsLength=16,
            sizeAdjustPolicy=QComboBox.AdjustToMinimumContentsLengthWithIcon,
            insertPolicy=QComboBox.NoInsert,
        )
        cb.currentIndexChanged.connect(self.__currentIndexChanged)
        # default text if no items are present
        cb.setEditText(self.tr("Window Group 1"))
        cb.lineEdit().selectAll()
        form.addRow(self.tr("Save As:"), cb)
        self._checkbox = check = QCheckBox(
            self.tr("Use as default"),
            toolTip=self.tr("Automatically use this preset when opening "
                            "the workflow.")
        )
        form.setWidget(1, QFormLayout.FieldRole, check)
        bb = QDialogButtonBox(
            standardButtons=QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.__accept_check)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)
        layout.setSizeConstraint(QVBoxLayout.SetFixedSize)
        self.setLayout(layout)
        self.setWhatsThis(self.tr(
            "Save the current open widgets' window arrangement to the "
            "workflow view presets."
        ))
        cb.setFocus(Qt.NoFocusReason)

    def __currentIndexChanged(self, idx):
        # type: (int) -> None
        state = self._combobox.itemData(idx, Qt.UserRole + 1)
        if not isinstance(state, bool):
            state = False
        self._checkbox.setChecked(state)

    def __accept_check(self):
        # type: () -> None
        cb = self._combobox
        text = cb.currentText()
        if cb.findText(text) == -1:
            self.accept()
            return
        # Ask for overwrite confirmation
        mb = QMessageBox(
            self, windowTitle=self.tr("Confirm Overwrite"),
            icon=QMessageBox.Question,
            standardButtons=QMessageBox.Yes | QMessageBox.Cancel,
            text=self.tr("The window group '{}' already exists. Do you want " +
                         "to replace it?").format(text),
        )
        mb.setDefaultButton(QMessageBox.Yes)
        mb.setEscapeButton(QMessageBox.Cancel)
        mb.setWindowModality(Qt.WindowModal)
        button = mb.button(QMessageBox.Yes)
        button.setText(self.tr("Replace"))

        def on_finished(status):  # type: (int) -> None
            if status == QMessageBox.Yes:
                self.accept()
        mb.finished.connect(on_finished)
        mb.show()

    def setItems(self, items):
        # type: (List[str]) -> None
        """Set a list of existing items/names to present to the user"""
        self._combobox.clear()
        self._combobox.addItems(items)
        if items:
            self._combobox.setCurrentIndex(len(items) - 1)

    def setDefaultIndex(self, idx):
        # type: (int) -> None
        self._combobox.setItemData(idx, True, Qt.UserRole + 1)
        self._checkbox.setChecked(self._combobox.currentIndex() == idx)

    def selectedText(self):
        # type: () -> str
        """Return the current entered text."""
        return self._combobox.currentText()

    def isDefaultChecked(self):
        # type: () -> bool
        """Return the state of the 'Use as default' check box."""
        return self._checkbox.isChecked()

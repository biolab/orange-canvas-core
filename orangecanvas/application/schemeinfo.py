"""
Scheme Info editor widget.

"""
import typing
from typing import Optional

from AnyQt.QtWidgets import (
    QWidget, QDialog, QLabel, QTextEdit, QCheckBox, QFormLayout,
    QVBoxLayout, QHBoxLayout, QDialogButtonBox, QSizePolicy
)
from AnyQt.QtCore import Qt

from ..gui.lineedit import LineEdit
from ..gui.utils import StyledWidget_paintEvent, StyledWidget

if typing.TYPE_CHECKING:
    from ..scheme import Scheme


class SchemeInfoEdit(QWidget):
    """Scheme info editor widget.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scheme = None  # type: Optional[Scheme]
        self.__schemeIsUntitled = True
        self.__setupUi()

    def __setupUi(self):
        layout = QFormLayout()
        layout.setRowWrapPolicy(QFormLayout.WrapAllRows)
        layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        self.name_edit = LineEdit(self)
        self.name_edit.setPlaceholderText(self.tr("untitled"))
        self.name_edit.setSizePolicy(QSizePolicy.Expanding,
                                     QSizePolicy.Fixed)
        self.desc_edit = QTextEdit(self)
        self.desc_edit.setTabChangesFocus(True)

        layout.addRow(self.tr("Title"), self.name_edit)
        layout.addRow(self.tr("Description"), self.desc_edit)

        self.setLayout(layout)

    def setScheme(self, scheme):
        # type: (Scheme) -> None
        """Set the scheme to display/edit

        """
        self.scheme = scheme
        if not scheme.title:
            self.name_edit.setText(self.tr("untitled"))
            self.name_edit.selectAll()
            self.__schemeIsUntitled = True
        else:
            self.name_edit.setText(scheme.title)
            self.__schemeIsUntitled = False
        self.desc_edit.setPlainText(scheme.description or "")

    def commit(self):
        # type: () -> None
        """
        Commit the current contents of the editor widgets back to the scheme.
        """
        if self.scheme is None:
            return

        if self.__schemeIsUntitled and \
            self.name_edit.text() == self.tr("untitled"):
            # 'untitled' text was not changed
            name = ""
        else:
            name = self.name_edit.text().strip()

        description = self.desc_edit.toPlainText().strip()
        self.scheme.title = name
        self.scheme.description = description

    def paintEvent(self, event):
        return StyledWidget_paintEvent(self, event)

    def title(self):
        # type: () -> str
        return self.name_edit.text().strip()

    def description(self):
        # type: () -> str
        return self.desc_edit.toPlainText().strip()


class SchemeInfoDialog(QDialog):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scheme = None  # type: Optional[Scheme]
        self.__autoCommit = True

        self.__setupUi()

    def __setupUi(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.editor = SchemeInfoEdit(self)
        self.editor.layout().setContentsMargins(20, 20, 20, 20)
        self.editor.layout().setSpacing(15)
        self.editor.setSizePolicy(QSizePolicy.MinimumExpanding,
                                  QSizePolicy.MinimumExpanding)

        heading = self.tr("Workflow Info")
        heading = "<h3>{0}</h3>".format(heading)
        self.heading = QLabel(heading, self, objectName="heading")

        # Insert heading
        self.editor.layout().insertRow(0, self.heading)

        self.buttonbox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal,
            self
            )

        # Insert button box
        self.editor.layout().addRow(self.buttonbox)

        widget = StyledWidget(self, objectName="auto-show-container")
        check_layout = QHBoxLayout()
        check_layout.setContentsMargins(20, 10, 20, 10)
        self.__showAtNewSchemeCheck = \
            QCheckBox(self.tr("Show when I make a New Workflow."),
                      self,
                      objectName="auto-show-check",
                      checked=False,
                      )

        check_layout.addWidget(self.__showAtNewSchemeCheck)
        check_layout.addWidget(
               QLabel(self.tr("You can also edit Workflow Info later "
                              "(File -> Workflow Info)."),
                      self,
                      objectName="auto-show-info"),
               alignment=Qt.AlignRight)
        widget.setLayout(check_layout)
        widget.setSizePolicy(QSizePolicy.MinimumExpanding,
                             QSizePolicy.Fixed)

        if self.__autoCommit:
            self.buttonbox.accepted.connect(self.editor.commit)

        self.buttonbox.accepted.connect(self.accept)
        self.buttonbox.rejected.connect(self.reject)

        layout.addWidget(self.editor, stretch=10)
        layout.addWidget(widget)

        self.setLayout(layout)

    def setShowAtNewScheme(self, checked):
        # type: (bool) -> None
        """
        Set the 'Show at new scheme' check state.
        """
        self.__showAtNewSchemeCheck.setChecked(checked)

    def showAtNewScheme(self):
        # type: () -> bool
        """
        Return the check state of the 'Show at new scheme' check box.
        """
        return self.__showAtNewSchemeCheck.isChecked()

    def setAutoCommit(self, auto):
        # type: (bool) -> None
        if self.__autoCommit != auto:
            self.__autoCommit = auto
            if auto:
                self.buttonbox.accepted.connect(self.editor.commit)
            else:
                self.buttonbox.accepted.disconnect(self.editor.commit)

    def setScheme(self, scheme):
        # type: (Scheme) -> None
        """Set the scheme to display/edit.
        """
        self.scheme = scheme
        self.editor.setScheme(scheme)

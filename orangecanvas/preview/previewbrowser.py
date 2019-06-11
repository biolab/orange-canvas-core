"""
Preview Browser Widget.

"""
import os
from xml.sax.saxutils import escape


from AnyQt.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout
from AnyQt.QtSvg import QSvgWidget
from AnyQt.QtCore import Qt, QByteArray, QModelIndex, QAbstractItemModel
from AnyQt.QtCore import pyqtSignal as Signal

from ..gui.dropshadow import DropShadowFrame
from ..gui.iconview import LinearIconView
from ..gui.textlabel import TextLabel
from . import previewmodel


NO_PREVIEW_SVG = """

"""


# Default description template
DESCRIPTION_TEMPLATE = """
<h3 class=item-heading>{name}</h3>
<p class=item-description>
{description}
</p>

"""

PREVIEW_SIZE = (440, 295)


class PreviewBrowser(QWidget):
    """
    A Preview Browser for recent/example workflow selection.
    """
    # Emitted when the current previewed item changes
    currentIndexChanged = Signal(int)

    # Emitted when an item is double clicked in the preview list.
    activated = Signal(int)

    def __init__(self, *args, heading="", previewMargins=12, **kwargs):
        super().__init__(*args, **kwargs)
        self.__model = None
        self.__currentIndex = -1
        self.__template = DESCRIPTION_TEMPLATE
        self.__margin = previewMargins
        self.__setupUi()
        self.setHeading(heading)

    def __setupUi(self):
        vlayout = QVBoxLayout()
        vlayout.setContentsMargins(0, 0, 0, 0)
        top_layout = QVBoxLayout(objectName="top-layout")
        margin = self.__margin
        top_layout.setContentsMargins(margin, margin, margin, margin)
        # Optional heading label

        self.__heading = QLabel(
            self, objectName="heading", visible=False
        )
        # Horizontal row with full text description and a large preview
        # image.
        hlayout = QHBoxLayout()
        hlayout.setContentsMargins(0, 0, 0, 0)
        self.__label = QLabel(
            self, objectName="description-label",
            wordWrap=True, alignment=Qt.AlignTop | Qt.AlignLeft
        )

        self.__label.setWordWrap(True)
        self.__label.setFixedSize(220, PREVIEW_SIZE[1])
        self.__label.setMinimumWidth(PREVIEW_SIZE[0] // 2)
        self.__label.setMaximumHeight(PREVIEW_SIZE[1])

        self.__image = QSvgWidget(self, objectName="preview-image")
        self.__image.setFixedSize(*PREVIEW_SIZE)

        self.__imageFrame = DropShadowFrame(self)
        self.__imageFrame.setWidget(self.__image)

        hlayout.addWidget(self.__label)
        hlayout.addWidget(self.__image)

        # Path text below the description and image
        path_layout = QHBoxLayout()
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_label = QLabel("<b>{0!s}</b>".format(self.tr("Path:")), self,
                            objectName="path-label")
        self.__path = TextLabel(self, objectName="path-text")

        path_layout.addWidget(path_label)
        path_layout.addWidget(self.__path)

        top_layout.addWidget(self.__heading)
        top_layout.addLayout(hlayout)
        top_layout.addLayout(path_layout)

        vlayout.addLayout(top_layout)

        # An list view with small preview icons.
        self.__previewList = LinearIconView(
            objectName="preview-list-view",
            wordWrap=True
        )
        self.__previewList.doubleClicked.connect(self.__onDoubleClicked)

        vlayout.addWidget(self.__previewList)
        self.setLayout(vlayout)

    def setHeading(self, text):
        # type: (str) -> None
        """
        Set the heading text.

        Parameters
        ----------
        text: str
            The new heading text. If empty the heading is hidden.
        """
        self.__heading.setVisible(bool(text))
        self.__heading.setText(text)

    def setPreviewMargins(self, margin):
        # type: (int) -> None
        """
        Set the left, top and right margins of the top widget part (heading
        and description)

        Parameters
        ----------
        margin : int
            Margin
        """
        if margin != self.__margin:
            layout = self.layout().itemAt(0).layout()
            assert isinstance(layout, QVBoxLayout)
            assert layout.objectName() == "top-layout"
            layout.setContentsMargins(margin, margin, margin, 0)

    def setModel(self, model):
        # type: (QAbstractItemModel) -> None
        """
        Set the item model for preview.

        Parameters
        ----------
        model : QAbstractItemModel
        """
        if self.__model != model:
            if self.__model:
                s_model = self.__previewList.selectionModel()
                s_model.selectionChanged.disconnect(self.__onSelectionChanged)
                self.__model.dataChanged.disconnect(self.__onDataChanged)

            self.__model = model
            self.__previewList.setModel(model)

            if model:
                s_model = self.__previewList.selectionModel()
                s_model.selectionChanged.connect(self.__onSelectionChanged)
                self.__model.dataChanged.connect(self.__onDataChanged)

            if model and model.rowCount():
                self.setCurrentIndex(0)

    def model(self):
        # type: () -> QAbstractItemModel
        """
        Return the item model.
        """
        return self.__model

    def setDescriptionTemplate(self, template):
        self.__template = template
        self.__update()

    def setCurrentIndex(self, index):
        # type: (int) -> None
        """
        Set the selected preview item index.

        Parameters
        ----------
        index : int
            The current selected index.
        """
        if self.__model is not None and self.__model.rowCount():
            index = min(index, self.__model.rowCount() - 1)
            index = self.__model.index(index, 0)
            sel_model = self.__previewList.selectionModel()
            # This emits selectionChanged signal and triggers
            # __onSelectionChanged, currentIndex is updated there.
            sel_model.select(index, sel_model.ClearAndSelect)
        elif self.__currentIndex != -1:
            self.__currentIndex = -1
            self.__update()
            self.currentIndexChanged.emit(-1)

    def currentIndex(self):  # type: () -> int
        """
        Return the current selected index.
        """
        return self.__currentIndex

    def __onSelectionChanged(self):
        # type: () -> None
        """Selected item in the preview list has changed.
        Set the new description and large preview image.
        """
        rows = self.__previewList.selectedIndexes()
        if rows:
            index = rows[0]
            self.__currentIndex = index.row()
        else:
            self.__currentIndex = -1

        self.__update()
        self.currentIndexChanged.emit(self.__currentIndex)

    def __onDataChanged(self, topLeft, bottomRight):
        # type: (QModelIndex, QModelIndex) -> None
        """Data changed, update the preview if current index in the changed
        range.
        """
        if topLeft.row() <= self.__currentIndex <= bottomRight.row():
            self.__update()

    def __onDoubleClicked(self, index):
        # type: (QModelIndex) -> None
        """Double click on an item in the preview item list.
        """
        self.activated.emit(index.row())

    def __update(self):
        # type: () -> None
        """Update the current description.
        """
        if self.__currentIndex != -1:
            index = self.model().index(self.__currentIndex, 0)
        else:
            index = QModelIndex()

        if not index.isValid():
            description = ""
            name = ""
            path = ""
            svg = NO_PREVIEW_SVG
        else:
            description = index.data(Qt.WhatsThisRole)
            if description:
                description = description
            else:
                description = "No description."

            description = escape(description)
            description = description.replace("\n", "<br/>")

            name = index.data(Qt.DisplayRole)
            if name:
                name = name
            else:
                name = "Untitled"

            name = escape(name)
            path = str(index.data(Qt.StatusTipRole))
            svg = str(index.data(previewmodel.ThumbnailSVGRole))

        desc_text = self.__template.format(description=description, name=name)

        self.__label.setText(desc_text)

        self.__path.setText(contractuser(path))

        if not svg:
            svg = NO_PREVIEW_SVG

        if svg:
            self.__image.load(QByteArray(svg.encode("utf-8")))


def contractuser(path):
    # type: (str) -> str
    """
    Inverse of `expanduser(join("~", path))`

    Return the path unmodified if not under user's home dir.

    Parameters
    ----------
    path : str

    Returns
    -------
    path : str

    Examples
    --------
    >>> contractuser(os.path.expanduser("~/hello"))
    '~/hello'
    """
    home = os.path.expanduser("~/")
    pathnorm = os.path.normcase(os.path.normpath(path))
    homenorm = os.path.normcase(os.path.normpath(home))
    if pathnorm.startswith(homenorm):
        path = os.path.join("~", os.path.relpath(path, home))
    return path

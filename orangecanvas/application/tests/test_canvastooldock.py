"""
Test for canvas toolbox.
"""

from AnyQt.QtWidgets import QWidget, QToolBar, QTextEdit, QSplitter
from AnyQt.QtCore import Qt, QTimer

from ...registry import tests as registry_tests
from ...registry.qt import QtWidgetRegistry
from ...gui.dock import CollapsibleDockWidget

from ..canvastooldock import (
    WidgetToolBox, CanvasToolDock, SplitterResizer, QuickCategoryToolbar,
    CategoryPopupMenu
)

from ...gui import test


class TestCanvasDockWidget(test.QAppTestCase):
    def test_dock(self):
        reg = registry_tests.small_testing_registry()
        reg = QtWidgetRegistry(reg, parent=self.app)

        toolbox = WidgetToolBox()
        toolbox.setObjectName("widgets-toolbox")
        toolbox.setModel(reg.model())

        text = QTextEdit()
        splitter = QSplitter()
        splitter.setOrientation(Qt.Vertical)

        splitter.addWidget(toolbox)
        splitter.addWidget(text)

        dock = CollapsibleDockWidget()
        dock.setExpandedWidget(splitter)

        toolbar = QToolBar()
        toolbar.addAction("1")
        toolbar.setOrientation(Qt.Vertical)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        dock.setCollapsedWidget(toolbar)

        dock.show()
        self.qWait()

    def test_canvas_tool_dock(self):
        reg = registry_tests.small_testing_registry()
        reg = QtWidgetRegistry(reg, parent=self.app)

        dock = CanvasToolDock()
        dock.toolbox.setModel(reg.model())

        dock.show()
        self.qWait()

    def test_splitter_resizer(self):
        w = QSplitter(orientation=Qt.Vertical)
        w.addWidget(QWidget())
        text = QTextEdit()
        w.addWidget(text)
        resizer = SplitterResizer(parent=None)
        resizer.setSplitterAndWidget(w, text)

        def toogle():
            if resizer.size() == 0:
                resizer.open()
            else:
                resizer.close()

        w.show()
        timer = QTimer(resizer, interval=100)
        timer.timeout.connect(toogle)
        timer.start()
        toogle()
        self.qWait()
        timer.stop()

    def test_category_toolbar(self):
        reg = registry_tests.small_testing_registry()
        reg = QtWidgetRegistry(reg, parent=self.app)

        w = QuickCategoryToolbar()
        w.setModel(reg.model())
        w.show()
        self.qWait()


class TestPopupMenu(test.QAppTestCase):
    def test(self):
        reg = registry_tests.small_testing_registry()
        reg = QtWidgetRegistry(reg, parent=self.app)
        model = reg.model()

        w = CategoryPopupMenu()
        w.setModel(model)
        w.setRootIndex(model.index(0, 0))
        w.show()
        self.qWait()

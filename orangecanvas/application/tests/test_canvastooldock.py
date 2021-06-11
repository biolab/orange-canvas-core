"""
Test for canvas toolbox.
"""

from AnyQt.QtWidgets import (
    QWidget, QToolBar, QTextEdit, QSplitter, QApplication
)
from AnyQt.QtCore import Qt, QTimer, QPoint

from ...registry import tests as registry_tests
from ...registry.qt import QtWidgetRegistry
from ...gui.dock import CollapsibleDockWidget

from ..canvastooldock import (
    WidgetToolBox, CanvasToolDock, SplitterResizer, QuickCategoryToolbar,
    CategoryPopupMenu, popup_position_from_source, widget_popup_geometry
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
        w.popup()
        self.qWait()

    def test_popup_position(self):
        popup = CategoryPopupMenu()
        screen = popup.screen()
        screen_geom = screen.availableGeometry()
        popup.setMinimumHeight(screen_geom.height() + 20)
        w = QWidget()
        w.setGeometry(
            screen_geom.left() + 100, screen_geom.top() + 100, 20, 20
        )
        pos = popup_position_from_source(popup, w)
        self.assertTrue(screen_geom.contains(pos))
        pos = QPoint(screen_geom.top() - 100, screen_geom.left() - 100)
        geom = widget_popup_geometry(pos, popup)
        self.assertEqual(screen_geom.intersected(geom), geom)

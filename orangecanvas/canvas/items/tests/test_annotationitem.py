import math
import time

from AnyQt.QtGui import QColor
from AnyQt.QtCore import Qt, QRectF, QLineF, QTimer

from ..annotationitem import TextAnnotation, ArrowAnnotation, ArrowItem

from . import TestItems


class TestAnnotationItem(TestItems):
    def test_textannotation(self):
        text = "Annotation"
        annot = TextAnnotation()
        annot.setPlainText(text)
        self.assertEqual(annot.toPlainText(), text)

        annot2 = TextAnnotation()
        self.assertEqual(annot2.toPlainText(), "")

        text = "This is an annotation"
        annot2.setPlainText(text)
        self.assertEqual(annot2.toPlainText(), text)

        annot2.setDefaultTextColor(Qt.red)
        control_rect = QRectF(0, 0, 100, 200)
        annot2.setGeometry(control_rect)
        self.assertEqual(annot2.geometry(), control_rect)

        annot.setTextInteractionFlags(Qt.TextEditorInteraction)
        annot.setPos(400, 100)
        annot.adjustSize()
        annot._TextAnnotation__textItem.setFocus()
        self.scene.addItem(annot)
        self.scene.addItem(annot2)
        self.qWait()

    def test_arrowannotation(self):
        item = ArrowItem()
        self.scene.addItem(item)
        item.setLine(QLineF(100, 100, 100, 200))
        item.setLineWidth(5)

        item = ArrowItem()
        item.setLine(QLineF(150, 100, 150, 200))
        item.setLineWidth(10)
        item.setArrowStyle(ArrowItem.Concave)
        self.scene.addItem(item)

        item = ArrowAnnotation()
        item.setPos(10, 10)
        item.setLine(QLineF(10, 10, 200, 200))

        self.scene.addItem(item)
        item.setLineWidth(5)

        def advance():
            clock = time.process_time() * 10
            item.setLineWidth(5 + math.sin(clock) * 5)
            item.setColor(QColor(Qt.red).lighter(100 + int(30 * math.cos(clock))))

        timer = QTimer(item, interval=10)
        timer.timeout.connect(advance)
        timer.start()
        self.qWait()
        timer.stop()

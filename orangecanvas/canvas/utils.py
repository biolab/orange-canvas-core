from AnyQt.QtCore import QT_VERSION, QBuffer, QRectF, Qt
from AnyQt.QtGui import QPainter
from AnyQt.QtWidgets import QGraphicsScene
from AnyQt.QtSvg import QSvgGenerator

if QT_VERSION >= 0x50900 and \
      QSvgGenerator().metric(QSvgGenerator.PdmDevicePixelRatioScaled) == 1:
    # QTBUG-63159
    class _QSvgGenerator(QSvgGenerator):  # type: ignore
        def metric(self, metric):
            if metric == QSvgGenerator.PdmDevicePixelRatioScaled:
                return int(1 * QSvgGenerator.devicePixelRatioFScale())
            else:
                return super().metric(metric)

else:
    _QSvgGenerator = QSvgGenerator  # type: ignore


def grab_svg(scene: QGraphicsScene) -> str:
    """
    Return a SVG rendering of the `scene`\\'s contents.

    Parameters
    ----------
    scene : :class:`QGraphicScene`
    """
    svg_buffer = QBuffer()
    gen = _QSvgGenerator()
    views = scene.views()
    if views:
        screen = views[0].screen()
        if screen is not None:
            res = screen.physicalDotsPerInch()
            gen.setResolution(int(res))
    gen.setOutputDevice(svg_buffer)

    items_rect = scene.itemsBoundingRect().adjusted(-10, -10, 10, 10)

    if items_rect.isNull():
        items_rect = QRectF(0, 0, 10, 10)

    width, height = items_rect.width(), items_rect.height()
    rect_ratio = float(width) / height

    # Keep a fixed aspect ratio.
    aspect_ratio = 1.618
    if rect_ratio > aspect_ratio:
        height = int(height * rect_ratio / aspect_ratio)
    else:
        width = int(width * aspect_ratio / rect_ratio)

    target_rect = QRectF(0, 0, width, height)
    source_rect = QRectF(0, 0, width, height)
    source_rect.moveCenter(items_rect.center())

    gen.setSize(target_rect.size().toSize())
    gen.setViewBox(target_rect)

    painter = QPainter(gen)

    # Draw background.
    painter.setPen(Qt.NoPen)
    painter.setBrush(scene.palette().base())
    painter.drawRect(target_rect)

    # Render the scene
    scene.render(painter, target_rect, source_rect)
    painter.end()

    buffer_str = bytes(svg_buffer.buffer())
    return buffer_str.decode("utf-8")

from itertools import count

from AnyQt.QtCore import Qt, QSize, QRect, QRectF
from AnyQt.QtGui import QIconEngine, QIcon, QPixmap, QPainter, QPixmapCache
from AnyQt.QtSvg import QSvgRenderer
from AnyQt.QtWidgets import QStyleOption, QApplication

_cache_id_gen = count()


class SvgIconEngine(QIconEngine):
    """
    An svg icon engine reimplementation drawing from in-memory svg contents.

    Arguments
    ---------
    contents : bytes
        The svg icon contents
    """
    __slots__ = ("__contents", "__generator", "__cache_id")

    def __init__(self, contents):
        # type: (bytes) -> None
        super().__init__()
        self.__contents = contents
        self.__generator = QSvgRenderer(contents)
        self.__cache_id = next(_cache_id_gen)

    def paint(self, painter, rect, mode, state):
        # type: (QPainter, QRect, QIcon.Mode, QIcon.State) -> None
        if self.__generator.isValid():
            size = rect.size()
            dpr = 1.0
            try:
                dpr = painter.device().devicePixelRatioF()
            except AttributeError:
                pass
            if dpr != 1.0:
                size = size * dpr
            painter.drawPixmap(rect, self.pixmap(size, mode, state))

    def pixmap(self, size, mode, state):
        # type: (QSize, QIcon.Mode, QIcon.State) -> QPixmap
        if not self.__generator.isValid():
            return QPixmap()

        dsize = self.__generator.defaultSize()  # type: QSize
        if not dsize.isNull():
            dsize.scale(size, Qt.KeepAspectRatio)
            size = dsize
        key = "{}.SVGIconEngine/{}/{}x{}".format(
            __name__, self.__cache_id, size.width(), size.height()
        )
        pm = QPixmapCache.find(key)
        if pm is None or pm.isNull():
            pm = QPixmap(size)
            pm.fill(Qt.transparent)
            painter = QPainter(pm)
            try:
                self.__generator.render(
                    painter, QRectF(0, 0, size.width(), size.height()))
            finally:
                painter.end()
            QPixmapCache.insert(key, pm)
        style = QApplication.style()
        if style is not None:
            opt = QStyleOption()
            opt.palette = QApplication.palette()
            pm = style.generatedIconPixmap(mode, pm, opt)
        return pm

    def clone(self):
        # type: () -> QIconEngine
        return SvgIconEngine(self.__contents)

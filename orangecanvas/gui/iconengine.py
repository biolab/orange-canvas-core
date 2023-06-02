from itertools import count
from contextlib import contextmanager
from typing import Optional

from AnyQt.QtCore import Qt, QObject, QSize, QRect, QT_VERSION_INFO
from AnyQt.QtGui import (
    QIconEngine, QPalette, QIcon, QPixmap, QPixmapCache, QImage, QPainter
)
from AnyQt.QtWidgets import QApplication, QStyleOption

from orangecanvas.gui.utils import luminance
from orangecanvas.utils.image import grayscale_invert

__all__ = [
    "StyledIconEngine",
    "SymbolIconEngine",
]


_cache_id_gen = count()


class StyledIconEngine(QIconEngine):
    """
    An abstract base class for icon engines that adapt to effective palette.
    """
    __slots__ = ("__palette", "__styleObject")

    def __init__(self, *args, palette: Optional[QPalette] = None,
                 styleObject: Optional[QObject] = None, **kwargs):
        self.__palette = QPalette(palette) if palette is not None else None
        self.__styleObject = styleObject
        super().__init__(*args, **kwargs)

    @staticmethod
    def paletteFromStyleObject(obj: QObject) -> Optional[QPalette]:
        palette = obj.property("palette")
        if isinstance(palette, QPalette):
            return palette
        else:
            return None

    __paletteOverride = None

    @staticmethod
    @contextmanager
    def setOverridePalette(palette: QPalette):
        """
        Temporarily override used QApplication.palette() with this class.

        This can be used when the icon is drawn on a non default background
        and as such might not contrast with it when using the default palette,
        and neither paint device nor styleObject can be used for this.
        """
        old = StyledIconEngine.__paletteOverride
        try:
            StyledIconEngine.__paletteOverride = palette
            yield
        finally:
            StyledIconEngine.__paletteOverride = old

    @staticmethod
    def paletteOverride() -> Optional[QPalette]:
        return StyledIconEngine.__paletteOverride

    def effectivePalette(self) -> QPalette:
        if StyledIconEngine.__paletteOverride is not None:
            return StyledIconEngine.__paletteOverride
        if self.__palette is not None:
            return self.__palette
        elif self.__styleObject is not None:
            palette = self.paletteFromStyleObject(self.__styleObject)
            if palette is not None:
                return palette
        return QApplication.palette()


# shorthands for eliminating runtime attr load in hot path
_QIcon_Active_Modes = (QIcon.Active, QIcon.Selected)
_QIcon_Disabled = QIcon.Disabled

_QPalette_Active = QPalette.Active
_QPalette_WindowText = QPalette.WindowText
_QPalette_Disabled = QPalette.Disabled
_QPalette_HighlightedText = QPalette.HighlightedText


class SymbolIconEngine(StyledIconEngine):
    """
    A *Symbolic* icon engine adapter for turning simple grayscale base icon
    to current effective appearance.

    Arguments
    ---------
    base: QIcon
        The base icon.
    """
    def __init__(self, base: QIcon):
        super().__init__()
        self.__base = QIcon(base)
        self.__cache_key = next(_cache_id_gen)

    def paint(
            self, painter: QPainter, rect: QRect, mode: QIcon.Mode,
            state: QIcon.State
    ) -> None:
        if not self.__base.isNull():
            palette = self.effectivePalette()
            size = rect.size()
            dpr = painter.device().devicePixelRatioF()
            size = size * dpr
            pm = self.__renderStyledPixmap(size, mode, state, palette)
            painter.drawPixmap(rect, pm)

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        return self.__renderStyledPixmap(size, mode, state, self.effectivePalette())

    def __renderStyledPixmap(
            self, size: QSize, mode: QIcon.Mode, state: QIcon.State,
            palette: QPalette
    ) -> QPixmap:
        active = mode in _QIcon_Active_Modes
        disabled = mode == _QIcon_Disabled
        cg = _QPalette_Disabled if disabled else _QPalette_Active
        role = _QPalette_WindowText if active else _QPalette_HighlightedText
        namespace = f"{__name__}:SymbolIconEngine/{self.__cache_key}"
        cachekey = f"{size.width()}x{size.height()}"
        style_key = f"{hex(palette.cacheKey())}-{cg}-{role}"
        pmcachekey = f"{namespace}/{cachekey}/{style_key}"
        pm = QPixmapCache.find(pmcachekey)
        if pm is None or pm.isNull():
            color = palette.color(QPalette.Text)
            src = qicon_pixmap(self.__base, size, 1.0, mode, state)
            src = src.toImage().convertToFormat(QImage.Format_ARGB32_Premultiplied)
            if luminance(color) > 0.5:
                dest = grayscale_invert(
                    src,
                    palette.color(QPalette.Text),
                    palette.color(QPalette.Base),
                )
            else:
                dest = src
            pm = QPixmap.fromImage(dest)
            QPixmapCache.insert(pmcachekey, pm)

        self.__style = style = QApplication.style()
        if style is not None:
            opt = QStyleOption()
            opt.palette = palette
            pm = style.generatedIconPixmap(mode, pm, opt)
        return pm

    def clone(self) -> 'QIconEngine':
        return SymbolIconEngine(self.__base)


def qicon_pixmap(
        base: QIcon, size: QSize, scale: float, mode: QIcon.Mode,
        state: QIcon.State
) -> QPixmap:
    """
    Like QIcon.pixmap(size: QSize, scale: float, ...) overload in Qt6.

    On Qt 6 this directly calls the corresponding overload.
    On Qt 5 this is emulated by painting on a suitable constructed pixmap.
    """
    size = base.actualSize(size * scale, mode, state)
    pm = QPixmap(size)
    pm.setDevicePixelRatio(scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    base.paint(p, 0, 0, size.width(), size.height(), Qt.AlignCenter, mode, state)
    p.end()
    return pm


if QT_VERSION_INFO >= (6, 0):
    qicon_pixmap = QIcon.pixmap

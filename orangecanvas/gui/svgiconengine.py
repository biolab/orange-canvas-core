import io
from contextlib import contextmanager

from typing import IO, Optional

from itertools import count
from xml.sax import make_parser, handler, saxutils

from AnyQt.QtCore import Qt, QSize, QRect, QRectF, QObject
from AnyQt.QtGui import (
    QIconEngine, QIcon, QPixmap, QPainter, QPixmapCache, QPalette, QColor,
    QPaintDevice
)
from AnyQt.QtSvg import QSvgRenderer
from AnyQt.QtWidgets import QStyleOption, QApplication

from .utils import luminance, merged_color

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
        self.__renderer = QSvgRenderer(contents)
        self.__cache_id = next(_cache_id_gen)

    def paint(self, painter, rect, mode, state):
        # type: (QPainter, QRect, QIcon.Mode, QIcon.State) -> None
        if self.__renderer.isValid():
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
        if not self.__renderer.isValid():
            return QPixmap()

        dsize = self.__renderer.defaultSize()  # type: QSize
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
            self.__renderer.render(
                painter, QRectF(0, 0, size.width(), size.height()))
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


class StyledSvgIconEngine(QIconEngine):
    """
    A basic styled icon engine based on a QPalette colors.

    This engine can draw css styled svg icons of specific format so as to
    conform to the current color scheme based on effective `QPalette`.

    (Loosely based on KDE's KIconLoader)

    Parameters
    ----------
    contents: str
        The svg icon content.
    palette: Optional[QPalette]
        A fixed palette colors to use.
    styleObject: Optional[QObject]
        An optional QObject whose 'palette' property defines the effective
        palette.

    If neither `palette` nor `styleObject` are specified then the current
    `QApplication.palette` is used.
    """
    __slots__ = (
        "__contents", "__styled_contents_cache", "__palette", "__renderer",
        "__cache_key", "__style_object",
    )

    def __init__(
            self,
            contents: bytes,
            *,
            palette: Optional[QPalette] = None,
            styleObject: Optional[QObject] = None,
    ) -> None:
        super().__init__()
        self.__contents = contents
        self.__styled_contents_cache = {}
        if palette is not None and styleObject is not None:
            raise TypeError("only one of palette or styleObject can be defined")
        self.__palette = QPalette(palette) if palette is not None else None
        self.__renderer = QSvgRenderer(contents)
        self.__cache_key = next(_cache_id_gen)
        self.__style_object = styleObject

    @staticmethod
    def __paletteFromPaintDevice(dev: QPaintDevice) -> Optional[QPalette]:
        if isinstance(dev, QObject):
            palette_ = dev.property("palette")
            if isinstance(palette_, QPalette):
                return palette_
        return None

    @staticmethod
    def __paletteFromStyleObject(obj: QObject) -> Optional[QPalette]:
        palette = obj.property("palette")
        if isinstance(palette, QPalette):
            return palette
        else:
            return None

    def paint(self, painter, rect, mode, state):
        # type: (QPainter, QRect, QIcon.Mode, QIcon.State) -> None
        if self.__renderer.isValid():
            if self.__paletteOverride is not None:
                palette = self.__paletteOverride
            elif self.__palette is None:
                palette = self.__paletteFromPaintDevice(painter.device())
                if palette is None:
                    palette = self._palette()
            else:
                palette = self._palette()
            size = rect.size()
            dpr = painter.device().devicePixelRatioF()
            size = size * dpr
            pm = self.__renderStyledPixmap(size, mode, state, palette)
            painter.drawPixmap(rect, pm)

    def _palette(self) -> QPalette:
        if self.__paletteOverride is not None:
            return self.__paletteOverride
        if self.__palette is not None:
            return self.__palette
        elif self.__style_object is not None:
            palette = self.__paletteFromStyleObject(self.__style_object)
            if palette is not None:
                return palette

        if self.__paletteOverride is not None:
            return QPalette(self.__paletteOverride)
        return QApplication.palette()

    def pixmap(self, size, mode, state):
        # type: (QSize, QIcon.Mode, QIcon.State) -> QPixmap
        return self.__renderStyledPixmap(size, mode, state, self._palette())

    def __renderStyledPixmap(
            self, size: QSize, mode: QIcon.Mode, state: QIcon.State,
            palette: QPalette
    ) -> QPixmap:
        active = mode in (QIcon.Active, QIcon.Selected)
        disabled = mode == QIcon.Disabled
        cg = QPalette.Disabled if disabled else QPalette.Active
        role = QPalette.HighlightedText if active else QPalette.WindowText
        namespace = "{}:{}/{}/".format(
            __name__, __class__.__name__, self.__cache_key)
        style_key = "{}-{}-{}".format(hex(palette.cacheKey()), cg, role)
        renderer = self.__styled_contents_cache.get(style_key)
        if renderer is None:
            css = render_svg_color_scheme_css(palette, state)
            contents_ = replace_css_style(io.BytesIO(self.__contents), css)
            renderer = QSvgRenderer(contents_)
            self.__styled_contents_cache[style_key] = renderer

        if not renderer.isValid():
            return QPixmap()

        dsize = renderer.defaultSize()  # type: QSize

        if not dsize.isNull():
            dsize.scale(size, Qt.KeepAspectRatio)
            size = dsize

        pmcachekey = namespace + style_key + \
                     "/{}x{}".format(size.width(), size.height())
        pm = QPixmapCache.find(pmcachekey)
        if pm is None or pm.isNull():
            pm = QPixmap(size)
            pm.fill(Qt.transparent)
            painter = QPainter(pm)
            renderer.render(painter, QRectF(0, 0, size.width(), size.height()))
            painter.end()
            QPixmapCache.insert(pmcachekey, pm)

        style = QApplication.style()
        if style is not None:
            opt = QStyleOption()
            opt.palette = palette
            pm = style.generatedIconPixmap(mode, pm, opt)
        return pm

    def clone(self) -> 'QIconEngine':
        return StyledSvgIconEngine(
            self.__contents,
            palette=self.__palette,
            styleObject=self.__style_object
        )

    __paletteOverride = None

    @classmethod
    @contextmanager
    def setOverridePalette(cls, palette: QPalette):
        """
        Temporarily override used QApplication.palette() with this class.

        This can be used when the icon is drawn on a non default background
        and as such might not contrast with it when using the default palette,
        and neither paint device nor styleObject can be used for this.
        """
        old = StyledSvgIconEngine.__paletteOverride
        try:
            StyledSvgIconEngine.__paletteOverride = palette
            yield
        finally:
            StyledSvgIconEngine.__paletteOverride = old


#: Like KDE's KIconLoader
TEMPLATE = """
* {{
    color: {text};
}}
.ColorScheme-Text {{
    color: {text};
}}
.ColorScheme-Background {{
    color: {background};
}}
.ColorScheme-Highlight {{
    color: {highlight};
}}
.ColorScheme-Disabled-Text {{
    color: {disabled_text};
}}
.ColorScheme-Contrast {{
    color: {contrast};
}}
.ColorScheme-Complement {{
    color: {complement};
}}
"""


def _hexrgb_solid(color: QColor) -> str:
    """
    Return a #RRGGBB color string from color. If color has alpha component
    multipy the color components with alpha to get a solid color.
    """
    # On macOS the disabled text color is black/white with an alpha
    # component but QtSvg does not support alpha component declarations
    # (in hex or rgba syntax) so we pre-multiply with alpha to get solid
    # gray scale.
    if color.alpha() != 255:
        contrast = QColor(Qt.black) if luminance(color) else QColor(Qt.white)
        color = merged_color(color, contrast, color.alphaF())
    return color.name(QColor.HexRgb)


def render_svg_color_scheme_css(palette: QPalette, state: QIcon.State) -> str:
    selected = state == QIcon.Selected
    text = QPalette.HighlightedText if selected else QPalette.WindowText
    background = QPalette.Highlight if selected else QPalette.Window
    hligh = QPalette.HighlightedText if selected else QPalette.Highlight
    lum = luminance(palette.color(background))
    complement = QColor(Qt.white) if lum > 0.5 else QColor(Qt.black)
    contrast = QColor(Qt.black) if lum > 0.5 else QColor(Qt.white)
    return TEMPLATE.format(
        text=_hexrgb_solid(palette.color(text)),
        background=_hexrgb_solid(palette.color(background)),
        highlight=_hexrgb_solid(palette.color(hligh)),
        disabled_text=_hexrgb_solid(palette.color(QPalette.Disabled, text)),
        contrast=_hexrgb_solid(contrast),
        complement=_hexrgb_solid(complement),
    )


def replace_css_style(
        svgcontents: IO, stylesheet: str, id="current-color-scheme",
) -> bytes:
    """
    Insert/replace an inline css style in the svgcontents with `stylesheet`.

    Parameters
    ----------
    svgcontents: IO
        A file like stream object open for reading.
    stylesheet: str
        CSS contents to insert.
    id: str
        The if of the existing <style id='...'>... node in svg. This node is
        replaced with the `stylesheet`.
    """
    class StyleReplaceFilter(saxutils.XMLFilterBase):
        _in_style = False

        def startElement(self, tag, attrs):
            if tag == "style" and attrs.get("id") == id:
                # replace a <style id="current-color-scheme" ...> ...</style>
                # with the supplied stylesheet.
                super().startElement("style", attrs)
                super().characters("\n" + stylesheet + "\n")
                super().endElement("style")
                self._in_style = True
            else:
                super().startElement(tag, attrs)

        def characters(self, content):
            # skip original css style contents
            if not self._in_style:
                super().characters(content)

        def endElement(self, name):
            if self._in_style and name == "style":
                self._in_style = False
            else:
                super().endElement(name)

    buffer = io.BytesIO()
    writer = saxutils.XMLGenerator(out=buffer, encoding="utf-8")

    # build the parser and disable external entity resolver (bpo-17239)
    # (this is the default in Python 3.8)
    parser = make_parser()
    parser.setFeature(handler.feature_external_ges, False)
    parser.setFeature(handler.feature_external_pes, False)

    filter = StyleReplaceFilter(parent=parser)
    filter.setContentHandler(writer)
    filter.parse(svgcontents)
    return buffer.getvalue()

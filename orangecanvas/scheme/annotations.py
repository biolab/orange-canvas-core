"""
==================
Scheme Annotations
==================

"""
from typing import Tuple, Optional, Any

from AnyQt.QtCore import QObject
from AnyQt.QtCore import pyqtSignal as Signal, pyqtProperty as Property

from ..utils import check_type

Pos = Tuple[float, float]
Rect = Tuple[float, float, float, float]


class BaseSchemeAnnotation(QObject):
    """
    Base class for scheme annotations.
    """
    # Signal emitted when the geometry of the annotation changes
    geometry_changed = Signal()


class SchemeArrowAnnotation(BaseSchemeAnnotation):
    """
    An arrow annotation in the scheme.
    """

    color_changed = Signal(str)

    def __init__(self, start_pos, end_pos, color="red", anchor=None,
                 parent=None):
        # type: (Pos, Pos, str, Any, Optional[QObject]) -> None
        super().__init__(parent)
        self.__start_pos = start_pos
        self.__end_pos = end_pos
        self.__color = color
        self.__anchor = anchor

    def set_line(self, start_pos, end_pos):
        # type: (Pos, Pos) -> None
        """
        Set arrow lines start and end position (``(x, y)`` tuples).
        """
        if self.__start_pos != start_pos or self.__end_pos != end_pos:
            self.__start_pos = start_pos
            self.__end_pos = end_pos
            self.geometry_changed.emit()

    def _start_pos(self):
        # type: () -> Pos
        """
        Start position of the arrow (base point).
        """
        return self.__start_pos

    start_pos: Pos
    start_pos = Property(tuple, _start_pos)  # type: ignore

    def _end_pos(self):
        """
        End position of the arrow (arrow head points toward the end).
        """
        return self.__end_pos

    end_pos: Pos
    end_pos = Property(tuple, _end_pos)  # type: ignore

    def set_geometry(self, geometry):
        # type: (Tuple[Pos, Pos]) -> None
        """
        Set the geometry of the arrow as a start and end position tuples
        (e.g. ``set_geometry(((0, 0), (100, 0))``).

        """
        (start_pos, end_pos) = geometry
        self.set_line(start_pos, end_pos)

    def _geometry(self):
        # type: () -> Tuple[Pos, Pos]
        """
        Return the start and end positions of the arrow.
        """
        return (self.start_pos, self.end_pos)

    geometry: Tuple[Pos, Pos]
    geometry = Property(tuple, _geometry, set_geometry)  # type: ignore

    def set_color(self, color):
        # type: (str) -> None
        """
        Set the fill color for the arrow as a string (`#RGB`, `#RRGGBB`,
        `#RRRGGGBBB`, `#RRRRGGGGBBBB` format or one of SVG color keyword
        names).

        """
        if self.__color != color:
            self.__color = color
            self.color_changed.emit(color)

    def _color(self):
        # type: () -> str
        """
        The arrow's fill color.
        """
        return self.__color

    color: str
    color = Property(str, _color, set_color)  # type: ignore

    def __getstate__(self):
        return self.__start_pos, \
               self.__end_pos, \
               self.__color, \
               self.__anchor, \
               self.parent()

    def __setstate__(self, state):
        self.__init__(*state)


class SchemeTextAnnotation(BaseSchemeAnnotation):
    """
    Text annotation in the scheme.
    """

    # Signal emitted when the annotation content change.
    content_changed = Signal(str, str)

    # Signal emitted when the annotation text changes.
    text_changed = Signal(str)

    # Signal emitted when the annotation text font changes.
    font_changed = Signal(dict)

    def __init__(self, rect, text="", content_type="text/plain", font=None,
                 anchor=None, parent=None):
        # type: (Rect, str, str, Optional[dict], Any, Optional[QObject]) -> None
        super().__init__(parent)
        self.__rect = rect  # type: Rect
        self.__content = text
        self.__content_type = content_type
        self.__font = {} if font is None else font
        self.__anchor = anchor

    def set_rect(self, rect):
        # type: (Rect) -> None
        """
        Set the text geometry bounding rectangle (``(x, y, width, height)``
        tuple).
        """
        if self.__rect != rect:
            self.__rect = rect
            self.geometry_changed.emit()

    def _rect(self):
        # type: () -> Rect
        """
        Text bounding rectangle
        """
        return self.__rect

    rect: Rect
    rect = Property(tuple, _rect, set_rect)  # type: ignore

    def set_geometry(self, rect):
        # type: (Rect) -> None
        """
        Set the text geometry (same as ``set_rect``)
        """
        self.set_rect(rect)

    def _geometry(self):
        # type: () -> Rect
        """
        Text annotation geometry (same as ``rect``)
        """
        return self.__rect

    geometry: Rect
    geometry = Property(tuple, _geometry, set_geometry)  # type: ignore

    def set_text(self, text):
        # type: (str) -> None
        """
        Set the annotation text.

        Same as `set_content(text, "text/plain")`
        """
        self.set_content(text, "text/plain")

    def _text(self):
        # type: () -> str
        """
        Annotation text.

        .. deprecated::
            Use `content` instead.
        """
        return self.__content

    text: str
    text = Property(str, _text, set_text)  # type: ignore

    @property
    def content_type(self):
        # type: () -> str
        """
        Return the annotations' content type.

        Currently this will be 'text/plain', 'text/html' or 'text/rst'.
        """
        return self.__content_type

    @property
    def content(self):
        # type: () -> str
        """
        The annotation content.

        How the content is interpreted/displayed depends on `content_type`.
        """
        return self.__content

    def set_content(self, content, content_type="text/plain"):
        # type: (str, str) -> None
        """
        Set the annotation content.

        Parameters
        ----------
        content : str
            The content.
        content_type : str
            Content type. Currently supported are 'text/plain' 'text/html'
            (subset supported by `QTextDocument`) and `text/rst`.
        """
        if self.__content != content or self.__content_type != content_type:
            text_changed = self.__content != content
            self.__content = content
            self.__content_type = content_type
            self.content_changed.emit(content, content_type)
            if text_changed:
                self.text_changed.emit(content)

    def set_font(self, font):
        # type: (dict) -> None
        """
        Set the annotation's default font as a dictionary of font properties
        (at the moment only family and size are used).

            >>> annotation.set_font({"family": "Helvetica", "size": 16})

        """
        check_type(font, dict)
        font = dict(font)
        if self.__font != font:
            self.__font = font
            self.font_changed.emit(font)

    def _font(self):
        # type: () -> dict
        """
        Annotation's font property dictionary.
        """
        return dict(self.__font)

    font: dict
    font = Property(object, _font, set_font)  # type: ignore

    def __getstate__(self):
        return self.__rect, \
               self.__content, \
               self.__content_type, \
               self.__font, \
               self.__anchor, \
               self.parent()

    def __setstate__(self, state):
        self.__init__(*state)

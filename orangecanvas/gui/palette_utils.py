from AnyQt.QtWidgets import (
    QApplication
)
from AnyQt.QtGui import (
    QColor, QPalette
)

from orangecanvas.registry import NAMED_COLORS, DEFAULT_COLOR
from orangecanvas.gui.utils import saturated, foreground_for_background


def create_palette(background):
    # type: (Any) -> QPalette
    """
    Return a new :class:`QPalette` from for the :class:`NodeBodyItem`.
    """
    app = QApplication.instance()
    darkMode = app.property('darkMode')

    defaults = {
        # Canvas widget background radial gradient
        QPalette.Light:
            lambda color: saturated(color, 50),
        QPalette.Midlight:
            lambda color: saturated(color, 90),
        QPalette.Button:
            lambda color: color,
        # Canvas widget shadow
        QPalette.Shadow:
            lambda color: saturated(color, 125) if darkMode else
                          saturated(color, 150),

        # Category tab color
        QPalette.Highlight:
            lambda color: color,

        QPalette.HighlightedText:
            lambda color: foreground_for_background(color),
    }

    palette = QPalette()

    if isinstance(background, dict):
        if app.property('darkMode'):
            background = background.get('dark', next(iter(background.values())))
        else:
            background = background.get('light', next(iter(background.values())))
        base_color = background[QPalette.Button]
        base_color = QColor(base_color)
    else:
        color = NAMED_COLORS.get(background, background)
        color = QColor(background)
        if color.isValid():
            base_color = color
        else:
            color = NAMED_COLORS[DEFAULT_COLOR]
            base_color = QColor(color)

    for role, default in defaults.items():
        if isinstance(background, dict) and role in background:
            v = background[role]
            color = NAMED_COLORS.get(v, v)
            color = QColor(color)
            if color.isValid():
                palette.setColor(role, color)
                continue
        color = default(base_color)
        palette.setColor(role, color)

    return palette


def default_palette():
    # type: () -> QPalette
    """
    Create and return a default palette for a node.
    """
    return create_palette(DEFAULT_COLOR)

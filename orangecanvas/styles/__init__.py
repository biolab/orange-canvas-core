"""
QSS style sheets.
"""
from typing import Mapping, Callable

from AnyQt.QtCore import Qt
from AnyQt.QtGui import QPalette, QColor


def breeze_dark() -> QPalette:
    # 'Breeze Dark' color scheme from KDE.
    text = QColor(239, 240, 241)
    textdisabled = QColor(98, 108, 118)
    window = QColor(49, 54, 59)
    base = QColor(35, 38, 41)
    highlight = QColor(61, 174, 233)
    link = QColor(41, 128, 185)

    light = QColor(69, 76, 84)
    mid = QColor(43, 47, 52)
    dark = QColor(28, 31, 34)
    shadow = QColor(20, 23, 25)

    palette = QPalette()
    palette.setColor(QPalette.Window, window)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Disabled, QPalette.WindowText, textdisabled)
    palette.setColor(QPalette.Base, base)
    palette.setColor(QPalette.AlternateBase, window)
    palette.setColor(QPalette.ToolTipBase, window)
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Disabled, QPalette.Text, textdisabled)
    palette.setColor(QPalette.Button, window)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, textdisabled)
    palette.setColor(QPalette.BrightText, Qt.white)
    palette.setColor(QPalette.Highlight, highlight)
    palette.setColor(QPalette.HighlightedText, text)
    palette.setColor(QPalette.Light, light)
    palette.setColor(QPalette.Mid, mid)
    palette.setColor(QPalette.Dark, dark)
    palette.setColor(QPalette.Shadow, shadow)
    palette.setColor(QPalette.Link, link)
    return palette


def zion_reversed() -> QPalette:
    # 'Zion Reversed' color scheme from KDE.
    text = Qt.white
    textdisabled = QColor(85, 85, 85)
    window = QColor(16, 16, 16)
    base = Qt.black
    highlight = QColor(0, 49, 110)
    highlight_disabled = window
    link = QColor(128, 181, 255)

    light = QColor(174, 174, 174)
    mid = QColor(89, 89, 89)
    dark = QColor(118, 118, 118)
    shadow = QColor(141, 141, 141)

    palette = QPalette()
    palette.setColor(QPalette.Window, window)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Disabled, QPalette.WindowText, textdisabled)
    palette.setColor(QPalette.Base, base)
    palette.setColor(QPalette.AlternateBase, window)
    palette.setColor(QPalette.Disabled, QPalette.Base, window)
    palette.setColor(QPalette.Disabled, QPalette.AlternateBase, window)
    palette.setColor(QPalette.ToolTipBase, window)
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Disabled, QPalette.Text, textdisabled)
    palette.setColor(QPalette.Button, window)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, textdisabled)
    palette.setColor(QPalette.BrightText, Qt.white)
    palette.setColor(QPalette.Highlight, highlight)
    palette.setColor(QPalette.Disabled, QPalette.Highlight, highlight_disabled)
    palette.setColor(QPalette.HighlightedText, text)
    palette.setColor(QPalette.Light, light)
    palette.setColor(QPalette.Mid, mid)
    palette.setColor(QPalette.Dark, dark)
    palette.setColor(QPalette.Shadow, shadow)
    palette.setColor(QPalette.Link, link)
    return palette


def dark():
    text = Qt.white
    base = QColor(0x20, 0x20, 0x20)
    window = QColor(0x30, 0x30, 0x30)
    textdisabled = QColor(0x9B, 0x9B, 0x9B)
    highlight = QColor(0x2E, 0x93, 0xFF)
    highlight_disabled = window
    link = QColor(0x2E, 0x93, 0xFF)

    light = QColor(174, 174, 174)
    mid = QColor(89, 89, 89)
    dark = QColor(118, 118, 118)
    shadow = QColor(141, 141, 141)
    palette = QPalette()
    palette.setColor(QPalette.Window, window)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Disabled, QPalette.WindowText, textdisabled)
    palette.setColor(QPalette.Base, base)
    palette.setColor(QPalette.AlternateBase, window)
    palette.setColor(QPalette.Disabled, QPalette.Base, window)
    palette.setColor(QPalette.Disabled, QPalette.AlternateBase, window)
    palette.setColor(QPalette.ToolTipBase, window)
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Disabled, QPalette.Text, textdisabled)
    palette.setColor(QPalette.Button, window)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, textdisabled)
    palette.setColor(QPalette.BrightText, Qt.white)
    palette.setColor(QPalette.Highlight, highlight)
    palette.setColor(QPalette.Disabled, QPalette.Highlight, highlight_disabled)
    palette.setColor(QPalette.HighlightedText, text)
    palette.setColor(QPalette.Light, light)
    palette.setColor(QPalette.Mid, mid)
    palette.setColor(QPalette.Dark, dark)
    palette.setColor(QPalette.Shadow, shadow)
    palette.setColor(QPalette.Link, link)
    return palette


colorthemes = {
    "breeze-dark": breeze_dark,
    "zion-reversed": zion_reversed,
    "dark": dark
}  # type: Mapping[str, Callable[[],QPalette]]

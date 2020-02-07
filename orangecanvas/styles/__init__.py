"""
"""
from typing import Mapping, Callable

from AnyQt.QtCore import Qt
from AnyQt.QtGui import QPalette, QColor


def _make_palette(
        base: QColor, text: QColor, window: QColor,
        highlight: QColor,
        highlight_disabled: QColor,
        text_disabled: QColor, link: QColor,
        light: QColor, mid: QColor, dark: QColor, shadow: QColor

):
    palette = QPalette()
    palette.setColor(QPalette.Window, window)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Disabled, QPalette.WindowText, text_disabled)
    palette.setColor(QPalette.Base, base)
    palette.setColor(QPalette.AlternateBase, window)
    palette.setColor(QPalette.ToolTipBase, window)
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Disabled, QPalette.Text, text_disabled)
    palette.setColor(QPalette.Button, window)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, text_disabled)
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


def breeze_light() -> QPalette:
    # 'Breeze-Light' color scheme from KDE.
    return _make_palette(
        text=QColor("#30363C"),
        text_disabled=QColor("#888786"),
        window=QColor("#EFF0F1"),
        base=QColor("#FCFCFC"),
        highlight=QColor("#00B0EF"),
        highlight_disabled=QColor("#00B0EF"),
        link=QColor("#0057B4"),
        light=QColor("#ffffff"),
        mid=QColor("#c4c9cd"),
        dark=QColor("#888e93"),
        shadow=QColor("#474a4c"),
    )


def breeze_dark() -> QPalette:
    # 'Breeze Dark' color scheme from KDE.
    return _make_palette(
        text=QColor(239, 240, 241),
        text_disabled=QColor(98, 108, 118),
        window=QColor(49, 54, 59),
        base=QColor(35, 38, 41),
        highlight=QColor(61, 174, 233),
        highlight_disabled=QColor(61, 174, 233),
        link=QColor(41, 128, 185),
        light=QColor(69, 76, 84),
        mid=QColor(43, 47, 52),
        dark=QColor(28, 31, 34),
        shadow=QColor(20, 23, 25),
    )


def zion_reversed() -> QPalette:
    # 'Zion Reversed' color scheme from KDE.
    window = QColor(16, 16, 16)
    return _make_palette(
        text=QColor(Qt.white),
        text_disabled=QColor(85, 85, 85),
        window=window,
        base=QColor(Qt.black),
        highlight=QColor(0, 49, 110),
        highlight_disabled=window,
        link=QColor(128, 181, 255),
        light=QColor(174, 174, 174),
        mid=QColor(89, 89, 89),
        dark=QColor(118, 118, 118),
        shadow=QColor(141, 141, 141),
    )


def dark():
    window = QColor(0x30, 0x30, 0x30)
    return _make_palette(
        text=QColor(Qt.white),
        base=QColor(0x20, 0x20, 0x20),
        window=QColor(0x30, 0x30, 0x30),
        text_disabled=QColor(0x9B, 0x9B, 0x9B),
        highlight=QColor(0x2E, 0x93, 0xFF),
        highlight_disabled=window,
        link=QColor(0x2E, 0x93, 0xFF),
        light=QColor(174, 174, 174),
        mid=QColor(89, 89, 89),
        dark=QColor(118, 118, 118),
        shadow=QColor(141, 141, 141),
    )


colorthemes = {
    "breeze-light": breeze_light,
    "breeze-dark": breeze_dark,
    "zion-reversed": zion_reversed,
    "dark": dark
}  # type: Mapping[str, Callable[[],QPalette]]

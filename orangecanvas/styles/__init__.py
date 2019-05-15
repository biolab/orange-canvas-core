"""
QSS style sheets.
"""
from AnyQt.QtGui import QPalette, QColor


def breeze_dark():
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

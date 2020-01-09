"""
Orange Canvas Application

"""
import argparse

from AnyQt.QtWidgets import QApplication

from AnyQt.QtCore import Qt, QUrl, QEvent, QSettings, pyqtSignal as Signal


class CanvasApplication(QApplication):
    fileOpenRequest = Signal(QUrl)

    __args = None

    def __init__(self, argv):
        if hasattr(Qt, "AA_EnableHighDpiScaling"):
            # Turn on HighDPI support when available
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)

        CanvasApplication.__args, argv_ = self.parse_style_arguments(argv)
        if self.__args.style:
            argv_ = argv_ + ["-style", self.__args.style]
        super().__init__(argv_)
        argv[:] = argv_
        self.setAttribute(Qt.AA_DontShowIconsInMenus, True)
        self.configureStyle()

    def event(self, event):
        if event.type() == QEvent.FileOpen:
            self.fileOpenRequest.emit(event.url())
        elif event.type() == QEvent.PolishRequest:
            self.configureStyle()
        return super().event(event)

    @staticmethod
    def parse_style_arguments(argv):
        parser = argparse.ArgumentParser()
        parser.add_argument("-style", type=str, default=None)
        parser.add_argument("-colortheme", type=str, default=None)
        ns, rest = parser.parse_known_args(argv)
        if ns.style is not None:
            if ":" in ns.style:
                ns.style, colortheme = ns.style.split(":", 1)
                if ns.colortheme is None:
                    ns.colortheme = colortheme
        return ns, rest

    @staticmethod
    def configureStyle():
        from orangecanvas import styles
        args = CanvasApplication.__args
        settings = QSettings()
        settings.beginGroup("application-style")
        name = settings.value("style-name", "", type=str)
        if args is not None and args.style:
            # command line params take precedence
            name = args.style

        if name != "":
            inst = QApplication.instance()
            if inst is not None:
                if inst.style().objectName().lower() != name.lower():
                    QApplication.setStyle(name)

        theme = settings.value("palette", "", type=str)
        if args is not None and args.colortheme:
            theme = args.colortheme

        if theme and theme in styles.colorthemes:
            palette = styles.colorthemes[theme]()
            QApplication.setPalette(palette)

import os.path
from unittest.mock import patch
from types import SimpleNamespace as ns

from orangecanvas.gui.test import QCoreAppTestCase
from orangecanvas.help import HelpManager
from orangecanvas.help.provider import HtmlIndexProvider
from orangecanvas.registry.tests import small_testing_registry
from orangecanvas.utils import pkgmeta


class FakeDistribution(pkgmeta.Distribution):
    def read_text(self, filename):
        pass

    def locate_file(self, path):
        return os.path.join(os.path.devnull, path)

    _entry_points = None
    _name = None
    _version = None

    def __init__(self, name, version, eps):
        self._name = name
        self._version = version
        self._entry_points = eps

    @property
    def name(self):
        return self._name

    @property
    def version(self):
        return self._version

    @property
    def entry_points(self):
        return self._entry_points


HELP_PATHS = (
    ("https://example.com/help", ""),
)


class TestHelpManager(QCoreAppTestCase):
    def test_manager(self):
        manager = HelpManager()
        reg = small_testing_registry()
        manager.set_registry(reg)
        ep = pkgmeta.EntryPoint("html-index", f"{__name__}:HELP_PATHS", "-")
        eps = ns(select=lambda *_, **__: [ep])
        dist = FakeDistribution("foo", "0.0", eps)
        vars(ep).update(dist=dist)
        with patch("orangecanvas.help.manager.get_distribution", lambda *_: dist):
            provider = manager.get_provider("foobar")
            self.assertIsInstance(provider, HtmlIndexProvider)

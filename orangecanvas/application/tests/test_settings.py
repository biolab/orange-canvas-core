import logging

from AnyQt.QtCore import QSettings
from AnyQt.QtWidgets import QTreeView
from orangecanvas import config

from ...gui import test

from ..settings import UserSettingsDialog, UserSettingsModel, \
    UserDefaultsPropertyBinding
from ...utils.settings import Settings, config_slot
from ... import registry
from ...registry import tests as registry_tests


class TestUserSettings(test.QAppTestCase):
    def setUp(self):
        logging.basicConfig()
        super().setUp()

    def test(self):
        registry.set_global_registry(registry_tests.small_testing_registry())
        settings = UserSettingsDialog()
        settings.show()

        self.qWait()
        registry.set_global_registry(None)

    def test_settings_model(self):
        store = QSettings(QSettings.IniFormat, QSettings.UserScope,
                          "biolab.si", "Orange Canvas UnitTests")

        defaults = [config_slot("S1", bool, True, "Something"),
                    config_slot("S2", str, "I an not a String",
                                "Disregard the string.")]

        settings = Settings(defaults=defaults, store=store)
        model = UserSettingsModel(settings=settings)

        self.assertEqual(model.rowCount(), len(settings))

        view = QTreeView()
        view.setHeaderHidden(False)

        view.setModel(model)

        view.show()
        self.qWait()

    def test_conda_checkbox(self):
        """
        We want that orange is installed with conda by default, users can
        change this setting in settings if they need to. This test check
        whether the default setting for conda checkbox is True.
        """
        settings = config.settings()
        setting = UserDefaultsPropertyBinding(
            settings, "add-ons/allow-conda")
        self.assertTrue(setting.get())

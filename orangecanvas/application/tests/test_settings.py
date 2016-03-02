import logging

import six

from AnyQt.QtWidgets import QTreeView

from ...gui import test

from ..settings import UserSettingsDialog, UserSettingsModel
from ...utils.settings import Settings, config_slot
from ...utils.qtcompat import QSettings
from ... import registry
from ...registry import tests as registry_tests


class TestUserSettings(test.QAppTestCase):
    def setUp(self):
        logging.basicConfig()
        test.QAppTestCase.setUp(self)

#     def test(self):
#         registry.set_global_registry(registry_tests.small_testing_registry())
#         settings = UserSettingsDialog()
#         settings.show()
#
#         self.app.exec_()
#         registry.set_global_registry(None)

    def test_settings_model(self):
        store = QSettings(QSettings.IniFormat, QSettings.UserScope,
                          "biolab.si", "Orange Canvas UnitTests")

        defaults = [config_slot("S1", bool, True, "Something"),
                    config_slot("S2", six.text_type, "I an not a String",
                                "Disregard the string.")]

        settings = Settings(defaults=defaults, store=store)
        model = UserSettingsModel(settings=settings)

        self.assertEqual(model.rowCount(), len(settings))

        view = QTreeView()
        view.setHeaderHidden(False)

        view.setModel(model)

        view.show()
        self.app.exec_()

#! /usr/bin/env python
import os

from setuptools import setup
from setuptools.command.install import install


class InstallMultilingualCommand(install):
    def run(self):
        super().run()
        self.compile_to_multilingual()

    def compile_to_multilingual(self):
        from trubar import translate

        package_dir = os.path.dirname(os.path.abspath(__file__))
        translate(
            "msgs.jaml",
            source_dir=os.path.join(self.install_lib, "orangecanvas"),
            config_file=os.path.join(package_dir, "i18n", "trubar-config.yaml"))


if __name__ == "__main__":
    # setup.cfg has authoritative package descriptions
    setup(
        cmdclass={
            'install': InstallMultilingualCommand,
        },
    )

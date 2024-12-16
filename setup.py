#! /usr/bin/env python
import os

from setuptools import setup, find_packages
from setuptools.command.install import install


NAME = "orange-canvas-core"
VERSION = "0.2.5"
DESCRIPTION = "Core component of Orange Canvas"

with open("README.rst", "rt", encoding="utf-8") as f:
    LONG_DESCRIPTION = f.read()

URL = "http://orange.biolab.si/"
AUTHOR = "Bioinformatics Laboratory, FRI UL"
AUTHOR_EMAIL = 'contact@orange.biolab.si'

LICENSE = "GPLv3"
DOWNLOAD_URL = 'https://github.com/biolab/orange-canvas-core'
PACKAGES = find_packages()

PACKAGE_DATA = {
    "orangecanvas": ["icons/*.svg", "icons/*png"],
    "orangecanvas.styles": ["*.qss", "orange/*.svg"],
}

INSTALL_REQUIRES = (
    "AnyQt>=0.2.0",
    "docutils",
    "commonmark>=0.8.1",
    "requests",
    "requests-cache",
    "pip>=18.0",
    "dictdiffer",
    "qasync>=0.10.0",
    "importlib_metadata>=4.6; python_version<'3.10'",
    "importlib_resources; python_version<'3.9'",
    "typing_extensions",
    "packaging",
    "numpy",
)


CLASSIFIERS = (
    "Development Status :: 1 - Planning",
    "Environment :: X11 Applications :: Qt",
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    "Operating System :: OS Independent",
    "Topic :: Scientific/Engineering :: Visualization",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Intended Audience :: Education",
    "Intended Audience :: Developers",
)

EXTRAS_REQUIRE = {
    'DOCBUILD': ['sphinx', 'sphinx-rtd-theme'],
}

PROJECT_URLS = {
    "Bug Reports": "https://github.com/biolab/orange-canvas-core/issues",
    "Source": "https://github.com/biolab/orange-canvas-core/",
    "Documentation": "https://orange-canvas-core.readthedocs.io/en/latest/",
}

PYTHON_REQUIRES = ">=3.9"


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
    setup(
        name=NAME,
        version=VERSION,
        description=DESCRIPTION,
        long_description=LONG_DESCRIPTION,
        long_description_content_type="text/x-rst",
        url=URL,
        author=AUTHOR,
        author_email=AUTHOR_EMAIL,
        license=LICENSE,
        packages=PACKAGES,
        package_data=PACKAGE_DATA,
        install_requires=INSTALL_REQUIRES,
        cmdclass={
            'install': InstallMultilingualCommand,
        },
        extras_require=EXTRAS_REQUIRE,
        project_urls=PROJECT_URLS,
        python_requires=PYTHON_REQUIRES,
    )

#! /usr/bin/env python

import sys

try:
    import setuptools
except ImportError:
    import ez_setup
    ez_setup.use_setuptools()

from setuptools import setup, find_packages

NAME = "Orange-Canvas-Core"
VERSION = "0.0.8"
DESCRIPTION = "Core component of Orange Canvas"
LONG_DESCRIPTION = open("README.txt", "rt").read()

URL = "http://orange.biolab.si/"
AUTHOR = "Bioinformatics Laboratory, FRI UL"
AUTHOR_EMAIL = 'contact@orange.biolab.si'

LICENSE = "GPLv3"
DOWNLOAD_URL = 'https://github.org/ales-erjavec/orange-canvas'
PACKAGES = find_packages()

PACKAGE_DATA = {
    "orangecanvas": ["icons/*.svg", "icons/*png"],
    "orangecanvas.styles": ["*.qss", "orange/*.svg"],
}

INSTALL_REQUIRES = (
    "setuptools>=11.3",
    "six",
    "future",
    "AnyQt",
    "docutils",
    "numpy",
)


CLASSIFIERS = (
    "Development Status :: 1 - Planning",
    "Environment :: X11 Applications :: Qt",
    "Programming Language :: Python",
    "Programming Language :: Python :: 2",
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    "Operating System :: OS Independent",
    "Topic :: Scientific/Engineering :: Visualization",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Intended Audience :: Education",
    "Intended Audience :: Science/Research",
    "Intended Audience :: Developers",
)

EXTRAS_REQUIRE = {
    # ?? :python_version<="3.2" does not work (Invalid environment
    # marker error).
    ':python_version=="2.7"': ["futures", "contextlib2", "enum34"],
    ':python_version=="3.0"': ["futures", "contextlib2", "enum34"],
    ':python_version=="3.1"': ["futures", "contextlib2", "enum34"],
    ':python_version=="3.2"': ["futures", "contextlib2", "enum34"],
    ':python_version=="3.3"': ["contextlib2", "enum34"],
}

if __name__ == "__main__":
    setup(name=NAME,
          version=VERSION,
          description=DESCRIPTION,
          long_description=LONG_DESCRIPTION,
          url=URL,
          author=AUTHOR,
          author_email=AUTHOR_EMAIL,
          license=LICENSE,
          packages=PACKAGES,
          package_data=PACKAGE_DATA,
          install_requires=INSTALL_REQUIRES,
          extras_require=EXTRAS_REQUIRE,)

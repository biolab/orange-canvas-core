#! /usr/bin/env python

import sys

try:
    import setuptools
except ImportError:
    import ez_setup
    ez_setup.use_setuptools()

from setuptools import setup, find_packages

NAME = "Orange Canvas Core"
VERSION = "0.0.0"
DESCRIPTION = "Core component of Orange Canvas"
LONG_DESCRIPTION = open("README.txt", "rt").read()

URL = "http://orange.biolab.si/"
AUTHOR = "Bioinformatics Laboratory, FRI UL"
AUTHOR_EMAIL = 'contact@orange.biolab.si'

LICENSE = "GPLv2"
DOWNLOAD_URL = 'https://github.org/ales-erjavec/orange-canvas'
PACKAGES = find_packages()

PACKAGE_DATA = {
    "orangecanvas": ["icons/*.svg", "icons/*png"],
    "orangecanvas.styles": ["*.qss", "orange/*.svg"],
}

INSTALL_REQUIRES = ("six",)

if sys.version_info < (3, 2):
    INSTALL_REQUIRES = INSTALL_REQUIRES + ("futures",)

if sys.version_info < (3, 3):
    INSTALL_REQUIRES = INSTALL_REQUIRES + ("contextlib2",)

if sys.version_info < (3, ):
    INSTALL_REQUIRES = INSTALL_REQUIRES + ("future",)


CLASSIFIERS = (
    "Development Status :: 1 - Planning",
    "Environment :: X11 Applications :: Qt",
    "Programming Language :: Python",
    "Programming Language :: Python :: 2",
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
    "Operating System :: OS Independent",
    "Topic :: Scientific/Engineering :: Artificial Intelligence",
    "Topic :: Scientific/Engineering :: Visualization",
    "Topic :: Software Development :: Libraries :: Python Modules",
    "Intended Audience :: Education",
    "Intended Audience :: Science/Research",
    "Intended Audience :: Developers",
)


if __name__ == "__main__":
    setup(name=NAME,
          description=DESCRIPTION,
          long_description=LONG_DESCRIPTION,
          url=URL,
          author=AUTHOR,
          author_email=AUTHOR_EMAIL,
          license=LICENSE,
          packages=PACKAGES,
          package_data=PACKAGE_DATA,
          install_requires=INSTALL_REQUIRES,)

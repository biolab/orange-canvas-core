"""
Orange Canvas Resource Loader

"""
import os
import glob

from typing import Tuple, Dict, Optional, List, IO

from AnyQt.QtGui import QIcon


def package_dirname(package):
    """Return the directory path where package is located.

    """
    if isinstance(package, str):
        package = __import__(package, fromlist=[""])
    filename = package.__file__
    dirname = os.path.dirname(filename)
    return dirname


def package(qualified_name):
    """Return the enclosing package name where qualified_name is located.

    `qualified_name` can be a module inside the package or even an object
    inside the module. If a package name itself is provided it is returned.

    """
    try:
        module = __import__(qualified_name, fromlist=[""])
    except ImportError:
        # qualified_name could name an object inside a module/package
        if "." in qualified_name:
            qualified_name, attr_name = qualified_name.rsplit(".", 1)
            module = __import__(qualified_name, fromlist=[attr_name])
        else:
            raise

    if module.__package__:
        # the module's enclosing package
        return module.__package__
    else:
        # 'qualified_name' is itself the package
        assert module.__name__ == qualified_name
        return qualified_name


dirname = os.path.abspath(os.path.dirname(__file__))

DEFAULT_SEARCH_PATHS = [("", dirname)]

del dirname


def default_search_paths():
    return DEFAULT_SEARCH_PATHS


def add_default_search_paths(search_paths):
    DEFAULT_SEARCH_PATHS.extend(search_paths)


def search_paths_from_description(desc):
    """Return the search paths for the Category/WidgetDescription.
    """
    paths = []
    if desc.package:
        dirname = package_dirname(desc.package)
        paths.append(("", dirname))
    elif desc.qualified_name:
        dirname = package_dirname(package(desc.qualified_name))
        paths.append(("", dirname))

    if hasattr(desc, "search_paths"):
        paths.extend(desc.search_paths)
    return paths


class resource_loader(object):
    def __init__(self, search_paths=[]):
        self._search_paths = []
        self.add_search_paths(search_paths)

    @classmethod
    def from_description(cls, desc):
        """Construct an resource from a Widget or Category description.
        """
        paths = search_paths_from_description(desc)
        return icon_loader(search_paths=paths)

    def add_search_paths(self, paths):
        """Add `paths` to the list of search paths.
        """
        self._search_paths.extend(paths)

    def search_paths(self):
        """Return a list of all search paths.
        """
        return self._search_paths + default_search_paths()

    def split_prefix(self, path):
        # type: (str) -> Tuple[str, str]
        """Split prefixed path.
        """
        if self.is_valid_prefixed(path) and ":" in path:
            prefix, path = path.split(":", 1)
        else:
            prefix = ""
        return prefix, path

    def is_valid_prefixed(self, path):
        # type: (str) -> bool
        i = path.find(":")
        return i != 1

    def find(self, name):
        # type: (str) -> Optional[str]
        """Find a resource matching `name`.
        """
        prefix, path = self.split_prefix(name)
        if prefix == "" and self.match(path):
            return path
        elif self.is_valid_prefixed(path):
            for pp, search_path in self.search_paths():
                if pp == prefix and \
                        self.match(os.path.join(search_path, path)):
                    return os.path.join(search_path, path)

        return None

    def match(self, path):
        # type: (str) -> bool
        return os.path.exists(path)

    def get(self, name):
        # type: (str) -> bytes
        return self.load(name)

    def load(self, name):
        # type: (str) -> bytes
        return self.open(name).read()

    def open(self, name):
        # type: (str) -> IO[bytes]
        path = self.find(name)
        if path is not None:
            return open(path, "rb")
        else:
            raise FileNotFoundError("Cannot find %r" % name)


class icon_loader(resource_loader):
    _icon_cache = {}  # type: Dict[Tuple[str, ...], QIcon]
    DEFAULT_ICON = "icons/default-widget.svg"

    def match(self, path):
        # type: (str) -> bool
        if super().match(path):
            return True
        return self.is_icon_glob(path)

    def icon_glob(self, path):
        # type: (str) -> List[str]
        name, ext = os.path.splitext(path)
        pattern = name + "_*" + ext
        return glob.glob(pattern)

    def is_icon_glob(self, path):
        # type: (str) -> bool
        name, ext = os.path.splitext(path)
        pattern = name + "_*" + ext
        return bool(glob.glob(pattern))

    def get(self, name, default=None):
        # type: (str, Optional[str]) -> QIcon
        if name:
            path = self.find(name)
        else:
            path = None

        if path is None:
            path = self.find(self.DEFAULT_ICON if default is None else default)
        if path is None:
            return QIcon()

        if self.is_icon_glob(path):
            icons = self.icon_glob(path)
        else:
            icons = [path]

        cache_key = tuple(icons)
        icon = QIcon()
        if icons:
            if cache_key not in self._icon_cache:
                for path in icons:
                    icon.addFile(path)
                self._icon_cache[cache_key] = icon
            else:
                icon = self._icon_cache[cache_key]
        return QIcon(icon)

    def open(self, name):
        raise NotImplementedError

    def load(self, name):
        # type: (str) -> QIcon
        return self.get(name)

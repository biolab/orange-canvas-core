"""
Widget Discovery
================

Discover which widgets are installed/available.

This module implements a discovery process

"""
import abc
import os
import sys
import logging
import types
import pkgutil
from collections import namedtuple
from typing import Union

from .description import (
    WidgetDescription, CategoryDescription,
    WidgetSpecificationError, CategorySpecificationError
)

from . import VERSION_HEX
from . import cache, WidgetRegistry
from . import utils
from ..utils.pkgmeta import entry_points

log = logging.getLogger(__name__)


_CacheEntry = \
    namedtuple(
        "_CacheEntry",
        ["mod_path",         # Module path (filename)
         "name",             # Module qualified import name
         "mtime",            # Modified time
         "project_name",     # distribution name (if available)
         "project_version",  # distribution version (if available)
         "exc_type",         # exception type when last trying to import
         "exc_val",          # exception value (str of value)
         "description"       # WidgetDescription instance
         ]
    )


def default_category_name_for_module(module):
    if isinstance(module, str):
        module = __import__(module, fromlist=[""])
    path = module.__name__.split(".")
    name = path[-1]
    if name == "widgets" and len(path) > 1:
        name = path[-2].capitalize()
    return name


def default_category_for_module(module):
    """
    Return a default constructed :class:`CategoryDescription`
    for a `module`.

    """
    if isinstance(module, str):
        module = __import__(module, fromlist=[""])
    name = default_category_name_for_module(module)
    qualified_name = module.__name__
    return CategoryDescription(
        name=name, qualified_name=qualified_name, package=module.__package__
    )


class WidgetDiscovery(object):
    """
    Base widget discovery runner.
    """
    class Handler:
        @abc.abstractmethod
        def handle_category(self, category: CategoryDescription): pass

        @abc.abstractmethod
        def handle_widget(self, widget: WidgetDescription): pass

    class RegistryHandler(Handler):
        def __init__(self, registry: WidgetRegistry, **kwargs):
            super().__init__(**kwargs)
            self.registry = registry

        def handle_category(self, category: CategoryDescription) -> None:
            self.registry.register_category(category)

        def handle_widget(self, desc: WidgetDescription) -> None:
            self.registry.register_widget(desc)

    def __init__(
            self,
            registry: Union[WidgetRegistry, Handler, None] = None,
            cached_descriptions=None
    ) -> None:
        if isinstance(registry, WidgetRegistry):
            self.registry = registry
            self.handler = WidgetDiscovery.RegistryHandler(registry)
        elif isinstance(registry, WidgetDiscovery.Handler):
            self.handler = registry
            self.registry = None
        elif registry is None:
            self.handler = None
            self.registry = None
        else:
            raise TypeError("'WidgetRegistry', 'Handler' or None expected")

        self.cached_descriptions = cached_descriptions or {}
        version = (VERSION_HEX, )
        if self.cached_descriptions.get("!VERSION") != version:
            self.cached_descriptions.clear()
            self.cached_descriptions["!VERSION"] = version

    def run(self, entry_points_iter):
        """
        Run the widget discovery process from an entry point iterator
        (yielding :class:`importlib.metadata.EntryPoint` instances).

        As a convenience, if `entry_points_iter` is a string it will be used
        to retrieve the iterator using `importlib.metadata.entry_points`.

        """
        if isinstance(entry_points_iter, str):
            entry_points_iter = entry_points(group=entry_points_iter)

        for entry_point in entry_points_iter:
            try:
                point = entry_point.load()
            except Exception:
                log.error("An exception occurred while loading "
                          "entry point '%s'", entry_point, exc_info=True)
                continue

            try:
                if isinstance(point, types.ModuleType):
                    if hasattr(point, "__path__"):
                        # Entry point is a package (a widget category)
                        self.process_category_package(
                            point,
                            name=entry_point.name,
                            distribution=entry_point.dist
                        )
                    else:
                        # Entry point is a module (a single widget)
                        self.process_widget_module(
                            point,
                            name=entry_point.name,
                            distribution=entry_point.dist
                        )
                elif isinstance(point, (types.FunctionType, types.MethodType)):
                    # Entry point is a callable loader function
                    self.process_loader(point)
                elif isinstance(point, (list, tuple)):
                    # An iterator yielding Category/WidgetDescriptor instances.
                    self.process_iter(point)
                else:
                    log.error("Cannot handle entry point %r", point)
            except Exception:
                log.error("An exception occurred while processing %r.",
                          entry_point, exc_info=True)

    def process_widget_module(self, module, name=None, category_name=None,
                              distribution=None):
        """
        Process a widget module.
        """
        try:
            desc = self.widget_description(module, widget_name=name,
                                           distribution=distribution)
        except (WidgetSpecificationError, Exception) as ex:
            log.info("Invalid widget specification.", exc_info=True)
            return

        self.handle_widget(desc)

    def process_category_package(self, category, name=None, distribution=None):
        """
        Process a category package.
        """
        cat_desc = None
        category = asmodule(category)

        if hasattr(category, "widget_discovery"):
            widget_discovery = getattr(category, "widget_discovery")
            self.process_loader(widget_discovery)
            return  # The widget_discovery function handles all
        elif hasattr(category, "category_description"):
            category_description = getattr(category, "category_description")
            try:
                cat_desc = category_description()
            except Exception:
                log.error("Error calling 'category_description' in %r.",
                          category, exc_info=True)
                cat_desc = default_category_for_module(category)
        else:
            try:
                cat_desc = utils.category_from_package_globals(category)
            except (CategorySpecificationError, Exception):
                log.info("Package %r does not describe a category.", category,
                         exc_info=True)
                cat_desc = default_category_for_module(category)

        if cat_desc.name is None:
            if name is not None:
                cat_desc.name = name
            else:
                cat_desc.name = default_category_name_for_module(category)

        if distribution is not None:
            cat_desc.project_name = distribution.name

        self.handle_category(cat_desc)

        desc_iter = self.iter_widget_descriptions(
                        category,
                        category_name=cat_desc.name,
                        distribution=distribution
                        )

        for desc in desc_iter:
            self.handle_widget(desc)

    def process_loader(self, callable):
        """
        Process a callable loader function.
        """
        try:
            callable(self)
        except Exception:
            log.error("Error calling %r", callable, exc_info=True)

    def process_iter(self, iter):
        """
        """
        for desc in iter:
            if isinstance(desc, CategoryDescription):
                self.handle_category(desc)
            elif isinstance(desc, WidgetDescription):
                self.handle_widget(desc)
            else:
                log.error("Category or Widget Description instance "
                          "expected. Got %r.", desc)

    def handle_widget(self, desc):
        """
        Handle a found widget description.

        Base implementation adds it to the registry supplied in the
        constructor.

        """
        if self.handler:
            self.handler.handle_widget(desc)

    def handle_category(self, desc):
        """
        Handle a found category description.

        Base implementation adds it to the registry supplied in the
        constructor.

        """
        if self.handler:
            self.handler.handle_category(desc)

    def iter_widget_descriptions(self, package, category_name=None,
                                 distribution=None):
        """
        Return an iterator over widget descriptions accessible from
        `package`.

        """
        package = asmodule(package)

        for path in package.__path__:
            for _, mod_name, ispkg in pkgutil.iter_modules([path]):
                if ispkg:
                    continue
                name = package.__name__ + "." + mod_name
                source_path = os.path.join(path, mod_name + ".py")
                desc = None

                # Check if the path can be ignored.
                if self.cache_can_ignore(source_path, distribution):
                    log.info("Ignoring %r.", source_path)
                    continue

                # Check if a source file for the module is available
                # and is already cached.
                if self.cache_has_valid_entry(source_path, distribution):
                    desc = self.cache_get(source_path).description

                if desc is None:
                    try:
                        module = asmodule(name)
                    except ImportError:
                        log.info("Could not import %r.", name, exc_info=True)
                        continue
                    except Exception:
                        log.warning("Error while importing %r.", name,
                                    exc_info=True)
                        continue

                    try:
                        desc = self.widget_description(
                                 module,
                                 category_name=category_name,
                                 distribution=distribution
                                 )
                    except WidgetSpecificationError:
                        self.cache_log_error(
                                 source_path, WidgetSpecificationError,
                                 distribution
                                 )

                        continue
                    except Exception:
                        log.warning("Problem parsing %r", name, exc_info=True)
                        continue
                yield desc
                self.cache_insert(source_path, os.stat(source_path).st_mtime,
                                  desc, distribution)

    def widget_description(self, module, widget_name=None,
                           category_name=None, distribution=None):
        """
        Return a widget description from a module.
        """
        if isinstance(module, str):
            module = __import__(module, fromlist=[""])

        desc = None
        try:
            desc = utils.widget_from_module_globals(module)
        except WidgetSpecificationError:
            exc_info = sys.exc_info()

        if desc is None:
            # Raise the original exception.
            raise exc_info[1]

        if widget_name is not None:
            desc.name = widget_name

        if category_name is not None:
            desc.category = category_name

        if distribution is not None:
            desc.project_name = distribution.name

        return desc

    def cache_insert(self, module, mtime, description, distribution=None,
                     error=None):
        """
        Insert the description into the cache.
        """
        if isinstance(module, types.ModuleType):
            mod_path = module.__file__
            mod_name = module.__name__
        else:
            mod_path = module
            mod_name = None
        mod_path = fix_pyext(mod_path)

        project_name = project_version = None

        if distribution is not None:
            project_name = distribution.name
            project_version = distribution.version

        exc_type = exc_val = None

        if error is not None:
            if isinstance(error, type):
                exc_type = error
                exc_val = None
            elif isinstance(error, Exception):
                exc_type = type(error)
                exc_val = repr(error.args)

        self.cached_descriptions[mod_path] = \
                _CacheEntry(mod_path, mod_name, mtime, project_name,
                            project_version, exc_type, exc_val,
                            description)

    def cache_get(self, mod_path, distribution=None):
        """
        Get the cache entry for `mod_path`.
        """
        if isinstance(mod_path, types.ModuleType):
            mod_path = mod_path.__file__
        mod_path = fix_pyext(mod_path)
        return self.cached_descriptions.get(mod_path)

    def cache_has_valid_entry(self, mod_path, distribution=None):
        """
        Does the cache have a valid entry for `mod_path`.
        """
        mod_path = fix_pyext(mod_path)

        if not os.path.exists(mod_path):
            return False

        if mod_path in self.cached_descriptions:
            entry = self.cache_get(mod_path)
            mtime = os.stat(mod_path).st_mtime
            if entry.mtime != mtime:
                return False

            if distribution is not None:
                if entry.project_name != distribution.name or \
                        entry.project_version != distribution.version:
                    return False

            if entry.exc_type == WidgetSpecificationError:
                return False

            # All checks pass
            return True

        return False

    def cache_can_ignore(self, mod_path, distribution=None):
        """
        Can the `mod_path` be ignored (i.e. it was determined that it
        could not contain a valid widget description, for instance the
        module does not have a valid description and was not changed from
        the last discovery run).

        """
        mod_path = fix_pyext(mod_path)
        if not os.path.exists(mod_path):
            # Possible orphaned .py[co] file
            return True

        mtime = os.stat(mod_path).st_mtime
        if mod_path in self.cached_descriptions:
            entry = self.cached_descriptions[mod_path]
            return entry.mtime == mtime and \
                    entry.exc_type == WidgetSpecificationError
        else:
            return False

    def cache_log_error(self, mod_path, error, distribution=None):
        """
        Cache that the `error` occurred while processing `mod_path`.
        """
        mod_path = fix_pyext(mod_path)
        if not os.path.exists(mod_path):
            # Possible orphaned .py[co] file
            return
        mtime = os.stat(mod_path).st_mtime

        self.cache_insert(mod_path, mtime, None, distribution, error)


def fix_pyext(mod_path):
    """
    Fix a module filename path extension to always end with the
    modules source file (i.e. strip compiled/optimized .pyc, .pyo
    extension and replace it with .py).

    """
    if mod_path[-4:] in [".pyo", "pyc"]:
        mod_path = mod_path[:-1]
    return mod_path


def widget_descriptions_from_package(package):
    package = asmodule(package)

    desciptions = []
    for _, name, ispkg in pkgutil.iter_modules(
            package.__path__, package.__name__ + "."):
        if ispkg:
            continue
        try:
            module = asmodule(name)
        except Exception:
            log.error("Error importing %r.", name, exc_info=True)
            continue

        desc = None
        try:
            desc = utils.widget_from_module_globals(module)
        except Exception:
            pass

        if not desc:
            log.info("Error in %r", name, exc_info=True)
        else:
            desciptions.append(desc)
    return desciptions


def asmodule(module):
    """
    Return the module references by `module` name. If `module` is
    already an imported module instance, return it as is.

    """
    if isinstance(module, types.ModuleType):
        return module
    elif isinstance(module, str):
        return __import__(module, fromlist=[""])
    else:
        raise TypeError(type(module))


def run_discovery(entry_point, cached=False):
    """
    Run the default widget discovery and return a :class:`WidgetRegistry`
    instance.

    """
    reg_cache = {}
    if cached:
        reg_cache = cache.registry_cache()

    registry = WidgetRegistry()
    discovery = WidgetDiscovery(registry, cached_descriptions=reg_cache)
    discovery.run()
    if cached:
        cache.save_registry_cache(reg_cache)
    return registry

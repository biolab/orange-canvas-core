"""

"""
import os
import string
import itertools
import logging
import urllib.parse
import warnings
from sysconfig import get_path

import typing
from typing import Dict, Optional, List, Tuple, Union, Callable, Sequence

import pkg_resources

from AnyQt.QtCore import QObject, QUrl, QDir

from ..utils.pkgmeta import get_dist_url, is_develop_egg
from . import provider

if typing.TYPE_CHECKING:
    from ..registry import WidgetRegistry, WidgetDescription
    Distribution = pkg_resources.Distribution
    EntryPoint = pkg_resources.EntryPoint

log = logging.getLogger(__name__)


class HelpManager(QObject):
    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self._registry = None  # type: Optional[WidgetRegistry]
        self._providers = {}  # type: Dict[str, provider.HelpProvider]

    def set_registry(self, registry):
        # type: (Optional[WidgetRegistry]) -> None
        """
        Set the widget registry for which the manager should provide help.
        """
        if self._registry is not registry:
            self._registry = registry

    def registry(self):
        # type: () -> Optional[WidgetRegistry]
        """
        Return the previously set with set_registry.
        """
        return self._registry

    def initialize(self) -> None:
        warnings.warn(
            "`HelpManager.initialize` is deprecated and does nothing.",
            DeprecationWarning, stacklevel=2
        )
        return

    def get_provider(self, project: str) -> Optional[provider.HelpProvider]:
        """
        Return a `HelpProvider` for the `project` name.
        """
        provider = self._providers.get(project, None)
        if provider is None:
            try:
                dist = pkg_resources.get_distribution(project)
            except pkg_resources.ResolutionError:
                log.exception("Could not get distribution for '%s'", project)
            else:
                try:
                    provider = get_help_provider_for_distribution(dist)
                except Exception:  # noqa
                    log.exception("Error while initializing help "
                                  "provider for %r", project)

        if provider:
            self._providers[project] = provider
        return provider

    def get_help(self, url):
        # type: (QUrl) -> QUrl
        """
        """
        if url.scheme() == "help" and url.authority() == "search":
            return self.search(qurl_query_items(url))
        else:
            return url

    def description_by_id(self, desc_id):
        # type: (str) -> WidgetDescription
        reg = self._registry
        if reg is not None:
            return get_by_id(reg, desc_id)
        else:
            raise RuntimeError("No registry set. Cannot resolve")

    def search(self, query):
        # type: (Union[QUrl, Dict[str, str], Sequence[Tuple[str, str]]]) -> QUrl
        if isinstance(query, QUrl):
            query = qurl_query_items(query)

        query = dict(query)
        desc_id = query["id"]
        desc = self.description_by_id(desc_id)

        provider = None
        if desc.project_name:
            provider = self.get_provider(desc.project_name)

        if provider is not None:
            return provider.search(desc)
        else:
            raise KeyError(desc_id)

    async def search_async(self, query, timeout=2):
        if isinstance(query, QUrl):
            query = qurl_query_items(query)

        query = dict(query)
        desc_id = query["id"]
        desc = self.description_by_id(desc_id)

        provider = None
        if desc.project_name:
            provider = self.get_provider(desc.project_name)

        if provider is not None:
            return await provider.search_async(desc, timeout=timeout)
        else:
            raise KeyError(desc_id)


def get_by_id(registry, descriptor_id):
    # type: (WidgetRegistry, str) -> WidgetDescription
    for desc in registry.widgets():
        if desc.qualified_name == descriptor_id:
            return desc

    raise KeyError(descriptor_id)


def qurl_query_items(url: QUrl) -> List[Tuple[str, str]]:
    if not url.hasQuery():
        return []
    querystr = url.query()
    return urllib.parse.parse_qsl(querystr)


def _replacements_for_dist(dist):
    # type: (Distribution) -> Dict[str, str]
    replacements = {"PROJECT_NAME": dist.project_name,
                    "PROJECT_NAME_LOWER": dist.project_name.lower(),
                    "PROJECT_VERSION": dist.version,
                    "DATA_DIR": get_path("data")}
    try:
        replacements["URL"] = get_dist_url(dist)
    except KeyError:
        pass

    if is_develop_egg(dist):
        replacements["DEVELOP_ROOT"] = dist.location

    return replacements


def qurl_from_path(urlpath):
    # type: (str) -> QUrl
    if QDir(urlpath).isAbsolute():
        # deal with absolute paths including windows drive letters
        return QUrl.fromLocalFile(urlpath)
    return QUrl(urlpath, QUrl.TolerantMode)


def create_intersphinx_provider(entry_point):
    # type: (EntryPoint) -> Optional[provider.IntersphinxHelpProvider]
    locations = entry_point.resolve()
    if entry_point.dist is not None:
        replacements = _replacements_for_dist(entry_point.dist)
    else:
        replacements = {}

    formatter = string.Formatter()

    for target, inventory in locations:
        # Extract all format fields
        format_iter = formatter.parse(target)
        if inventory:
            format_iter = itertools.chain(format_iter,
                                          formatter.parse(inventory))
        # Names used in both target and inventory
        fields = {name for _, name, _, _ in format_iter if name}

        if not set(fields) <= set(replacements.keys()):
            continue

        target = formatter.format(target, **replacements)
        if inventory:
            inventory = formatter.format(inventory, **replacements)

        targeturl = qurl_from_path(target)
        if not targeturl.isValid():
            continue

        if targeturl.isLocalFile():
            if os.path.exists(os.path.join(target, "objects.inv")):
                inventory = QUrl.fromLocalFile(
                    os.path.join(target, "objects.inv"))
            else:
                log.info("Local doc root '%s' does not exist.", target)
                continue

        else:
            if not inventory:
                # Default inventory location
                inventory = targeturl.resolved(QUrl("objects.inv"))

        if inventory is not None:
            return provider.IntersphinxHelpProvider(
                inventory=inventory, target=target)
    return None


def create_html_provider(entry_point):
    # type: (EntryPoint) -> Optional[provider.SimpleHelpProvider]
    locations = entry_point.resolve()
    if entry_point.dist is not None:
        replacements = _replacements_for_dist(entry_point.dist)
    else:
        replacements = {}

    formatter = string.Formatter()

    for target in locations:
        # Extract all format fields
        format_iter = formatter.parse(target)
        fields = {name for _, name, _, _ in format_iter if name}

        if not set(fields) <= set(replacements.keys()):
            continue
        target = formatter.format(target, **replacements)

        targeturl = qurl_from_path(target)
        if not targeturl.isValid():
            continue

        if targeturl.isLocalFile():
            if not os.path.exists(target):
                log.info("Local doc root '%s' does not exist.", target)
                continue

        if target:
            return provider.SimpleHelpProvider(
                baseurl=QUrl.fromLocalFile(target))

    return None


def create_html_inventory_provider(entry_point):
    # type: (EntryPoint) -> Optional[provider.HtmlIndexProvider]
    locations = entry_point.resolve()
    if entry_point.dist is not None:
        replacements = _replacements_for_dist(entry_point.dist)
    else:
        replacements = {}

    formatter = string.Formatter()

    for target, xpathquery in locations:
        if isinstance(target, (tuple, list)):
            pass

        # Extract all format fields
        format_iter = formatter.parse(target)
        fields = {name for _, name, _, _ in format_iter if name}

        if not set(fields) <= set(replacements.keys()):
            continue
        target = formatter.format(target, **replacements)

        targeturl = qurl_from_path(target)
        if not targeturl.isValid():
            continue

        if targeturl.isLocalFile():
            if not os.path.exists(target):
                log.info("Local doc root '%s' does not exist", target)
                continue

            inventory = QUrl.fromLocalFile(target)
        else:
            inventory = QUrl(target)

        return provider.HtmlIndexProvider(
            inventory=inventory, xpathquery=xpathquery)

    return None


_providers = {
    "intersphinx": create_intersphinx_provider,
    "html-simple": create_html_provider,
    "html-index": create_html_inventory_provider,
}  # type: Dict[str, Callable[[EntryPoint], Optional[provider.HelpProvider]]]

_providers_cache = {}  # type: Dict[str, provider.HelpProvider]


def get_help_provider_for_distribution(dist):
    # type: (pkg_resources.Distribution) -> Optional[provider.HelpProvider]
    """
    Return a HelpProvider for the distribution.

    A 'orange.canvas.help' entry point is used to lookup one of the known
    provider classes, and the corresponding constructor factory is called
    with the entry point as the only parameter.

    Parameters
    ----------
    dist : Distribution

    Returns
    -------
    provider: Optional[provider.HelpProvider]
    """
    if dist.project_name in _providers_cache:
        return _providers_cache[dist.project_name]

    eps = dist.get_entry_map()
    entry_points = eps.get("orange.canvas.help", {})
    if not entry_points:
        # alternative name
        entry_points = eps.get("orangecanvas.help", {})

    provider = None
    for name, entry_point in entry_points.items():
        create = _providers.get(name, None)
        if create:
            try:
                provider = create(entry_point)
            except pkg_resources.DistributionNotFound as err:
                log.warning("Unsatisfied dependencies (%r)", err)
                continue
            except Exception as ex:
                log.exception("Exception {}".format(ex))
            if provider:
                log.info("Created %s provider for %s",
                         type(provider), dist)
                break

    if provider is not None:
        _providers_cache[dist.project_name] = provider
    return provider

"""

"""
import sys
import os
import string
import itertools
import logging
import email
import urllib.parse

from distutils.version import StrictVersion
from operator import itemgetter
from sysconfig import get_path

import typing
from typing import Dict, Optional, List, Union, Callable

import pkg_resources

from AnyQt.QtCore import QObject, QUrl, QDir

from . import provider

if typing.TYPE_CHECKING:
    from ..registry import WidgetRegistry, WidgetDescription
    Distribution = pkg_resources.Distribution
    EntryPoint = pkg_resources.EntryPoint

log = logging.getLogger(__name__)


class HelpManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._registry = None  # type: Optional[WidgetRegistry]
        self._initialized = False
        self._providers = {}  # type: Dict[str, provider.HelpProvider]

    def set_registry(self, registry):
        # type: (Optional[WidgetRegistry]) -> None
        """
        Set the widget registry for which the manager should provide help.
        """
        if self._registry is not registry:
            self._registry = registry
            self._initialized = False
            self.initialize()

    def registry(self):
        # type: () -> Optional[WidgetRegistry]
        """
        Return the previously set with set_registry.
        """
        return self._registry

    def initialize(self):
        # type: () -> None
        if self._initialized or self._registry is None:
            return

        reg = self._registry
        all_projects = set(desc.project_name for desc in reg.widgets()
                           if desc.project_name is not None)

        providers = []
        for project in set(all_projects) - set(self._providers.keys()):
            provider = None
            try:
                dist = pkg_resources.get_distribution(project)
            except pkg_resources.ResolutionError:
                log.exception("Could not get distribution for '%s'", project)
            else:
                try:
                    provider = get_help_provider_for_distribution(dist)
                except Exception:
                    log.exception("Error while initializing help "
                                  "provider for %r", project)

            if provider:
                providers.append((project, provider))

        self._providers.update(dict(providers))
        self._initialized = True

    def get_help(self, url):
        # type: (QUrl) -> QUrl
        """
        """
        self.initialize()
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
        # type: (Union[QUrl, Dict[str, str]]) -> QUrl
        self.initialize()

        if isinstance(query, QUrl):
            query = qurl_query_items(query)

        query = dict(query)
        desc_id = query["id"]
        desc = self.description_by_id(desc_id)

        provider = None
        if desc.project_name:
            provider = self._providers.get(desc.project_name)

        # TODO: Ensure initialization of the provider
        if provider:
            return provider.search(desc)
        else:
            raise KeyError(desc_id)


def get_by_id(registry, descriptor_id):
    # type: (WidgetRegistry, str) -> WidgetDescription
    for desc in registry.widgets():
        if desc.qualified_name == descriptor_id:
            return desc

    raise KeyError(descriptor_id)


def qurl_query_items(url):
    if not url.hasQuery():
        return []
    querystr = url.query()
    return urllib.parse.parse_qsl(querystr)


def get_help_provider_for_description(desc):
    # type: (WidgetDescription) -> Optional[provider.HelpProvider]
    if desc.project_name:
        dist = pkg_resources.get_distribution(desc.project_name)
        return get_help_provider_for_distribution(dist)
    else:
        return None


def is_develop_egg(dist):
    # type: (Distribution) -> bool
    """
    Is the distribution installed in development mode (setup.py develop)
    """
    meta_provider = dist._provider
    egg_info_dir = os.path.dirname(meta_provider.egg_info)
    egg_name = pkg_resources.to_filename(dist.project_name)
    return meta_provider.egg_info.endswith(egg_name + ".egg-info") \
           and os.path.exists(os.path.join(egg_info_dir, "setup.py"))


def left_trim_lines(lines):
    # type: (List[str]) -> List[str]
    """
    Remove all unnecessary leading space from lines.
    """
    lines_striped = zip(lines[1:], map(str.lstrip, lines[1:]))
    lines_striped = filter(itemgetter(1), lines_striped)
    indent = min([len(line) - len(striped) \
                  for line, striped in lines_striped] + [sys.maxsize])

    if indent < sys.maxsize:
        return [line[indent:] for line in lines]
    else:
        return list(lines)


def trim_trailing_lines(lines):
    # type: (List[str]) -> List[str]
    """
    Trim trailing blank lines.
    """
    lines = list(lines)
    while lines and not lines[-1]:
        lines.pop(-1)
    return lines


def trim_leading_lines(lines):
    # type: (List[str]) -> List[str]
    """
    Trim leading blank lines.
    """
    lines = list(lines)
    while lines and not lines[0]:
        lines.pop(0)
    return lines


def trim(string):
    # type: (str) -> str
    """
    Trim a string in PEP-256 compatible way
    """
    lines = string.expandtabs().splitlines()

    lines = list(map(str.lstrip, lines[:1])) + left_trim_lines(lines[1:])

    return "\n".join(trim_leading_lines(trim_trailing_lines(lines)))


# Fields allowing multiple use (from PEP-0345)
MULTIPLE_KEYS = ["Platform", "Supported-Platform", "Classifier",
                 "Requires-Dist", "Provides-Dist", "Obsoletes-Dist",
                 "Project-URL"]


def parse_meta(contents):
    # type: (str) -> Dict[str, Union[str, List[str]]]
    message = email.message_from_string(contents)
    meta = {}  # type: Dict[str, Union[str, List[str]]]
    for key in set(message.keys()):
        if key in MULTIPLE_KEYS:
            meta[key] = list(str(m) for m in message.get_all(key))
        else:
            value = str(message.get(key))
            if key == "Description":
                value = trim(value)
            meta[key] = value

    version = StrictVersion(meta["Metadata-Version"])  # type: ignore

    if version >= StrictVersion("1.3") and "Description" not in meta:
        desc = message.get_payload()
        if isinstance(desc, str):
            meta["Description"] = desc
    return meta


def get_meta_entry(dist, name):
    # type: (pkg_resources.Distribution, str) -> Union[List[str], str, None]
    """
    Get the contents of the named entry from the distributions PKG-INFO file
    """
    meta = get_dist_meta(dist)
    return meta.get(name)


def get_dist_url(dist):
    # type: (pkg_resources.Distribution) -> Optional[str]
    """
    Return the 'url' of the distribution (as passed to setup function)
    """
    return get_meta_entry(dist, "Home-page")


def get_dist_meta(dist):
    # type: (pkg_resources.Distribution) -> Dict[str, Union[str, List[str]]]
    contents = None  # type: Optional[str]
    if dist.has_metadata("PKG-INFO"):
        # egg-info
        contents = dist.get_metadata("PKG-INFO")
    elif dist.has_metadata("METADATA"):
        # dist-info
        contents = dist.get_metadata("METADATA")

    if contents is not None:
        return parse_meta(contents)
    else:
        return {}


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
    entry_points = dist.get_entry_map().get("orange.canvas.help", {})
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

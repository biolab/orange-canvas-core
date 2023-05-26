import itertools
import json
import logging
import os
import re
import shlex
import sys
import sysconfig
from collections import deque
from datetime import timedelta
from enum import Enum
from types import SimpleNamespace
from typing import AnyStr, Callable, List, NamedTuple, Optional, Tuple, TypeVar, Union

import requests
import requests_cache

from AnyQt.QtCore import QObject, QSettings, QStandardPaths, QTimer, Signal, Slot
from pkg_resources import (
    Requirement,
    ResolutionError,
    VersionConflict,
    WorkingSet,
    get_distribution,
    parse_version,
)

from orangecanvas.utils import unique
from orangecanvas.utils.pkgmeta import parse_meta
from orangecanvas.utils.shtools import create_process, python_process

log = logging.getLogger(__name__)

PYPI_API_JSON = "https://pypi.org/pypi/{name}/json"
A = TypeVar("A")
B = TypeVar("B")


def normalize_name(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def prettify_name(name):
    dash_split = name.split('-')
    # Orange3-ImageAnalytics => ImageAnalytics
    orange_prefix = len(dash_split) > 1 and dash_split[0].lower() in ['orange', 'orange3']
    name = ' '.join(dash_split[1:] if orange_prefix else dash_split)
    # ImageAnalytics => Image Analytics  # while keeping acronyms
    return re.sub(r"(?<!^)((?<![\s\d])[A-Z][a-z]|(?<=[a-z])[A-Z])", r" \1", name)


class Installable(
    NamedTuple(
        "Installable", (
            ("name", str),
            ("version", str),
            ("summary", str),
            ("description", str),
            ("package_url", str),
            ("release_urls", List['ReleaseUrl']),
            ("requirements", List[str]),
            ("description_content_type", Optional[str]),
            ("force", bool),
        ))):
    """
    An installable distribution from PyPi

    Attributes
    ----------
    name: str
        The distribution/project name
    version: str
        The release version
    summary: str
        Short one line summary text
    description: str
        A longer more detailed description
    package_url: str
    release_urls: List[ReleaseUrls]
    """

Installable.__new__.__defaults__ = (
    [],
    None,  # description_content_type = None,
    False,  # force = False
)


class ReleaseUrl(
    NamedTuple(
        "ReleaseUrl", (
            ("filename", str),
            ("url", str),
            ("size", int),
            ("python_version", str),
            ("package_type", str),
        ))):
    """
    An source/wheel/egg release for a distribution,
    """


class Available(
    NamedTuple(
        "Available", (
            ("installable", Installable),
    ))):
    """
    An available package.

    Attributes
    ----------
    installable : Installable
    """
    @property
    def project_name(self):
        return self.installable.name

    @property
    def normalized_name(self):
        return normalize_name(self.project_name)


class Installed(
    NamedTuple(
        "Installed", (
            ("installable", Optional[Installable]),
            ("local", 'Distribution'),
            ("required", bool),
            ("constraint", Optional[Requirement]),
        ))):
    """
    An installed package. Does not need to have a corresponding installable
    entry (eg. only local or private distribution)

    Attributes
    ----------
    installable: Installable
        An optional installable item. Is None if the package is not available
        from any package index (is not published and installed locally or
        possibly orphaned).
    local : Distribution
        A :class:`~.Distribution` instance representing the distribution meta
        of the locally installed package.
    required : bool
        Is the distribution required (is part of the core application and
        must not be uninstalled).
    constraint: Optional[Requirement]
        A version constraint string.
    """
    def __new__(cls, installable, local, required=False, constraint=None):
        # type: (Optional[Installable], Distribution, bool, Optional[Requirement]) -> Installed
        return super().__new__(cls, installable, local, required, constraint)

    @property
    def project_name(self):
        if self.installable is not None:
            return self.installable.name
        else:
            return self.local.project_name

    @property
    def normalized_name(self):
        return normalize_name(self.project_name)


#: An installable item/slot
Item = Union[Available, Installed]


def is_updatable(item):
    # type: (Item) -> bool
    if isinstance(item, Available):
        return False
    elif item.installable is None:
        return False
    else:
        inst, dist = item.installable, item.local
        try:
            v1 = parse_version(dist.version)
            v2 = parse_version(inst.version)
        except ValueError:
            return False

        if inst.force:
            return True

        if item.constraint is not None and str(v2) not in item.constraint:
            return False
        else:
            return v1 < v2


def get_meta_from_archive(path):
    """Return project metadata extracted from sdist or wheel archive, or None
    if metadata can't be found."""

    def is_metadata(fname):
        return fname.endswith(('PKG-INFO', 'METADATA'))

    meta = None
    if path.endswith(('.zip', '.whl')):
        from zipfile import ZipFile
        with ZipFile(path) as archive:
            meta = next(filter(is_metadata, archive.namelist()), None)
            if meta:
                meta = archive.read(meta).decode('utf-8')
    elif path.endswith(('.tar.gz', '.tgz')):
        import tarfile
        with tarfile.open(path) as archive:
            meta = next(filter(is_metadata, archive.getnames()), None)
            if meta:
                meta = archive.extractfile(meta).read().decode('utf-8')
    if meta:
        return parse_meta(meta)


def pypi_json_query_project_meta(projects, session=None):
    # type: (List[str], Optional[requests.Session]) -> List[Optional[dict]]
    """
    Parameters
    ----------
    projects : List[str]
        List of project names to query
    session : Optional[requests.Session]
    """
    if session is None:
        session = _session()
    rval = []  # type: List[Optional[dict]]
    for name in projects:
        r = session.get(PYPI_API_JSON.format(name=name))
        if r.status_code != 200:
            rval.append(None)
        else:
            try:
                meta = r.json()
            except json.JSONDecodeError:
                rval.append(None)
            else:
                try:
                    # sanity check
                    installable_from_json_response(meta)
                except (TypeError, KeyError):
                    rval.append(None)
                else:
                    rval.append(meta)
    return rval


def installable_from_json_response(meta):
    # type: (dict) -> Installable
    """
    Extract relevant project meta data from a PyPiJSONRPC response

    Parameters
    ----------
    meta : dict
        JSON response decoded into python native dict.

    Returns
    -------
    installable : Installable
    """
    info = meta["info"]
    name = info["name"]
    version = info.get("version", "0")
    summary = info.get("summary", "")
    description = info.get("description", "")
    content_type = info.get("description_content_type", None)
    package_url = info.get("package_url", "")
    distributions = meta.get("releases", {}).get(version, [])
    release_urls = [ReleaseUrl(r["filename"], url=r["url"], size=r["size"],
                               python_version=r.get("python_version", ""),
                               package_type=r["packagetype"])
                    for r in distributions]
    requirements = info.get("requires_dist", [])

    return Installable(name, version, summary, description, package_url, release_urls,
                       requirements, content_type)


def _session(cachedir=None):
    # type: (...) -> requests.Session
    """
    Return a requests.Session instance

    Parameters
    ----------
    cachedir : Optional[str]
        HTTP cache location.

    Returns
    -------
    session : requests.Session
    """
    if cachedir is None:
        cachedir = QStandardPaths.writableLocation(QStandardPaths.CacheLocation)
        cachedir = os.path.join(cachedir, "networkcache")
    session = requests_cache.CachedSession(
        os.path.join(cachedir, "requests.sqlite"),
        backend="sqlite",
        cache_control=True,
        expire_after=timedelta(days=1),
        stale_if_error=True,
    )
    return session


def optional_map(func: Callable[[A], B]) -> Callable[[Optional[A]], Optional[B]]:
    def f(x: Optional[A]) -> Optional[B]:
        return func(x) if x is not None else None
    return f


class _QueryResult(SimpleNamespace):
    def __init__(
            self, queryname: str, installable: Optional[Installable], **kwargs
    ) -> None:
        self.queryname = queryname
        self.installable = installable
        super().__init__(**kwargs)


def query_pypi(names: List[str]) -> List[_QueryResult]:
    res = pypi_json_query_project_meta(names)
    installable_from_json_response_ = optional_map(
        installable_from_json_response
    )
    return [
        _QueryResult(name, installable_from_json_response_(r))
        for name, r in zip(names, res)
    ]


def list_available_versions(config, session=None):
    # type: (config.Config, Optional[requests.Session]) -> (List[Installable], List[Exception])
    if session is None:
        session = _session()

    exceptions = []

    try:
        defaults = config.addon_defaults_list()
    except requests.exceptions.RequestException as e:
        defaults = []
        exceptions.append(e)

    def getname(item):
        # type: (Dict[str, Any]) -> str
        info = item.get("info", {})
        if not isinstance(info, dict):
            return ""
        name = info.get("name", "")
        assert isinstance(name, str)
        return name

    defaults_names = {getname(a) for a in defaults}

    # query pypi.org for installed add-ons that are not in the defaults
    # list
    installed = [ep.dist for ep in config.addon_entry_points()
                 if ep.dist is not None]
    missing = {dist.project_name.casefold() for dist in installed} - \
              {name.casefold() for name in defaults_names}

    distributions = []
    for p in missing:
        try:
            response = session.get(PYPI_API_JSON.format(name=p))
            if response.status_code != 200:
                continue
            distributions.append(response.json())
        except requests.exceptions.RequestException as e:
            exceptions.append(e)

    packages = []
    for addon in distributions + defaults:
        try:
            packages.append(installable_from_json_response(addon))
        except (TypeError, KeyError) as e:
            exceptions.append(e)

    return packages, exceptions


def installable_items(pypipackages, installed=[]):
    # type: (Iterable[Installable], Iterable[Distribution]) -> List[Item]
    """
    Return a list of installable items.

    Parameters
    ----------
    pypipackages : list of Installable
    installed : list of pkg_resources.Distribution
    """

    dists = {dist.project_name: dist for dist in installed}
    packages = {pkg.name: pkg for pkg in pypipackages}

    # For every pypi available distribution not listed by
    # `installed`, check if it is actually already installed.
    ws = WorkingSet()
    for pkg_name in set(packages.keys()).difference(set(dists.keys())):
        try:
            d = ws.find(Requirement.parse(pkg_name))
        except ResolutionError:
            pass
        except ValueError:
            # Requirements.parse error ?
            pass
        else:
            if d is not None:
                dists[d.project_name] = d

    project_names = unique(itertools.chain(packages.keys(), dists.keys()))

    items = []  # type: List[Item]
    for name in project_names:
        if name in dists and name in packages:
            item = Installed(packages[name], dists[name])
        elif name in dists:
            item = Installed(None, dists[name])
        elif name in packages:
            item = Available(packages[name])
        else:
            assert False
        items.append(item)
    return items


def is_requirement_available(
        req: Union[Requirement, str], working_set: Optional[WorkingSet] = None
) -> bool:
    if not isinstance(req, Requirement):
        req = Requirement.parse(req)
    try:
        if working_set is None:
            d = get_distribution(req)
        else:
            d = working_set.find(req)
    except VersionConflict:
        return False
    except ResolutionError:
        return False
    else:
        return d is not None


def have_install_permissions():
    """Check if we can create a file in the site-packages folder.
    This works on a Win7 miniconda install, where os.access did not. """
    try:
        fn = os.path.join(sysconfig.get_path("purelib"), "test_write_" + str(os.getpid()))
        with open(fn, "w"):
            pass
        os.remove(fn)
        return True
    except PermissionError:
        return False
    except OSError:
        return False


class Command(Enum):
    Install = "Install"
    Upgrade = "Upgrade"
    Uninstall = "Uninstall"


Install = Command.Install
Upgrade = Command.Upgrade
Uninstall = Command.Uninstall

Action = Tuple[Command, Item]


class CommandFailed(Exception):
    def __init__(self, cmd, retcode, output):
        if not isinstance(cmd, str):
            cmd = " ".join(map(shlex.quote, cmd))
        self.cmd = cmd
        self.retcode = retcode
        self.output = output


class Installer(QObject):
    installStatusChanged = Signal(str)
    started = Signal()
    finished = Signal()
    error = Signal(str, object, int, list)

    def __init__(self, parent=None, steps=[]):
        super().__init__(parent)
        self.__interupt = False
        self.__queue = deque(steps)
        self.__statusMessage = ""
        self.pip = PipInstaller()
        self.conda = CondaInstaller()

    def start(self):
        QTimer.singleShot(0, self._next)

    def interupt(self):
        self.__interupt = True

    def setStatusMessage(self, message):
        if self.__statusMessage != message:
            self.__statusMessage = message
            self.installStatusChanged.emit(message)

    @Slot()
    def _next(self):
        command, pkg = self.__queue.popleft()
        try:
            if command == Install \
                    or (command == Upgrade and pkg.installable.force):
                self.setStatusMessage(
                    "Installing {}".format(pkg.installable.name))
                if self.conda:
                    try:
                        self.conda.install(pkg.installable)
                    except CommandFailed:
                        self.pip.install(pkg.installable)
                else:
                    self.pip.install(pkg.installable)
            elif command == Upgrade:
                self.setStatusMessage(
                    "Upgrading {}".format(pkg.installable.name))
                if self.conda:
                    try:
                        self.conda.upgrade(pkg.installable)
                    except CommandFailed:
                        self.pip.upgrade(pkg.installable)
                else:
                    self.pip.upgrade(pkg.installable)
            elif command == Uninstall:
                self.setStatusMessage(
                    "Uninstalling {}".format(pkg.local.project_name))
                if self.conda:
                    try:
                        self.conda.uninstall(pkg.local)
                    except CommandFailed:
                        self.pip.uninstall(pkg.local)
                else:
                    self.pip.uninstall(pkg.local)
        except CommandFailed as ex:
            self.error.emit(
                "Command failed: python {}".format(ex.cmd),
                pkg, ex.retcode, ex.output
            )
            return

        if self.__queue:
            QTimer.singleShot(0, self._next)
        else:
            self.finished.emit()


class PipInstaller:
    def __init__(self):
        arguments = QSettings().value('add-ons/pip-install-arguments', '', type=str)
        self.arguments = shlex.split(arguments)

    def install(self, pkg):
        # type: (Installable) -> None
        cmd = [
            "python", "-m", "pip", "install", "--upgrade",
            "--upgrade-strategy=only-if-needed",
        ] + self.arguments
        if pkg.package_url.startswith(("http://", "https://")):
            version = "=={}".format(pkg.version) if pkg.version is not None else ""
            cmd.append(pkg.name + version)
        else:
            # Package url is path to the (local) wheel
            cmd.append(pkg.package_url)
        run_command(cmd)

    def upgrade(self, package):
        cmd = [
            "python", "-m", "pip", "install",
                "--upgrade", "--upgrade-strategy=only-if-needed",
        ] + self.arguments
        if package.package_url.startswith(("http://", "https://")):
            version = (
                "=={}".format(package.version) if package.version is not None
                else ""
            )
            cmd.append(package.name + version)
        else:
            cmd.append(package.package_url)
        run_command(cmd)

    def uninstall(self, dist):
        cmd = ["python", "-m", "pip", "uninstall", "--yes", dist.project_name]
        run_command(cmd)


class CondaInstaller:
    def __init__(self):
        enabled = QSettings().value('add-ons/allow-conda', True, type=bool)
        if enabled:
            self.conda = self._find_conda()
        else:
            self.conda = None

    def _find_conda(self):
        executable = sys.executable
        bin = os.path.dirname(executable)

        # posix
        conda = os.path.join(bin, "conda")
        if os.path.exists(conda):
            return conda

        # windows
        conda = os.path.join(bin, "Scripts", "conda.bat")
        if os.path.exists(conda):
            # "activate" conda environment orange is running in
            os.environ["CONDA_PREFIX"] = bin
            os.environ["CONDA_DEFAULT_ENV"] = bin
            return conda

    def install(self, pkg):
        version = "={}".format(pkg.version) if pkg.version is not None else ""
        cmd = [self.conda, "install", "--yes", "--quiet",
               "--satisfied-skip-solve",
               self._normalize(pkg.name) + version]
        return run_command(cmd)

    def upgrade(self, pkg):
        version = "={}".format(pkg.version) if pkg.version is not None else ""
        cmd = [self.conda, "install", "--yes", "--quiet",
               "--satisfied-skip-solve",
               self._normalize(pkg.name) + version]
        return run_command(cmd)

    def uninstall(self, dist):
        cmd = [self.conda, "uninstall", "--yes",
               self._normalize(dist.project_name)]
        return run_command(cmd)

    def _normalize(self, name):
        # Conda 4.3.30 is inconsistent, upgrade command is case sensitive
        # while install and uninstall are not. We assume that all conda
        # package names are lowercase which fixes the problems (for now)
        return name.lower()

    def __bool__(self):
        return bool(self.conda)


def run_command(command, raise_on_fail=True, **kwargs):
    # type: (List[str], bool, Any) -> Tuple[int, List[AnyStr]]
    """
    Run command in a subprocess.

    Return `process` return code and output once it completes.
    """
    log.info("Running %s", " ".join(command))

    if command[0] == "python":
        process = python_process(command[1:], **kwargs)
    else:
        process = create_process(command, **kwargs)
    rcode, output = run_process(process, file=sys.stdout)
    if rcode != 0 and raise_on_fail:
        raise CommandFailed(command, rcode, output)
    else:
        return rcode, output


def run_process(process: 'subprocess.Popen', **kwargs) -> Tuple[int, List[AnyStr]]:
    file = kwargs.pop("file", sys.stdout)  # type: Optional[IO]
    if file is ...:
        file = sys.stdout

    output = []
    while process.poll() is None:
        line = process.stdout.readline()
        output.append(line)
        print(line, end="", file=file)
    # Read remaining output if any
    line = process.stdout.read()
    if line:
        output.append(line)
        print(line, end="", file=file)
    return process.returncode, output

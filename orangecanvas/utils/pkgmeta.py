import os
import sys
import email
from operator import itemgetter
from distutils.version import StrictVersion

from typing import TYPE_CHECKING, List, Dict, Optional, Union

import pkg_resources

if TYPE_CHECKING:
    Distribution = pkg_resources.Distribution


def is_develop_egg(dist):
    # type: (Distribution) -> bool
    """
    Is the distribution installed in development mode (setup.py develop)
    """
    meta_provider = dist._provider  # type: ignore
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
    url = get_meta_entry(dist, "Home-page")
    assert isinstance(url, str) or url is None
    return url


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

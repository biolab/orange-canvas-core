from __future__ import annotations
import os
import sys
import re
import json
import email
from operator import itemgetter
from urllib.parse import urlparse
from urllib.request import url2pathname
from typing import List, Dict, Optional, Union, cast

import packaging.version

if sys.version_info < (3, 10):
    from importlib_metadata import EntryPoint, Distribution, entry_points, PackageNotFoundError
else:
    from importlib.metadata import EntryPoint, Distribution, entry_points, PackageNotFoundError


__all__ = [
    "Distribution", "EntryPoint", "entry_points", "normalize_name", "trim",
    "trim_leading_lines", "trim_trailing_lines", "parse_meta", "get_dist_meta",
    "get_distribution", "develop_root", "get_dist_url"
]


def normalize_name(name: str) -> str:
    """
    PEP 503 normalization plus dashes as underscores.
    """
    return re.sub(r"[-_.]+", "-", name).lower().replace('-', '_')


def _direct_url(dist: Distribution) -> dict | None:
    """
    Return PEP-0610 direct_url dict.
    """
    direct_url_content = dist.read_text("direct_url.json")
    if direct_url_content:
        try:
            return json.loads(direct_url_content)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
    return None


def develop_root(dist: Distribution) -> str | None:
    """
    Return the distribution's editable root path if applicable (pip install -e).
    """
    direct_url = _direct_url(dist)
    if direct_url is not None and direct_url.get("dir_info", {}).get("editable", False):
        url = direct_url.get("url", None)
        if url is not None:
            url = urlparse(url)
            if url.scheme == "file":
                return url2pathname(url.path)

    egg_info_dir = dist.locate_file(f"{normalize_name(dist.name)}.egg-info/")
    setup = dist.locate_file("setup.py")
    if os.path.isdir(egg_info_dir) and os.path.isfile(setup):
        return os.path.dirname(setup)
    return None


def is_develop_egg(dist: Distribution) -> bool:
    """
    Is the distribution installed in development mode (setup.py develop)
    """
    return develop_root(dist) is not None


def left_trim_lines(lines: List[str]) -> List[str]:
    """
    Remove all unnecessary leading space from lines.
    """
    lines_striped = zip(lines[1:], map(str.lstrip, lines[1:]))
    lines_striped = filter(itemgetter(1), lines_striped)
    indent = min([len(line) - len(striped)
                  for line, striped in lines_striped] + [sys.maxsize])

    if indent < sys.maxsize:
        return [line[indent:] for line in lines]
    else:
        return list(lines)


def trim_trailing_lines(lines: List[str]) -> List[str]:
    """
    Trim trailing blank lines.
    """
    lines = list(lines)
    while lines and not lines[-1]:
        lines.pop(-1)
    return lines


def trim_leading_lines(lines: List[str]) -> List[str]:
    """
    Trim leading blank lines.
    """
    lines = list(lines)
    while lines and not lines[0]:
        lines.pop(0)
    return lines


def trim(string: str) -> str:
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


def parse_meta(contents: str) -> Dict[str, Union[str, List[str]]]:
    message = email.message_from_string(contents)
    meta = {}  # type: Dict[str, Union[str, List[str]]]
    for key in set(message.keys()):
        if key in MULTIPLE_KEYS:
            meta[key] = list(str(m) for m in message.get_all(key, []))
        else:
            value = str(message.get(key))
            if key == "Description":
                value = trim(value)
            meta[key] = value
    version_str = cast(str, meta["Metadata-Version"])
    version = packaging.version.parse(version_str)
    if version >= packaging.version.parse("1.3") and "Description" not in meta:
        desc = message.get_payload()
        if isinstance(desc, str):
            meta["Description"] = desc
    return meta


def get_meta_entry(dist: Distribution, name: str) -> Union[List[str], str, None]:
    """
    Get the contents of the named entry from the distributions PKG-INFO file
    """
    meta = get_dist_meta(dist)
    return meta.get(name)


def get_dist_url(dist: Distribution) -> Optional[str]:
    """
    Return the 'url' of the distribution (as passed to setup function)
    """
    url = get_meta_entry(dist, "Home-page")
    assert isinstance(url, str) or url is None
    return url


def get_dist_meta(dist: Distribution) -> Dict[str, Union[str, List[str]]]:
    metadata = dist.metadata
    meta: Dict[str, Union[str, List[str]]] = {}
    for key in metadata:
        if key == "Description":
            meta[key] = trim(metadata[key])
        elif key in MULTIPLE_KEYS:
            meta[key] = metadata.get_all(key)
        else:
            meta[key] = metadata[key]
    return meta


def get_distribution(name: str) -> Optional[Distribution]:
    try:
        return Distribution.from_name(name)
    except PackageNotFoundError:
        return None

"""

"""
import typing
from typing import Dict, Optional, List, Tuple, IO, Callable

import os
import logging
import io
import codecs

from urllib.parse import urljoin
from html import parser
from xml.etree.ElementTree import TreeBuilder, Element

from AnyQt.QtCore import QObject, QUrl
from AnyQt.QtNetwork import (
    QNetworkAccessManager, QNetworkDiskCache, QNetworkRequest, QNetworkReply
)

from .intersphinx import read_inventory_v1, read_inventory_v2

from ..utils import assocf
from .. import config

if typing.TYPE_CHECKING:
    from ..registry import WidgetDescription


log = logging.getLogger(__name__)


class HelpProvider(QObject):
    def search(self, description):
        # type: (WidgetDescription) -> QUrl
        raise NotImplementedError


class BaseInventoryProvider(HelpProvider):
    def __init__(self, inventory, parent=None):
        super().__init__(parent)
        self.inventory = QUrl(inventory)

        if not self.inventory.scheme() and not self.inventory.isEmpty():
            self.inventory.setScheme("file")

        self._error = None
        self._fetch_inventory(self.inventory)

    def _fetch_inventory(self, url):
        cache_dir = config.cache_dir()
        cache_dir = os.path.join(cache_dir, "help", type(self).__qualname__)

        try:
            os.makedirs(cache_dir, exist_ok=True)
        except OSError:
            pass

        url = QUrl(self.inventory)
        if not url.isLocalFile():
            # fetch and cache the inventory file.
            manager = QNetworkAccessManager(self)
            cache = QNetworkDiskCache()
            cache.setCacheDirectory(cache_dir)
            manager.setCache(cache)
            req = QNetworkRequest(url)

            # Follow redirects (for example http -> https)
            # If redirects were not followed, the documentation would not be found
            try:
                req.setAttribute(QNetworkRequest.FollowRedirectsAttribute, 1)  # from Qt 5.6
                req.setAttribute(QNetworkRequest.RedirectPolicyAttribute,  # from Qt 5.9
                                 QNetworkRequest.NoLessSafeRedirectPolicy)
            except AttributeError:  # if ran with earlier Qt
                pass

            self._reply = manager.get(req)
            manager.finished.connect(self._on_finished)
        else:
            with open(url.toLocalFile(), "rb") as f:
                self._load_inventory(f)

    def _on_finished(self, reply):
        # type: (QNetworkReply) -> None
        if reply.error() != QNetworkReply.NoError:
            log.error("An error occurred while fetching "
                      "help inventory '{0}'".format(self.inventory))
            self._error = reply.error(), reply.errorString()

        else:
            contents = bytes(reply.readAll())
            self._load_inventory(io.BytesIO(contents))

    def _load_inventory(self, stream):
        # type: (IO[bytes]) -> None
        raise NotImplementedError()


class IntersphinxHelpProvider(BaseInventoryProvider):
    def __init__(self, inventory, target=None, parent=None):
        self.target = target
        self.items = None
        super().__init__(inventory, parent)

    def search(self, description):
        if description.help_ref:
            ref = description.help_ref
        else:
            ref = description.name

        if not self.inventory.isLocalFile() and not self._reply.isFinished():
            self._reply.waitForReadyRead(2000)

        if self.items is None:
            labels = {}
        else:
            labels = self.items.get("std:label", {})
        entry = labels.get(ref.lower(), None)
        if entry is not None:
            _, _, url, _ = entry
            return QUrl(url)
        else:
            raise KeyError(ref)

    def _load_inventory(self, stream):
        version = stream.readline().rstrip()
        if self.inventory.isLocalFile():
            target = QUrl.fromLocalFile(self.target).toString()
        else:
            target = self.target

        if version == b"# Sphinx inventory version 1":
            items = read_inventory_v1(stream, target, urljoin)
        elif version == b"# Sphinx inventory version 2":
            items = read_inventory_v2(stream, target, urljoin)
        else:
            log.error("Invalid/unknown intersphinx inventory format.")
            self._error = (ValueError,
                           "{0} does not seem to be an intersphinx "
                           "inventory file".format(self.target))
            items = None

        self.items = items


class SimpleHelpProvider(HelpProvider):
    def __init__(self, parent=None, baseurl=None):
        super().__init__(parent)
        self.baseurl = baseurl

    def search(self, description):
        # type: (WidgetDescription) -> QUrl
        if description.help_ref:
            ref = description.help_ref
        else:
            raise KeyError()

        url = QUrl(self.baseurl).resolved(QUrl(ref))
        if url.isLocalFile():
            path = url.toLocalFile()
            fragment = url.fragment()
            if os.path.isfile(path):
                return url
            elif os.path.isfile("{}.html".format(path)):
                url = QUrl.fromLocalFile("{}.html".format(path))
                url.setFragment(fragment)
                return url
            elif os.path.isdir(path) and \
                    os.path.isfile(os.path.join(path, "index.html")):
                url = QUrl.fromLocalFile(os.path.join(path, "index.html"))
                url.setFragment(fragment)
                return url
            else:
                raise KeyError()
        else:
            if url.scheme() in ["http", "https"]:
                path = url.path()
                if not (path.endswith(".html") or path.endswith("/")):
                    url.setPath(path + ".html")
        return url


class HtmlIndexProvider(BaseInventoryProvider):
    """
    Provide help links from an html help index page.
    """
    class _XHTMLParser(parser.HTMLParser):
        # A helper class for parsing XHTML into an xml.etree.ElementTree
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.builder = TreeBuilder(element_factory=Element)

        def handle_starttag(self, tag, attrs):
            self.builder.start(tag, dict(attrs),)

        def handle_endtag(self, tag):
            self.builder.end(tag)

        def handle_data(self, data):
            self.builder.data(data)

    def __init__(self, inventory, parent=None, xpathquery=None):
        self.root = None
        self.items = {}  # type: Dict[str, str]
        self.xpathquery = xpathquery  # type: Optional[str]

        super().__init__(inventory, parent)

    def _load_inventory(self, stream):
        # type: (IO[bytes]) -> None
        try:
            contents = stream.read()
        except (IOError, ValueError):
            log.exception("Error reading help index.", exc_info=True)
            return
        # TODO: If contents are from a http response the charset from
        #  content-type header should take precedence.
        try:
            charset = sniff_html_charset(contents)
        except UnicodeDecodeError:
            log.exception("Could not determine html charset from contents.")
            charset = "utf-8"
        try:
            self.items = self._parse(contents.decode(charset or "utf-8"))
        except Exception:
            log.exception("Error parsing")

    def _parse(self, stream):
        parser = HtmlIndexProvider._XHTMLParser(convert_charrefs=True)
        parser.feed(stream)
        self.root = parser.builder.close()

        path = self.xpathquery or ".//div[@id='widgets']//li/a"

        items = {}  # type: Dict[str, str]
        for el in self.root.findall(path):
            href = el.attrib.get("href", None)
            name = el.text.lower()
            items[name] = href

        if not items:
            log.warning("No help references found. Wrong configuration??")
        return items

    def search(self, desc):
        # type: (WidgetDescription) -> QUrl
        if not self.inventory.isLocalFile() and not self._reply.isFinished():
            self._reply.waitForReadyRead(2000)

        if self.items is None:
            labels = {}  # type: Dict[str, str]
        else:
            labels = self.items

        entry = labels.get(desc.name.lower(), None)
        if entry is not None:
            return self.inventory.resolved(QUrl(entry))
        else:
            raise KeyError()


def sniff_html_charset(content: bytes) -> Optional[str]:
    """
    Parse html contents looking for a meta charset definition and return it.

    The contents should be encoded in an ascii compatible single byte encoding
    at least up to the actual meta charset definition, EXCEPT if the contents
    start with a UTF-16 byte order mark in which case 'utf-16' is returned
    without looking further.

    https://www.w3.org/International/questions/qa-html-encoding-declarations

    Parameters
    ----------
    content : bytes

    Returns
    -------
    charset: Optional[str]
        The specified charset if present in contents.
    """
    def parse_content_type(value: str) -> 'Tuple[str, List[Tuple[str, str]]]':
        """limited RFC-2045 Content-Type header parser.
        >>> parse_content_type('text/plain')
        ('text/plain', [])
        >>> parse_content_type('text/plain; charset=cp1252')
        ('text/plain, [('charset', 'cp1252')])
        """
        ctype, _, rest = value.partition(';')
        params = []
        rest = rest.strip()
        for param in map(str.strip, rest.split(";") if rest else []):
            key, _, value = param.partition("=")
            params.append((key.strip(), value.strip()))
        return ctype.strip(), params

    def cmp_casefold(s: str) -> Callable[[str], bool]:
        s = s.casefold()

        def f(s_: str) -> bool:
            return s_.casefold() == s
        return f

    class CharsetSniff(parser.HTMLParser):
        """
        Parse html contents until encountering a meta charset definition.
        """
        class Stop(BaseException):
            # Exception thrown with the result to stop the search.
            def __init__(self, result: str):
                super().__init__(result)
                self.result = result

        def handle_starttag(
                self, tag: str, attrs: 'List[Tuple[str, Optional[str]]]'
        ) -> None:
            if tag.lower() == "meta":
                attrs = [(k, v) for k, v in attrs if v is not None]
                charset = assocf(attrs, cmp_casefold("charset"))
                if charset is not None:
                    raise CharsetSniff.Stop(charset[1])
                http_equiv = assocf(attrs, cmp_casefold("http-equiv"))
                if http_equiv is not None \
                        and http_equiv[1].lower() == "content-type":
                    content = assocf(attrs, cmp_casefold("content"))
                    if content is not None:
                        _, prms = parse_content_type(content[1])
                    else:
                        prms = []
                    charset = assocf(prms, cmp_casefold("charset"))
                    if charset is not None:
                        raise CharsetSniff.Stop(charset[1])

    if content.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return 'utf-16'

    csparser = CharsetSniff()
    try:
        csparser.feed(content.decode("latin-1"))
    except CharsetSniff.Stop as rv:
        return rv.result
    else:
        return None

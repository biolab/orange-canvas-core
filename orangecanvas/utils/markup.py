from collections import OrderedDict
from xml.sax.saxutils import escape

from typing import Mapping, Callable

import docutils.core


def render_plain(content: str) -> str:
    """
    Return a html fragment for a plain pre-formatted text

    Parameters
    ----------
    content : str
        Plain text content

    Returns
    -------
    html : str
    """
    return '<p style="white-space: pre-wrap;">' + escape(content) + "</p>"


def render_html(content: str) -> str:
    """
    Return a html fragment unchanged.

    Parameters
    ----------
    content : str
        Html text.

    Returns
    -------
    html : str
    """
    return content


def render_markdown(content: str) -> str:
    """
    Return a html fragment from markdown text content

    Parameters
    ----------
    content : str
        A markdown formatted text

    Returns
    -------
    html : str
    """
    # commonmark >= 0.8.1; but only optionally. Many other packages may pin it
    # to <0.8 due to breaking changes.
    try:
        import commonmark
    except ImportError:
        return render_plain(content)
    else:
        return commonmark.commonmark(content)


def render_rst(content: str) -> str:
    """
    Return a html fragment from a RST text content

    Parameters
    ----------
    content : str
        A RST formatted text content

    Returns
    -------
    html : str
    """
    overrides = {
        "report_level": 10,  # suppress errors from appearing in the html
        "output-encoding": "utf-8"
    }
    html = docutils.core.publish_string(
        content, writer_name="html",
        settings_overrides=overrides
    )
    return html.decode("utf-8")


ContentRenderer = OrderedDict([
    ("text/plain", render_plain),
    ("text/rst", render_rst),
    ("text/x-rst", render_rst),
    ("text/markdown", render_markdown),
    ("text/html", render_html),
])  # type: Mapping[str, Callable[[str], str]]


def render_as_rich_text(content: str, content_type="text/plain") -> str:
    # split off the parameters (not supported)
    content_type, _, _ = content_type.partition(";")
    renderer = ContentRenderer.get(content_type.lower(), render_plain)
    try:
        return renderer(content)
    except (ImportError, ValueError):
        return render_plain(content)

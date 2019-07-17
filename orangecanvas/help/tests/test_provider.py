import base64
import codecs
import io

import unittest
from orangecanvas.gui.test import QCoreAppTestCase

from orangecanvas.help.provider import sniff_html_charset, HtmlIndexProvider


class TestUtils(unittest.TestCase):
    def test_sniff_html_charset(self):
        contents = (
            b'<html>\n'
            b' <header>\n'
            b'   <meta http-equiv="Content-Type" \n'
            b'         content="text/html; charset=cp1252" />\n'
            b' </header>\n'
            b'</html>'
        )
        self.assertEqual(sniff_html_charset(contents), "cp1252")
        self.assertEqual(sniff_html_charset(contents[:-7]), "cp1252")
        self.assertEqual(
            sniff_html_charset(contents[:-7] + b'.<>>,<<.\xfe\xff<'),
            "cp1252"
        )
        contents = (
            b'<html>\n'
            b' <header>\n'
            b'   <meta charset="utf-8" />\n'
            b' </header>\n'
            b'</html>'
        )
        self.assertEqual(sniff_html_charset(contents), "utf-8")
        self.assertEqual(sniff_html_charset(codecs.BOM_UTF8 + contents), "utf-8")

        self.assertEqual(sniff_html_charset(b''), None)
        self.assertEqual(sniff_html_charset(b'<html></html>'), None)

        self.assertEqual(
            sniff_html_charset(
                codecs.BOM_UTF16_BE +"<html></html>".encode("utf-16-be")
            ),
            'utf-16'
        )


def data_url(mimetype, payload):
    # type: (str, bytes) -> str
    payload = base64.b64encode(payload).decode("ascii")
    return "data:{};base64,{}".format(mimetype, payload)


class TestHtmlIndexProvider(QCoreAppTestCase):
    def test(self):
        contents = (
            b'<html>\n'
            b' <header>\n'
            b'   <meta charset=cp1252" />\n'
            b' </header>\n'
            b' <body><div id="widgets">\n'
            b'  <ul>\n'
            b'   <li><a href="a.html">aa</li>\n'
            b'  </ul>\n'
            b'  </div>\n'
            b'</html>'
        )
        url = data_url("text/html", contents)
        p = HtmlIndexProvider(url)
        p._load_inventory(io.BytesIO(contents))
        self.assertEqual(p.items, {"aa": "a.html"})

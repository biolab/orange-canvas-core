import base64
import codecs

import unittest

from AnyQt.QtCore import QUrl

from orangecanvas.gui.test import QCoreAppTestCase

from orangecanvas.help.provider import sniff_html_charset, HtmlIndexProvider
from orangecanvas.registry import WidgetDescription
from orangecanvas.utils.asyncutils import get_event_loop
from orangecanvas.utils.shtools import temp_named_file


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
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.loop = get_event_loop()

    @classmethod
    def tearDownClass(cls):
        cls.loop.close()
        super().tearDownClass()

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
        with temp_named_file(contents.decode("ascii"),) as fname:
            url = QUrl.fromLocalFile(fname)
            p = HtmlIndexProvider(url)
            loop = get_event_loop()
            desc = WidgetDescription(name="aa", id="aa", qualified_name="aa")
            res = loop.run_until_complete(p.search_async(desc))
            self.assertEqual(res, url.resolved(QUrl("a.html")))
            self.assertEqual(p.items, {"aa": "a.html"})

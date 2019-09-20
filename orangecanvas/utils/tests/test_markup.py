import unittest
from orangecanvas.utils import markup


RST = """
Title
-----

* aaa
* bbb
"""

MD = """
Title
-----

* aaa
* bbb
"""

HTML = """<h3>Title</h3><p><ul><li>aaa</li><li>bbb</li></ul></p>"""


# This does not really test much since most of it is in 3rd party
# implementation. Just run through the calls
class TestMarkup(unittest.TestCase):
    def test_markup(self):
        c = markup.render_as_rich_text(RST, "text/x-rst",)
        self.assertIn("<", c)
        c = markup.render_as_rich_text(MD, "text/markdown")
        self.assertTrue(c.startswith("<"))
        c = markup.render_as_rich_text(HTML, "text/html")
        self.assertTrue(c.startswith("<"))
        c = markup.render_as_rich_text(RST, "text/plain")
        self.assertIn("<", c)

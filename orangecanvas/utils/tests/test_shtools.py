import os

from orangecanvas.utils.shtools import python_process, temp_named_file

import unittest


class Test(unittest.TestCase):
    def test_python_process(self):
        p = python_process(["-c", "print('Hello')"])
        out, _ = p.communicate()
        self.assertEqual(out.strip(), "Hello")
        self.assertEqual(p.wait(), 0)

    def test_temp_named_file(self):
        cases = [
            ("Hello", "utf-8"),
            ("Hello", "utf-16"),
        ]
        for content, encoding in cases:
            with temp_named_file(content, encoding=encoding) as fname:
                with open(fname, "r", encoding=encoding) as f:
                    c = f.read()
                    self.assertEqual(c, content)
            self.assertFalse(os.path.exists(fname))

from orangecanvas.utils.shtools import python_process

import unittest


class Test(unittest.TestCase):
    def test_python_process(self):
        p = python_process(["-c", "print('Hello')"])
        out, _ = p.communicate()
        self.assertEqual(out.strip(), "Hello")
        self.assertEqual(p.wait(), 0)

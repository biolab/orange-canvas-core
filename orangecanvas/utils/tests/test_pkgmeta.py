import os
from unittest import TestCase

from orangecanvas.utils.pkgmeta import (
    Distribution, normalize_name, is_develop_egg, get_dist_meta, parse_meta,
    trim, develop_root,
)


class TestPkgMeta(TestCase):
    def test_normalize_name(self):
        self.assertEqual(normalize_name("a-c_4"), "a_c_4")

    def test_is_develop_egg(self):
        d = Distribution.from_name("AnyQt")
        is_develop_egg(d)
        try:
            d = Distribution.from_name("orange-canvas-core")
        except Exception:
            pass
        else:
            is_develop_egg(d)

    def test_develop_root(self):
        d = Distribution.from_name("AnyQt")
        path = develop_root(d)
        if path is not None:
            self.assertTrue(os.path.isfile(d.locate_file("setup.py")))
        try:
            d = Distribution.from_name("orange-canvas-core")
        except Exception:
            pass
        else:
            path = develop_root(d)
            if path is not None:
                self.assertTrue(os.path.isfile(d.locate_file("setup.py")))

    def test_get_dist_meta(self):
        d = Distribution.from_name("AnyQt")
        meta = get_dist_meta(d)
        self.assertEqual(meta["Name"], "AnyQt")

    def test_parse_meta(self):
        m = parse_meta(trim("""
            Metadata-Version: 1.0
            Name: AA
            Version: 0.1
            Requires-Dist: foo
            Requires-Dist: bar
        """))
        self.assertEqual(m["Name"], "AA")
        self.assertEqual(m["Version"], "0.1")
        self.assertEqual(m["Requires-Dist"], ["foo", "bar"])

    def test_trim(self):
        self.assertEqual(trim("A\n    a\n    b"), "A\na\nb")

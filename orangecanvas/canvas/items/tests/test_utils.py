import math

import unittest
from AnyQt.QtGui import QPainterPath

from ..utils import (
    linspace, linspace_trunc, argsort, composition, qpainterpath_sub_path
)


class TestUtils(unittest.TestCase):
    def test_linspace(self):
        cases = [
            (0, []),
            (1, [0.0]),
            (2, [0.0, 1.0]),
            (3, [0.0, 0.5, 1.0]),
            (4, [0.0, 1./3, 2./3, 1.0]),
            (5, [0.0, 0.25, 0.5, 0.75, 1.0]),
        ]
        for n, expected in cases:
            self.assertSequenceEqual(
                list(linspace(n)), expected
            )

    def test_linspace_trunc(self):
        cases = [
            (0, []),
            (1, [0.5]),
            (2, [1./3, 2./3]),
            (3, [0.25, 0.5, 0.75]),
        ]
        for n, expected in cases:
            self.assertSequenceEqual(
                list(linspace_trunc(n)), expected
            )

    def test_argsort(self):
        cases = [
            ([], []),
            ([1], [0]),
            ([1, 2, 3], [0, 1, 2]),
            (['c', 'b', 'a'], [2, 1, 0]),
            ([(2, 'b'), (3, 'c'), (1, 'a')], [2, 0, 1])
        ]
        for seq, expected in cases:
            self.assertSequenceEqual(
                argsort(seq), expected
            )
            self.assertSequenceEqual(
                argsort(seq, reverse=True), expected[::-1]
            )

        cases = [
            ([(2, 2), (3,), (5,)], [1, 0, 2]),
        ]
        for seq, expected in cases:
            self.assertSequenceEqual(argsort(seq, key=sum), expected)
            self.assertSequenceEqual(argsort(seq, key=sum, reverse=True),
                                     expected[::-1])

    def test_composition(self):
        idt = composition(ord, chr)
        self.assertEqual(idt("a"), "a")
        next = composition(composition(ord, lambda a: a + 1), chr)
        self.assertEqual(next("a"), "b")

    def test_qpainterpath_sub_path(self):
        path = QPainterPath()
        p = qpainterpath_sub_path(path, 0, 0.5)
        self.assertTrue(p.isEmpty())

        path = QPainterPath()
        path.moveTo(0., 0.)
        path.quadTo(0.5, 0.0, 1.0, 0.0)

        p = qpainterpath_sub_path(path, 0, 0.5)
        els = p.elementAt(0)
        ele = p.elementAt(p.elementCount() - 1)
        self.assertEqual((els.x, els.y), (0.0, 0.0))
        self.assertTrue(math.isclose(ele.x, 0.5))
        self.assertEqual(ele.y, 0.0)

        p = qpainterpath_sub_path(path, 0.5, 1.0)
        els = p.elementAt(0)
        ele = p.elementAt(p.elementCount() - 1)
        self.assertTrue(math.isclose(els.x, 0.5))
        self.assertEqual(els.y, 0.0)
        self.assertEqual((ele.x, ele.y), (1.0, 0.0))

        path = QPainterPath()
        path.moveTo(0., 0.)
        path.lineTo(0.5, 0.0)
        path.lineTo(1.0, 0.0)

        p = qpainterpath_sub_path(path, 0.25, 0.75)
        els = p.elementAt(0)
        ele = p.elementAt(p.elementCount() - 1)
        self.assertTrue(math.isclose(els.x, 0.25))
        self.assertEqual(els.y, 0.0)
        self.assertTrue(math.isclose(ele.x, 0.75))
        self.assertEqual(ele.y, 0.0)

        path = QPainterPath()
        path.moveTo(0., 0.)
        path.lineTo(0.25, 0.)
        path.moveTo(0.75, 0.)
        path.lineTo(1.0, 0.)

        p = qpainterpath_sub_path(path, 0.0, 0.5)
        els = p.elementAt(0)
        ele = p.elementAt(p.elementCount() - 1)
        self.assertEqual((els.x, els.y), (0.0, 0.0))
        self.assertTrue(math.isclose(ele.x, 0.25))
        self.assertEqual(ele.y, 0.0)

        p = qpainterpath_sub_path(path, 0.5, 1.0)
        els = p.elementAt(0)
        ele = p.elementAt(p.elementCount() - 1)
        self.assertTrue(math.isclose(els.x, 0.75))
        self.assertEqual(els.y, 0.0)
        self.assertEqual((ele.x, ele.y), (1.0, 0.0))

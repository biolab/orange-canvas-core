import unittest

from ..utils import linspace, linspace_trunc, argsort, composition


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

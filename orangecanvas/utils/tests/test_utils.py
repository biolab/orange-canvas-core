import unittest

from .. import assocf, assocv


class TestUtils(unittest.TestCase):
    def test_assoc(self):
        cases = [
            ([], "a", None),
            ([("a", 1)], "a",  ("a", 1)),
            ([("a", 1)], "b",  None),
            ([("a", 1), ("b", 2), ("b", 3)], "b", ("b", 2)),
        ]
        for seq, key, expected in cases:
            res = assocf(seq, lambda k: k == key)
            self.assertEqual(res, expected)
            res = assocv(seq, key)
            self.assertEqual(res, expected)

import unittest

from .. import assocf, assocv, uniquify


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

    def test_uniquify(self):
        self.assertEqual(uniquify("A", []), "A-0")
        self.assertEqual(uniquify("A", ["A-0"]), "A-1")
        self.assertEqual(uniquify("A", ["A", "B"]), "A-0")
        self.assertEqual(uniquify("A", ["A", "A-0", "A-1", "B"]), "A-2")

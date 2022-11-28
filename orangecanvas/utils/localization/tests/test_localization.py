import unittest

from orangecanvas.utils.localization import pl


class TestLocalization(unittest.TestCase):
    def test_pl(self):
        for forms, singular, plural in (("word", "word", "words"),
                                        ("sun" , "sun", "suns"),
                                        ("day", "day", "days"),
                                        ("FEE", "FEE", "FEES"),
                                        ("daisy", "daisy", "daisies"),
                                        ("FEY", "FEY", "FEYS"),
                                        ("leaf|leaves", "leaf", "leaves")):
            self.assertEqual(pl(1, forms), singular)
            for n in (2, 5, 101, -1):
                self.assertEqual(pl(n, forms), plural, msg=f"for n={n}")


if __name__ == "__main__":
    unittest.main()

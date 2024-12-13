import importlib
import unittest
import warnings

from orangecanvas.localization import pl


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

    def test_deprecated_import(self):
        warnings.simplefilter("always")
        # Imports must work, but with warning
        with self.assertWarns(DeprecationWarning):
            # unittest discovery may have already imported this file -> reload
            import orangecanvas.utils.localization
            importlib.reload(orangecanvas.utils.localization)
        self.assertIs(orangecanvas.utils.localization.pl, pl)

        with self.assertWarns(DeprecationWarning):
            # pylint: disable=unused-import
            from orangecanvas.utils.localization.si import plsi
            
if __name__ == "__main__":
    unittest.main()

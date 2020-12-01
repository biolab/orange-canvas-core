import os
import sys
import time
import unittest

import orangecanvas.utils.after_exit as ae
import orangecanvas.utils.shtools as sh


def remove_after_exit(fname):
    ae.run_after_exit([
        sys.executable, '-c', f'import os, sys; os.remove(sys.argv[1])', fname
    ])


class TestAfterExit(unittest.TestCase):
    def test_after_exit(self):
        with sh.temp_named_file('', delete=False) as fname:
            r = sh.python_run([
                "-c",
                f"import sys, {__name__} as m\n"
                f"m.remove_after_exit(sys.argv[1])",
                fname
            ])

            start = time.perf_counter()
            while os.path.exists(fname) and time.perf_counter() - start < 5:
                pass
            self.assertEqual(r.returncode, 0)
            self.assertFalse(os.path.exists(fname))

import os
import sys
import time
import unittest

from orangecanvas.utils import shtools as sh
from orangecanvas.application import application as appmod
from orangecanvas.utils.shtools import temp_named_file


def application_test_helper():
    app = appmod.CanvasApplication([])
    app.quit()
    return


class TestApplication(unittest.TestCase):
    def test_application(self):
        res = sh.python_run([
            "-c",
            f"import {__name__} as m\n"
            f"m.application_test_helper()\n"
        ])
        self.assertEqual(res.returncode, 0)


def remove_after_exit(fname):
    appmod.run_after_exit([
        sys.executable, '-c', f'import os, sys; os.remove(sys.argv[1])', fname
    ])


def restart_command_test_helper(fname):
    cmd = [
        sys.executable, '-c', f'import os, sys; os.remove(sys.argv[1])', fname
    ]
    appmod.set_restart_command(cmd)
    assert appmod.restart_command() == cmd
    appmod.restart_cancel()
    assert appmod.restart_command() is None
    appmod.set_restart_command(cmd)


class TestApplicationRestart(unittest.TestCase):
    def test_restart_command(self):
        with temp_named_file('', delete=False) as fname:
            res = sh.python_run([
                "-c",
                f"import sys, {__name__} as m\n"
                f"m.restart_command_test_helper(sys.argv[1])\n",
                fname
            ])
            start = time.perf_counter()
            while os.path.exists(fname) and time.perf_counter() - start < 5:
                pass
            self.assertFalse(os.path.exists(fname))
            self.assertEqual(res.returncode, 0)

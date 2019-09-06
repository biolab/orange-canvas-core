from typing import List, Optional

import os
import sys
import subprocess


def python_process(
        args: List[str],
        script_name: Optional[str]=None,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        **kwargs
) -> subprocess.Popen:
    """
    Run a `sys.executable` in a subprocess with `args`.

    Parameters
    ----------
    args: List[str]
        A list of arguments for the python interpreter (e.g. `['-m', 'pip' ]`)
    script_name : Optional[str]
        If supplied the `script_name` replaces 'python' as the first argument
        of `exec?` call.
    kwargs:
        Passed to subproces.Popen

    Return
    ------
    process : subprocess.Popen

    Examples
    --------
    >>> p = python_process(['--version'])
    >>> p.communicate()[0]
    'Python ...
    >>> p = python_process(['-c', 'print("hello")'])
    >>> p.communicate()[0].rstrip()
    'hello'
    """
    executable = sys.executable
    if os.name == "nt" and os.path.basename(executable) == "pythonw.exe":
        # Don't run the script with a 'gui' (detached) process.
        dirname = os.path.dirname(executable)
        executable = os.path.join(dirname, "python.exe")

    if script_name is not None:
        progname = script_name
    else:
        progname = executable
    return create_process(
        [progname] + args,
        executable=executable, stderr=stderr, stdout=stdout, **kwargs
    )


def create_process(
        args: List[str],
        executable: Optional[str] = None,
        stderr=subprocess.STDOUT,
        stdout=subprocess.PIPE,
        universal_newlines=True,
        **kwargs
) -> subprocess.Popen:
    """
    Create and return a `subprocess.Popen` instance.

    This is a thin wrapper around the `subprocess.Popen`. It only thing it
    does is it ensures that a console window does not open by default on
    Windows.
    """
    if os.name == "nt":
        # do not open a new console window for command on windows.
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        kwargs.setdefault("startupinfo", startupinfo)

    return subprocess.Popen(
        args,
        executable=executable,
        stderr=stderr,
        stdout=stdout,
        universal_newlines=universal_newlines,
        **kwargs
    )
